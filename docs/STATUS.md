# Status

What has run on a real robot, what has only passed offline tests, and what is open. Updated 2026-11-06. The dated
records behind this page are in [`history/`](history/) and [`devices/`](devices/).

## Minerva

The robot runs release `20261105T040341Z-fc68d9d`. The repository is ahead of it: what is below "Merged, not on the
robot" has never run on the arms. [What v1 must do](robots/minerva/V1_ACCEPTANCE.md) lists what delivery needs against
this page.

### Proven on the robot

- Both arms teleoperated live from the GELLO leaders, on the 100 Hz direct profile with collision checking off. First
  powered teleop 2026-09-27, both arms 2026-10-09, a 12-minute two-arm session with the head on 2026-10-31.
- Helm as a service on the Jetson, over HTTPS with a login and one device in control, with the GELLO bridge on the
  operator station.
- The neck on its own receiver, steered by a Quest Pro, on the local network and over Tailscale from a phone hotspot.
- Recording in episode format 8 (14 axes, no torque). One real demonstration, 64 s of the right arm, was exported and
  trained on as a pipeline test (2026-10-22).
- Joint zero (2026-11-01, right J4 and J5), pedals (2026-10-18), gripper force feedback felt on the real leaders
  (2026-10-24).

### Partly tried on the robot

| Feature | How far it got |
| --- | --- |
| Pausing the arms when a camera drops | In the running release, written after a real loose-cable stall. No pause is recorded on the robot. |
| VR arm teleop | A live session on 2026-11-03 ended in a joint-speed trip. No completed session is recorded. |
| Headset 3D view | The head steers over the ordinary link. The operator reports the 3D picture working in the headset when last tried (2026-11-08); no record shows it. |
| Remote headset over WebRTC | Video has never been seen working on a Quest. |
| Guided camera calibration | Stills taken live on 2026-11-02. No solve is recorded on the robot. |
| Table fiducials | Labels are stuck on the table, and the head camera fitted five of them at 0.75 px RMS. |

### Offline or in simulation only

- Replay driving the arms, and policy mode. An exported 14-axis ACT policy loads and answers on the Jetson; none has
  driven the arms.

### Merged, not on the robot

These pass the offline gate and are not in the running release.

- [Episode format 9](data/EPISODE_FORMAT.md): 16 axes, effort and velocity, the head camera's pose per frame. Recording
  refuses without a live head. Its [first live check](data/EPISODE_FORMAT.md#first-live-check-of-format-9) is written.
- The arms holding after a joint-speed trip instead of lowering.
- The lift over USB serial (`firmware/lift_actuator`), tested only in its simulator. `lift` stays inactive in the
  robot's definition and has no receiver.
- The simulation line: scripted demonstrator, generated episodes, randomized layouts, table fiducials.
- The head's commands each taking a fresh offer (about 30 ms more lateness before `command_expired`), a fault record
  keeping its last cycles' timings, and **Restart head**, which re-arms a head its receiver stopped while the arms hold
  ([neck](robots/minerva/NECK_FEETECH.md)). Written after the head faulted holding on 2026-11-08.

### Open

- **Format 9's first live check.** Learning from real data depends on it.
- **A policy trained on all of format 9's axes cannot drive the robot.** Policy mode runs the 14 arm axes and refuses a
  policy with other joints. It fails closed. The exporter cuts a format 9 episode to the arms by name
  (`--joints left,right`) and policy mode takes such a policy's joints by name, but neither has run on real format 9
  data. Driving the head from a policy is future work ([training](data/TRAINING.md)).
- **Generated episodes cannot be exported to LeRobot.** The generator marks every row authority `policy` and the
  simulated task state has no lifecycle state, so the exporter refuses each one (reproduced 2026-11-08). Only
  `train_minerva.py`, which reads the HDF5 files directly, trains on them ([generated data](data/TRAINING.md#generated-data)).
- **No collision checking in the production teleop profile, and no hardware emergency stop that covers every actuator.**
  [Safety](operator/SAFETY.md) says exactly what stops what.
- **The install guides have not been followed on a fresh Jetson.** They were written from the code. The repository's
  profiles describe one unit: see [a new unit's profile](getting-started/NEW_UNIT_PROFILE.md).
- `lift` is not under control and there is no powered base.

## AIZEE

Kept as a robot option and not under active work. [Its page](robots/aizee/README.md) says what it runs and which
`aizee-*` names are really Minerva's.

## The offline gate

`python scripts/dev.py check` passes with no skips. It does not cover what needs torch or OpenCV (`tests/ml`, the
learning and policy-session tests, the collector simulation process), Linux services or hardware. One timing test,
`test_a_live_head_cycles_in_a_process_of_its_own_so_the_arms_never_wait_for_it`, fails about one gate in four on a
Windows laptop, when a scheduler stall exceeds its bound. It has not been relaxed; rerun the gate.
