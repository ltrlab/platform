// The Task card (helm.js renderTask): whether Record and Stop can act now, and in words why Record cannot.
//
// Every session on Live both arms can record (helm/teleop.py TeleopSession._session_capture): there is no setup step
// on the robot; the simulator's task scene is chosen before its session (Set up task). A failed episode keeps its
// partial file and ends only itself: Record starts the next one in the same session (2026-11-08).

const LIFECYCLE_READY = ['HOLD', 'TELEOP'];

// What the capture is waiting for before Record can start, from its status (helm/task_capture.py).
export function readiness(task) {
  const cameras = Object.entries(task.cameras || {}).filter(([, camera]) => camera && typeof camera === 'object');
  const stale = cameras
    .filter(([, camera]) => !camera.fresh)
    .map(([name, camera]) => (camera.error ? `${name} (${camera.error})` : name));
  if (stale.length) return `Waiting for camera frames: ${stale.join(', ')}.`;
  if (task.head && task.head.fresh === false)
    return 'Waiting for the head pose: the head must be running in this session.';
  const phase = task.task?.phase;
  return phase ? `Waiting: ${phase}.` : 'Waiting for the capture to be ready.';
}

// {setup, record: {enabled, reason}, stop, failure, status}: `reason` says why Record cannot act (null when it can);
// `failure` the last failed episode's reason, kept until the next episode starts.
export function taskView(state) {
  const t = state?.teleop || {};
  const task = t.task || {};
  const simulation = state?.mode === 'simulation';
  const running = ['starting', 'running'].includes(t.phase);
  const recording = task.recording || {};
  const active = recording.active === true || recording.state === 'recording';
  const pending = task.last_command?.state === 'pending';
  const failure = !active && recording.state === 'failed' && recording.error ? recording.error : null;
  let reason = null;
  if (t.recording_fault) reason = "This session's own log failed: stop the session before recording again.";
  else if (!running) reason = t.recording_unavailable || 'Start a session first.';
  else if (t.task_unavailable) reason = t.task_unavailable;
  else if (task.failed)
    reason = `Recording stopped in this session (${task.error || 'the capture ended'}): stop the session and start it again to record.`;
  else if (active) reason = 'Recording now.';
  else if (pending) reason = 'Waiting for the capture to answer…';
  else if (!LIFECYCLE_READY.includes(t.state)) reason = 'Record works while the arms hold (E) or follow (T).';
  else if (!task.available) reason = 'The capture is starting…';
  else if (!task.capture_ready) reason = readiness(task);
  const record = { enabled: running && reason === null, reason };
  let status;
  if (t.recording_fault) status = 'Recording failed for this session.';
  else if (active)
    status = `Recording episode ${recording.episode ?? ''}`.trim() + ': Stop recording (or pedal A) finishes it.';
  else if (!running)
    status = t.recording_unavailable
      ? `A session started now records nothing: ${t.recording_unavailable}.`
      : simulation
        ? 'Start the session, then Record while the arms hold or follow.'
        : 'Every session on Live both arms can record: start one, then Record while the arms hold or follow.';
  else if (failure)
    status = `Episode failed: ${failure}. Its partial file is kept${record.enabled ? '; Record starts the next episode.' : '.'}`;
  else status = record.enabled ? 'Ready: Record (or pedal A) starts an episode.' : reason;
  return {
    setup: { shown: simulation, enabled: simulation && !running && !!state?.teleop },
    record,
    stop: { enabled: running && active && !pending && !t.recording_fault },
    failure,
    status,
  };
}
