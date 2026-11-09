import assert from 'node:assert/strict';
import { readiness, taskView } from '../../src/robot_platform/helm/static/task_view.js';

// The Task card: Record works in any session on Live both arms, says why it cannot otherwise, and a failed episode
// leaves the next one possible (2026-11-08: a session started without Set up task could never record, and an episode
// that failed locked recording until the session was stopped).
const ready = { available: true, capture_ready: true, recording: { state: 'idle', active: false } };
const robot = (teleop) =>
  taskView({ mode: 'robot', teleop: { phase: 'running', state: 'HOLD', task: ready, ...teleop } });

// Before a session: no setup step on the robot; the card says whether a session started now records.
let view = taskView({ mode: 'robot', teleop: { phase: 'stopped', recording_unavailable: null } });
assert.equal(view.setup.shown, false);
assert.equal(view.record.enabled, false);
assert.match(view.status, /Every session on Live both arms can record/);
view = taskView({
  mode: 'robot',
  teleop: {
    phase: 'stopped',
    recording_unavailable: 'Recording needs both arms live: choose Live and Both, then start a session',
  },
});
assert.match(view.status, /^A session started now records nothing: Recording needs both arms live/);

// In a session: ready while holding or following; otherwise why not.
view = robot({});
assert.equal(view.record.enabled, true);
assert.equal(view.record.reason, null);
assert.match(view.status, /^Ready: Record \(or pedal A\)/);
assert.equal(robot({ state: 'TELEOP' }).record.enabled, true);
for (const state of ['DISABLED', 'IDLE', 'ENGAGING', 'SHUTDOWN']) {
  view = robot({ state });
  assert.equal(view.record.enabled, false);
  assert.match(view.record.reason, /hold \(E\) or follow \(T\)/);
}
view = robot({ task: null, task_unavailable: 'A session of the head alone records nothing' });
assert.equal(view.record.enabled, false);
assert.equal(view.record.reason, 'A session of the head alone records nothing');
const stale = {
  ...ready,
  capture_ready: false,
  cameras: { left_wrist: { fresh: false, error: null }, right_wrist: { fresh: true }, head: { fresh: true } },
};
view = robot({ task: stale });
assert.equal(view.record.enabled, false);
assert.equal(view.record.reason, 'Waiting for camera frames: left_wrist.');
assert.equal(
  readiness({ cameras: { head: { fresh: true } }, head: { fresh: false } }),
  'Waiting for the head pose: the head must be running in this session.',
);

// A failed episode: kept, its reason shown, and the next one can start in the same session.
const failed = {
  ...ready,
  recording: {
    active: false,
    state: 'failed',
    episode: 1,
    error: 'left_wrist: no fresh camera frame available at the observation cutoff',
  },
};
view = robot({ task: failed });
assert.equal(view.record.enabled, true);
assert.equal(view.failure, failed.recording.error);
assert.match(
  view.status,
  /^Episode failed: left_wrist: no fresh camera frame.*Its partial file is kept; Record starts the next episode\.$/,
);

// Recording: Stop finishes it; Record waits.
view = robot({ task: { ...ready, recording: { active: true, state: 'recording', episode: 2 } } });
assert.equal(view.record.enabled, false);
assert.equal(view.stop.enabled, true);
assert.match(view.status, /^Recording episode 2: Stop recording \(or pedal A\) finishes it\.$/);

// The capture stopped (its worker exited): nothing more records this session, and the card says so.
view = robot({ task: { ...ready, failed: true, error: 'capture worker exited' } });
assert.equal(view.record.enabled, false);
assert.match(view.record.reason, /^Recording stopped in this session \(capture worker exited\): stop the session/);

// The session's own log failed: the latch stays until the session stops.
view = robot({ recording_fault: 'disk full', task: { ...ready, recording: { active: true, state: 'recording' } } });
assert.equal(view.record.enabled, false);
assert.equal(view.stop.enabled, false);
assert.equal(view.status, 'Recording failed for this session.');

// The simulator keeps its scene choice before the session.
view = taskView({
  mode: 'simulation',
  teleop: {
    phase: 'stopped',
    recording_unavailable: 'Recording in the simulator needs its task scene: Set up task before the session',
  },
});
assert.equal(view.setup.shown, true);
assert.equal(view.setup.enabled, true);
assert.equal(
  taskView({ mode: 'simulation', teleop: { phase: 'running', state: 'HOLD', task: ready } }).setup.enabled,
  false,
);
console.log('Helm task card: record in any session, its reasons and a failed episode passed.');
