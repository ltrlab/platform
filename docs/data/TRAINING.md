# From a recording to a policy

This is the path for Minerva: record demonstrations with Helm, review them, export them as a LeRobot dataset, train on
a GPU machine, export the policy, evaluate it, and load it in Helm's policy mode. For AIZEE's separate pipeline see
[LEARNING_PIPELINE.md](../robots/aizee/LEARNING_PIPELINE.md).

## What works today

| Step | State |
| --- | --- |
| Record, review, export (format 8) | Ran on the robot: one real 64 s right-arm demonstration was exported and trained on for a pipeline test. |
| Record and export format 9 (16 axes) | **Never run on the robot.** Offline tests only. The first live check is in [EPISODE_FORMAT.md](EPISODE_FORMAT.md#first-live-check-of-format-9). |
| Train ACT on an export | Ran as a 200-step smoke run on one episode. It proves the path, not a policy. |
| Export a policy and load it on the Jetson | Ran for a 14-axis ACT smoke policy (loaded and answered a `(100, 14)` chunk; see [POLICY_MODE.md](../operator/POLICY_MODE.md)). |
| A trained policy driving the arms | Not shown on the robot. |
| A policy trained on format 9's arms driving the robot | **Not shown.** Export with `--joints left,right` (the 14 arm axes, each found by name); policy mode takes the policy's joints by name. Neither has run on real format 9 data. |
| A policy trained on all 16 axes driving the robot | **Not possible.** Policy mode drives the 14 arm axes and `data/lerobot_policy.py` refuses a policy with other joints. Driving the head from a policy is future work. |

What a person does today: record and review format 9 episodes (once the first live check passes) and export them. For
a policy the robot can drive, export the arms alone with `--joints left,right`: the 14 axes policy mode drives, with
their effort and velocity. A 16-axis export tests the pipeline, but policy mode refuses a 16-axis policy: driving the
head from a policy is future work.

## 1. Record and review

Recording and Replay are Helm features ([HELM_TASK_WORKFLOW.md](../operator/HELM_TASK_WORKFLOW.md)). Episodes are
written on the Jetson under `~/minerva/evidence/live-*/episodes/` as `task_episode_<uuid>.hdf5`, and the review log is
`~/minerva/evidence/live-*/reviews.jsonl`. Open **Replay**, play an episode, and press **Keep** or **Discard**, with an
optional note. A review is one appended line; the episode file is never changed. The latest line per episode wins, so a
verdict can be changed. Reviews are refused while a recording runs.

The exporter takes only complete episodes marked Keep. Partial files (`.partial.hdf5`) and episodes marked Discard are
never exported.

## 2. Copy episodes off the robot

The exporter reads a copy of the evidence folder. Copy it with any file transfer that reaches the Jetson, for example:

```bash
rsync -a <robot-user>@<robot-address>:minerva/evidence/ ~/minerva-episodes/
```

Episodes are large (hundreds of megabytes each, because the three camera streams are stored uncompressed), so copy
only what you need. Keep the layout `<session>/episodes/*.hdf5` plus the session's `reviews.jsonl`: the exporter finds
reviews by that layout.

## 3. Export to LeRobot

Export runs anywhere the repository and `.venv-dev` are, but writing the dataset needs LeRobot at the pinned revision
(step 4). The selection and resampling need only numpy and h5py, so `--dry-run` works without LeRobot.

```bash
python -m robot_platform.data.lerobot_export --evidence ~/minerva-episodes --out datasets/minerva-handoff --dry-run
python -m robot_platform.data.lerobot_export --evidence ~/minerva-episodes --out datasets/minerva-handoff \
    --repo-id minerva/handoff --task "Pick up the cube with the left hand, hand it to the right hand, and put it in the box."
```

| Option | Meaning |
| --- | --- |
| `--evidence DIR` | Required. A copy of `~/minerva/evidence`. |
| `--out DIR` | The dataset directory to create; it must not exist. |
| `--repo-id` | LeRobot's dataset label, default `minerva/handoff`. |
| `--fps N` | Output rate, 1 to 60, default 15 (the capture rate). |
| `--task TEXT` | The language instruction written for every episode. Default: the handoff task. |
| `--include-unreviewed` | Also export episodes with no verdict. Discarded ones are still skipped. |
| `--pre-takeover-s S` | Policy sessions: seconds dropped before each operator take-over, default 1. |
| `--min-stretch-s S` | Policy sessions: the shortest policy or correction stretch kept, default 0.5. |
| `--dry-run` | Print what would be exported and why others are refused. |

What it does to each episode:

- Keeps the span from the first to the last row a human drove with a valid action. A row inside the span that is not
  both refuses the episode.
- A policy session's episode (rows labelled `policy` or `correction`) exports as one LeRobot episode per stretch the
  policy or the operator's correction drove, so none spans a hold between drivers.
- Resamples to a fixed grid by the robot-clock timestamps: each grid time takes the latest recorded frame at or before
  it. A grid time more than `MAX_GAP_PERIODS` = 2.5 periods after its frame (two dropped frames in a row) refuses the
  episode.
- Writes `observation.state` = `qpos`, `action` = `actions` (the next commanded position), `observation.images.<role>`
  for each camera, and the task string. That is every recorded axis (14 for format 8, 16 for format 9), or with
  `--joints` the joints and groups of the robot definition it names: `left,right` is both arms and their grippers.
  Each is found in the episode by its name and written in the definition's order.
- Format 9 adds `observation.effort`, `observation.velocity` and `observation.head_camera_pose`, but only when **every
  exported row of every episode has them** (`complete_extras`). One row without a valid reading leaves that feature out
  of the whole dataset. Only the exported joints count: the head's missing readings do not drop the arms' effort or
  velocity from an arms-only export. The exporter refuses simulated episodes today ([generated data](#generated-data)).
- Never mixes episodes that differ in axes, cameras, image size or extras: the later episode is refused and listed. Export
  such episodes as separate datasets. With `--joints` the exported joints are compared, so episodes recorded in another
  order, or with more axes, share one dataset.
- Writes `meta/minerva_provenance.json`: each exported episode's source file, hash, review, kept span and who drove it.

The dataset is LeRobot format v2.1, the version openpi pins.

## 4. The LeRobot environment

The recipe is `scripts/training_server/setup_lerobot.sh`; it builds `.venv-lerobot` under `$AIZEE_SIM` (default
`~/aizee-sim`) and needs Python 3.12 and an NVIDIA GPU. The pins matter, because the pinned LeRobot predates the
newest dependencies:

| Package | Pin |
| --- | --- |
| lerobot | revision `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5` (openpi's) |
| torch, torchvision | 2.6.0, 0.21.0 (CUDA 12.4 wheels) |
| torchcodec | 0.2.1 |
| av | 14.2.0 (newer returns an `AVRational` where this LeRobot expects a fraction) |
| datasets, huggingface-hub, diffusers | below 4, below 1, below 0.36 |

The script ends by importing LeRobot and printing its dataset version; it should print `OK v2.1` and whether CUDA is
available. [scripts/training_server/README.md](../../scripts/training_server/README.md) describes the rest of the
server's folder layout.

## 5. Check the export

```bash
$AIZEE_SIM/.venv-lerobot/bin/python scripts/training_server/check_lerobot_dataset.py <dataset> <source episode.hdf5>
```

It loads the dataset with LeRobot itself and compares sampled frames with the first exported episode's source:
timestamps on the grid, `observation.state` and `action` equal to the source rows, the format 9 extras when present,
and decoded video quality (PSNR) per camera. It prints which extras the dataset has first.

## 6. Train

ACT through LeRobot, in a detached tmux session:

```bash
NAME=act-handoff DATA=$AIZEE_SIM/data/lerobot/minerva-handoff GPU=0 STEPS=20000 BATCH=8 \
    scripts/training_server/train_act.sh [more LeRobot options, e.g. --policy.chunk_size=50]
```

Defaults are those of the smoke run (batch 8, 200 steps, seed 1000, ACT's chunk of 100, learning rate 1e-5), so set
`STEPS` for a real run. Checkpoints land in `$AIZEE_SIM/ckpt/$NAME`, the log in `$AIZEE_SIM/logs/$NAME.log`. The script
refuses a name that exists. One episode teaches nothing; the smoke run showed only that the path works.

### The in-house trainer

`python/training/train_minerva.py` trains a separate flow-matching + JEPA policy (`minerva_model.py`) on episode HDF5
files directly, with no LeRobot. `minerva_dataset.py` reads `observations/qpos`, `qcmd` and `torques`, `actions`, the
three cameras, `authority` and the language instruction, taking the joint count from the file's `qpos` width and the
joint names from `minerva_joints`; it refuses a dataset whose episodes disagree. Its docstrings still describe a 17-slot
schema and the model defaults are `num_joints=17`, so pass the dataset's width explicitly and treat the 16-axis case as
untested. It does not read the `torque_valid` or `qvel` masks. Its checkpoints load in the simulation harness
(`checkpoint:<path>`); a 17-joint checkpoint is expanded to 14 plant axes. On the training server it is run through
`sim_train.py` and the `launch_train.sh` and `chain_*.sh` scripts, for generated data. It has not trained on real data.

## 7. Export the policy for the robot

On the training server, trace the checkpoint into a TorchScript file the Jetson can run with plain torch:

```bash
python -m robot_platform.data.lerobot_policy export <ckpt>/checkpoints/<step>/pretrained_model <out dir> \
    --dataset-info <dataset>/meta/info.json
```

Only ACT exports so far. The output holds `policy.pt`, `minerva_policy.json` (joints, fps, cameras, image shape) and a
sample for checking another machine. The export fails if the traced chunk differs from LeRobot's by more than 1 mrad.
Copy the folder to `~/minerva/policies/<name>` on the Jetson; Helm's Teleop **Policy** box lists what is there.

Loading matches the policy's joints to the receiver's by name, in whatever order each lists them, and refuses any
other set. Policy mode and its confirmation, take-over and
recording are in [POLICY_MODE.md](../operator/POLICY_MODE.md). Run a new policy on the Jetson's virtual receiver before
any live attempt.

## 8. Evaluate

Closed-loop success in the simulated task scene is the progress measure, not validation loss
([MINERVA_EVAL.md](../simulation/MINERVA_EVAL.md)):

```bash
python -m robot_platform.evaluation run --policy lerobot:<exported dir> --camera-size 320x240 --visual-mode cad
python -m robot_platform.evaluation report <trials.jsonl>
python -m robot_platform.evaluation compare ...   # do two success counts differ?
```

The harness policy interface is 14 arm axes, so it evaluates 14-axis policies only. Hand-logged robot trials go through
the same report. Simulation says nothing proven about the robot ([SIM2REAL.md](../simulation/SIM2REAL.md)).

## Generated data

The simulator can record synthetic demonstrations from a scripted demonstrator
([SIM_GENERATION.md](../simulation/SIM_GENERATION.md)):

```bash
python -m robot_platform.evaluation generate --episodes N --out DIR [--randomize FILE]
python scripts/sim/generate_parallel.py --out DIR --episodes 120 --workers 4 -- --grid 6x5 --jitter 1 --yaw 0.785398
```

`generate_parallel.py` runs several workers on one machine. On the training server, `gen_parallel.py` is its Linux
port, started with `launch_gen.sh` and watched with `gen_status.sh`. Generated episodes are format 9 with the
simulated head fixed at the neck's zero and no head effort, velocity or pose sample (NaN, masked). **The LeRobot
exporter refuses them.** Every row says authority `policy`, which the exporter reads as a Helm policy session, and the
simulated scene's task state names no lifecycle state, so each is refused as "a policy episode whose rows do not all say
their lifecycle state" (reproduced 2026-11-08, with and without `--joints`). `train_minerva.py` reads them directly.
They train the pipeline; they are not robot data and are never marked `sim2real_validated`.
