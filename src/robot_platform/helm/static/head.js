// The Teleop tab's Head card without the DOM: the head (helm/head_teleop.py) and the headset steering it (helm/xr.py,
// static/xr.html). The head follows the headset while a session follows (T); without one it holds at its zero.

const SOURCES = { headset: 'following the headset', holding: 'holding: the headset went quiet', zero: 'at its zero' };

export const signedDegrees = (radians) => `${radians >= 0 ? '+' : ''}${((radians * 180) / Math.PI).toFixed(0)}°`;

// {shown, readout, fault, headset, zero, restart}: zero is whether the Zero button can act (a headset tracking);
// restart whether Restart head can (a faulted head while the arms hold: helm/teleop.py's restart_head).
export function headView(teleop, xr, host) {
  const head = teleop?.head;
  const headset = xr || {};
  const view = {
    shown: Boolean(head) || Boolean(headset.connected),
    fault: false,
    zero: Boolean(headset.tracking),
    restart: Boolean(head?.restartable),
  };
  if (head?.restarting) {
    view.readout = 'Restarting the head where its receiver holds it…';
  } else if (head?.fault) {
    view.readout = head.fault;
    view.fault = true;
  } else if (head) {
    view.readout =
      `Head ${head.state ? head.state.toLowerCase() : 'starting'}` +
      (head.source && head.state === 'TELEOP' ? ` · ${SOURCES[head.source] || head.source}` : '');
  } else {
    view.readout =
      teleop?.phase === 'running'
        ? 'No head in this session.'
        : 'No session: the head moves only while one follows (T).';
  }
  const name = headset.device || 'Headset';
  view.headset = headset.tracking
    ? `${name} tracking · ${Math.round(headset.rate_hz || 0)} Hz · yaw ${signedDegrees(headset.yaw)}` +
      ` · pitch ${signedDegrees(headset.pitch)}`
    : headset.connected
      ? `${name} connected: start head tracking in it.`
      : `No headset: the head holds at its zero. On the Quest, open https://${host}/xr`;
  return view;
}
