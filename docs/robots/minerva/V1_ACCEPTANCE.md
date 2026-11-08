# Minerva v1: what "delivered" means

v1 is the bimanual teleoperation and data-collection rig. From the operator station, one person drives both arms, the
grippers, the head, the lift and the swerve base. Every session records the per-joint torque channel, in a dataset a
customer can train on.

A line is met only when its evidence exists: a dated record in [`history/`](../../history/) or
[`devices/`](../../devices/), or a gate test where the line says so. [Status](../../STATUS.md) is where proof lands, and
this page follows it. **Now** is one of **Met**, **Partly** (some of it has run on the robot) or **Not yet**.

## Teleoperation

| Requirement | Evidence that meets it | Now |
| --- | --- | --- |
| Both arms and grippers follow the GELLO leaders live, on the production profile | A two-arm session record | **Met**: a 12-minute two-arm session with the head on, 2026-10-31 |
| A session as long as a collection day needs, with no trip | A session record of that length (length: to decide) | **Not yet**: the longest recorded is 12 minutes; the VR session of 2026-11-03 ended in a joint-speed trip |
| Gripper force feedback on the leaders | Felt on the real leaders | **Met**: 2026-10-24 |
| After a joint-speed trip the arms hold where they are | A live trip, recorded | **Not yet**: merged, not deployed |
| The headset steers the head | A live session | **Met**: Quest Pro, on the local network and over Tailscale |
| The operator sees the 3D view in the headset | A dated record of it seen in the headset | **Partly**: the operator reports it working when last tried; there is no record yet |
| The lift raises and lowers under control, on its own receiver, with a stop | A live lift session, recorded | **Not yet**: [the firmware](../../../firmware/lift_actuator) is tested in its simulator only, and `lift` is inactive in the robot's definition |
| The swerve base drives from the operator station, with a stop | A live drive, recorded | **Not yet**: there is no powered base |

## Recording and data

| Requirement | Evidence that meets it | Now |
| --- | --- | --- |
| Every session records [format 9](../../data/EPISODE_FORMAT.md): effort, velocity and the head camera's pose | Its [first live check](../../data/EPISODE_FORMAT.md#first-live-check-of-format-9), passed | **Not yet**: recordings so far are format 8 (14 axes, no torque) |
| The lift and the base are in the recording | A format with them, checked live | **Not yet** |
| A recording exports to LeRobot with its effort channel | An exported dataset from a real session | **Partly**: [the export](../../data/DATASET_PIPELINE.md) exists; one format 8 demonstration was exported and trained on as a pipeline test (2026-10-22) |
| A policy trains on exported data with the axes chosen by name | Gate tests, then a dataset from a real session | **Partly**: the exporter's `--joints left,right` picks the 14 arm axes by name and policy mode matches a policy's joints by name, in gate tests ([training](../../data/TRAINING.md)); no dataset from a real session |
| A policy trained on real data drives the arms in a supervised trial | A trial record | **Not yet**: an exported 14-axis policy loads and answers on the Jetson; none has driven the arms |

## Safety

| Requirement | Evidence that meets it | Now |
| --- | --- | --- |
| One hardware emergency stop cuts every actuator: arms, head, lift and base | A test of the stop, recorded | **Not yet**: [the foot switch](../../operator/SAFETY.md) cuts the arm motors only, not the head's 12 V |
| Collision checking on in the production teleop profile, or its absence written as a limit the customer accepts | The profile, or the signed limit | **Not yet**: it is off |
| [Safety](../../operator/SAFETY.md) covers the lift and the base | The page | **Not yet** |

## Build, install and release

| Requirement | Evidence that meets it | Now |
| --- | --- | --- |
| The robot runs a release built from `main` | Its release ID in [Status](../../STATUS.md) | **Not yet**: it runs `20261105T040341Z-fc68d9d`, from before `main` |
| A fresh Jetson comes up from [the Jetson guide](../../getting-started/INSTALL_JETSON.md) alone | An install record | **Not yet**: the guide was written from the code |
| An operator station comes up from [its guide](../../getting-started/INSTALL_OPERATOR_STATION.md) alone | An install record | **Not yet** |
| A second unit gets its own profile from [a new unit's profile](../../getting-started/NEW_UNIT_PROFILE.md) | That unit's profile, and a session on it | **Not yet**: every profile describes one unit |

## Handover

| Requirement | Evidence that meets it | Now |
| --- | --- | --- |
| The [Helm manual](../../operator/HELM_MANUAL.md), [troubleshooting](../../operator/TROUBLESHOOTING.md) and [calibration](../../operator/CALIBRATION.md) cover the lift and the base | The pages | **Partly**: they cover the arms and the head |
| A video of a contact-rich task, with its torque channel | The video and its episode | **Not yet** |

## Not in v1

- Remote video over WebRTC ([the headset on a slow link](../../operator/REMOTE_HEADSET.md) still steers the head).

## To decide

- How long a session, or how many demonstrations, acceptance needs.
- Whether the base is an action in the recording and the policy, or motion the operator does that the policy never
  commands.
- Whether a policy driving the arms is a v1 requirement or the proof point that sells it.
- Whether collision checking must be on, or its absence is a written limit.
