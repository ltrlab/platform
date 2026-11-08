"""Load an exported Minerva LeRobot dataset with LeRobot itself and compare it with the source episode.
usage: check_lerobot_dataset.py <dataset root> <source episode .hdf5>   (the dataset's first episode's source)
Format 9's extras (effort, velocity, head camera pose) are compared too when the dataset has them. Each exported
joint is compared with its own column of the source, found by name: an export with --joints holds fewer, in the robot
definition's order."""

import json
import sys
from pathlib import Path

import h5py
import numpy as np
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

root, source = Path(sys.argv[1]), Path(sys.argv[2])
ROLES = ('left_wrist', 'right_wrist', 'head')
EXTRAS = {
    'observation.effort': 'observations/torques',
    'observation.velocity': 'observations/qvel',
    'observation.head_camera_pose': 'observations/head_camera_pose',
}  # data.lerobot_export.EXTRAS
PER_JOINT = ('observation.effort', 'observation.velocity')  # One value per joint, as the state.
ds = LeRobotDataset(repo_id=f'minerva/{root.name}', root=root)  # Local: the name is only a label.
info = json.loads((root / 'meta/info.json').read_text())
extras = [name for name in EXTRAS if name in info['features']]
print('extras', extras)
print('codebase', info['codebase_version'], 'fps', ds.fps, 'episodes', ds.num_episodes, 'frames', ds.num_frames)
print(
    'video',
    {
        k: (v['info'].get('video.codec'), v['info'].get('video.fps'))
        for k, v in info['features'].items()
        if v['dtype'] == 'video'
    },
)
provenance = json.loads((root / 'meta/minerva_provenance.json').read_text())['episodes'][0]
joints = info['features']['observation.state']['names']
print('joints', len(joints), joints)
with h5py.File(source, 'r') as f:
    value = f.attrs['minerva_joints']
    recorded = [name for name in (value.decode() if isinstance(value, bytes) else str(value)).split(',') if name]
    missing = [name for name in joints if name not in recorded]
    assert not missing, f'the source records no {missing}'
    columns = [recorded.index(name) for name in joints]
    telem = f['timestamps/telem'][:]
    first = provenance['source_span'][0]
    worst = {role: 99.0 for role in ROLES}
    for index in range(0, ds.num_frames, 23):
        item = ds[index]
        row = int(np.searchsorted(telem, telem[first] + index / ds.fps, side='right') - 1)
        assert abs(float(item['timestamp']) - index / ds.fps) < 1e-4, (index, float(item['timestamp']))
        assert np.allclose(item['observation.state'].numpy(), f['observations/qpos'][row][columns], atol=1e-6), index
        assert np.allclose(item['action'].numpy(), f['actions'][row][columns], atol=1e-6), index
        for name in extras:
            expected = f[EXTRAS[name]][row]
            expected = expected[columns] if name in PER_JOINT else expected
            assert np.allclose(item[name].numpy(), expected, atol=1e-6), (name, index)
        for role in ROLES:
            decoded = item[f'observation.images.{role}'].permute(1, 2, 0).numpy().astype(np.float64) * 255
            original = f[f'observations/images/{role}'][row].astype(np.float64)
            mse = np.mean((decoded - original) ** 2)
            worst[role] = min(worst[role], 10 * np.log10(255**2 / max(mse, 1e-9)))
    item = ds[0]
    print(
        'checked',
        len(range(0, ds.num_frames, 23)),
        'frames: timestamps, state, action and extras match the source rows',
    )
    print(
        'image',
        tuple(item['observation.images.head'].shape),
        'worst PSNR dB',
        {k: round(v, 1) for k, v in worst.items()},
    )
    print('task', item['task'])
