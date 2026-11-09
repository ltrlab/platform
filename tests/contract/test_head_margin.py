"""A live head's commands against its service's 10 ms ticks: how late one of its 40 ms cycles may start before the
command it renews expires, the timings a fault record keeps, and Restart head re-arming a stopped head where its
receiver holds it.

On Minerva the head faulted holding, while the arms held: "Head receiver stopped: command_expired · Guarded controller
rejected request: wrong_owner" (2026-11-08, live-head-20261108T180840Z). Its cycle started about 8 ms late (feedback
48 ms old against a 40 ms period), and its service's ticks ran up to 13.46 ms late in that session. Each command took
the offer in the reply before it, so a period of its 100 ms lifetime had gone when it was sent."""

import os
import time

import pytest

from robot_platform.helm.head_teleop import HeadTeleop
from robot_platform.helm.teleop import TeleopCore
from robot_platform.simulation.control_harness import NativeControlHarness
from tests.contract.test_direct_teleop import direct_profile
from tests.contract.test_helm_teleop_live import Clock, Leaders, bundle, run  # noqa: F401
from tests.contract.test_teleop_head import Ticking, head_bundle, live

TICK_MS = 10
ROBOT_FAULT = 'Head receiver stopped: command_expired · Guarded controller rejected request: wrong_owner'


class Service:
    """The head's service as bin/head_controller runs it (control_core's head_service): its receiver ticks every
    10 ms, each tick checks expiry before taking the request waiting, so a request is answered at the first tick
    after it arrives, and the exchange waits for that tick (the clock moves on to it). `late_ms`: the next request's
    tick runs that late, as the service's own ticks do on the Jetson."""

    def __init__(self, config, initial, clock):
        self.inner, self.clock, self.epoch = NativeControlHarness(config, initial), clock, clock()
        self.close = self.inner.close
        self.late_ms = 0

    now_ms = property(lambda self: self.inner.now_ms)
    last = property(lambda self: self.inner.last)

    def _ticks_to(self, now_ms):
        tick = (self.inner.now_ms // TICK_MS + 1) * TICK_MS
        while tick <= now_ms:
            self.inner.step(tick)
            tick += TICK_MS

    def step(self, now_ms, request=None):
        if request is None:
            self._ticks_to(now_ms)
            return self.inner.last
        at = (max(now_ms, self.inner.now_ms) // TICK_MS + 1) * TICK_MS
        self._ticks_to(at - TICK_MS)
        at, self.late_ms = at + self.late_ms, 0
        self.inner.step(at)  # The tick: expiry first, then the request waiting.
        out = self.inner.step(at, request, deferred=True)
        self.clock.now = max(self.clock.now, self.epoch + at / 1000 + 1e-6)
        return out


def head_on_ticks(*, following=False, fresh_offers=None, directory=None):
    """A head on its service's ticks, holding (or following its zero) on its grid for two seconds."""
    clock = Clock()

    def open_service(config, initial):
        service = Service(config, initial, clock)
        service.directory = directory
        return service

    head = HeadTeleop(head_bundle(), live=False, clock=clock, open_harness=open_service)
    head.build()
    if fresh_offers is not None:
        head.session.fresh_offers = fresh_offers
    for action in ('idle', 'enable') + (('engage',) if following else ()):
        head.cycle(action, clock())
    on_grid(head, clock, 50)
    assert head.fault is None and head.state == ('TELEOP' if following else 'HOLD'), (head.state, head.fault)
    return head, clock


def on_grid(head, clock, cycles):
    for _ in range(cycles):
        clock.now = max(clock.now, head.due or clock.now)  # No slot yet after a restart: at once.
        head.cycle(None, clock())


def late_cycle(head, clock, late_ms, *, tick_late_ms=0):
    """One cycle `late_ms` after its slot, its request answered at a tick `tick_late_ms` late, then five on time.
    Returns the head's fault, or None."""
    clock.now = max(clock.now, head.due) + late_ms / 1000
    head.receiver.late_ms = tick_late_ms
    try:
        head.cycle(None, clock())
        on_grid(head, clock, 5)
    except Exception:
        pass
    return head.fault


@pytest.mark.parametrize('following', [False, True])
def test_the_cycle_that_expired_on_minerva_keeps_its_command_with_a_fresh_offer(following):
    # The fault, reproduced: with the reply's offer, a cycle 10 ms late answered at a tick 13 ms late expired the
    # command before it, with Minerva's words. A fresh offer just before each command keeps it.
    head, clock = head_on_ticks(following=following, fresh_offers=False)
    try:
        assert late_cycle(head, clock, 10, tick_late_ms=13) == ROBOT_FAULT
    finally:
        head.close()
    head, clock = head_on_ticks(following=following)
    try:
        assert head.session.fresh_offers
        assert late_cycle(head, clock, 10, tick_late_ms=13) is None
        assert head.state == ('TELEOP' if following else 'HOLD')
    finally:
        head.close()


@pytest.mark.parametrize(('following', 'late_ms'), [(False, 44), (True, 34)])
def test_a_cycle_may_start_more_than_twice_as_late_as_before(following, late_ms):
    # With the reply's offer a cycle 20 ms late expired the command, in a hold and following alike. With a fresh offer
    # a hold keeps it 44 ms late, and following 34: its target's 100 ms age bounds its command's lifetime from the
    # moment it was sampled, before the offer.
    head, clock = head_on_ticks(following=following, fresh_offers=False)
    try:
        assert 'command_expired' in late_cycle(head, clock, 20)
    finally:
        head.close()
    head, clock = head_on_ticks(following=following)
    try:
        assert late_cycle(head, clock, late_ms) is None
    finally:
        head.close()


def test_a_head_stalled_past_its_commands_lifetime_still_stops():
    # Nothing is relaxed: the receiver still stops a head whose command is not renewed within its 100 ms.
    head, clock = head_on_ticks()
    try:
        fault = late_cycle(head, clock, 120)
        assert fault is not None and 'command_expired' in fault
    finally:
        head.close()


def test_each_cycle_keeps_its_timing_and_a_fault_record_keeps_the_last_ones(tmp_path):
    import json

    head, clock = head_on_ticks(directory=tmp_path)
    try:
        timing = head.timings[-1]
        # On its grid, a hold takes its fresh offer and sends its command: two exchanges, each a tick of the service.
        assert timing['late_ms'] == pytest.approx(0, abs=1) and timing['exchanges'] == 2
        assert timing['state'] == 'HOLD' and timing['failure'] is None
        assert timing['offer_ms'] == pytest.approx(TICK_MS, abs=1) and timing['rpc_ms'] == pytest.approx(TICK_MS, abs=1)
        assert timing['receiver_ms'] is not None and timing['cpu_ms'] >= 0
        assert late_cycle(head, clock, 120) is not None
        (record,) = tmp_path.glob('fault-*.json')
        recent = json.loads(record.read_text(encoding='utf-8'))['recent_cycles']
        assert recent[-1]['failure'] and recent[-1]['late_ms'] == pytest.approx(120, abs=1)
        assert len(recent) == len(head.timings) <= 250
    finally:
        head.close()


def test_restart_re_arms_a_stopped_head_where_its_receiver_holds_it():
    head, clock = head_on_ticks()
    try:
        assert late_cycle(head, clock, 120) is not None
        held = [joint['position'] for joint in head.session.controller.poll()['joints']]
        head.restart()
        assert (head.fault, head.state, head.restarts) == (None, 'HOLD', 1)
        assert list(head.session.lifecycle.target) == pytest.approx(held, abs=1e-9)  # Where it was held.
        on_grid(head, clock, 25)
        assert head.fault is None and head.state == 'HOLD'
        head.cycle('engage', clock())  # The arms' Engage (T): it follows again.
        on_grid(head, clock, 100)
        assert head.fault is None and head.state == 'TELEOP'
        with pytest.raises(ValueError, match='no fault'):
            head.restart()
    finally:
        head.close()


def test_restart_refuses_a_head_whose_receiver_is_gone_and_says_why():
    head, clock = head_on_ticks()
    try:
        head.receiver.close()  # The receiver went away: nothing holds the head.
        assert late_cycle(head, clock, 0) is not None
        with pytest.raises(ValueError):
            head.restart()
        assert ' · Restart failed: ' in head.fault and head.state == 'FAULT'
        with pytest.raises(ValueError):
            head.restart()
        assert head.fault.count(' · Restart failed: ') == 1  # A second attempt does not pile up.
    finally:
        try:
            head.close()
        except RuntimeError:
            pass  # Its receiver is already closed.


@pytest.fixture
def core(bundle):
    data, path = bundle
    direct_profile(path, 100)
    clock = Clock()
    core = TeleopCore(
        dict(data, receiver={'mode': 'virtual'}, head=head_bundle()), open_leaders=lambda _: Leaders(clock), clock=clock
    )
    core.build()
    yield core, clock
    core.close()


def stall_head(core, clock, seconds):
    """The head skips its cycles while the arms tick on, as a stuck head thread would: its command expires."""
    cycle = core.head.cycle
    core.head.cycle = lambda action, started: None
    run(core, clock, limit=round(seconds / core.period_s))
    core.head.cycle = cycle


def test_restart_head_in_a_session_re_arms_the_head_while_the_arms_hold(core):
    core, clock = core
    for key in ('I', 'E'):
        run(core, clock, key)
    run(core, clock, 'T', until='TELEOP', limit=1000)
    with pytest.raises(ValueError, match='no fault'):
        core.restart_head()
    assert core.view()['head']['restartable'] is False
    stall_head(core, clock, 0.15)
    run(core, clock, limit=20)
    assert 'command_expired' in core.head.fault and core.session.lifecycle.state == 'HOLD'
    assert 'Restart head' in core.message and core.view()['head']['restartable'] is True
    core.restart_head()
    assert core.head.fault is None and core.head.state == 'HOLD' and 're-armed' in core.message
    assert core.view()['head']['restartable'] is False
    run(core, clock, 'T', until='TELEOP', limit=1000)
    run(core, clock, limit=100)
    assert (core.session.lifecycle.state, core.head.state, core.head.fault) == ('TELEOP', 'TELEOP', None)


def test_restart_head_waits_for_the_arms_to_hold(core):
    core, clock = core
    for key in ('I', 'E'):
        run(core, clock, key)
    run(core, clock, 'T', until='TELEOP', limit=1000)
    stall_head(core, clock, 0.15)
    run(core, clock, limit=20)
    run(core, clock, 'T', until='TELEOP', limit=1000)  # The operator follows on without the head.
    assert core.head.fault and core.view()['head']['restartable'] is False
    with pytest.raises(ValueError, match='Hold the arms first'):
        core.restart_head()
    run(core, clock, 'T', until='HOLD', limit=100)
    core.restart_head()
    assert core.head.fault is None


class Stalling(Ticking):
    """A head whose service stalls once for 150 ms (the file HEAD_STALL_FLAG names, removed as it is taken): its
    ticks go on meanwhile, and the command it held expires."""

    def step(self, now_ms, request=None):
        flag = os.environ['HEAD_STALL_FLAG']
        if request is not None and os.path.exists(flag):
            os.remove(flag)
            time.sleep(0.15)
            now_ms = max(now_ms, self.inner.now_ms) + 150
            self.inner.step(now_ms)
        return super().step(now_ms, request)


def test_restart_head_reaches_a_head_in_its_own_process(bundle, tmp_path, monkeypatch):
    flag = tmp_path / 'head-stalls'
    monkeypatch.setenv('HEAD_STALL_FLAG', str(flag))
    data, path = bundle
    direct_profile(path, 100)
    core = TeleopCore(
        dict(data, receiver={'mode': 'virtual'}, head=head_bundle()),
        open_leaders=lambda _: Leaders(time.perf_counter),
        clock=time.perf_counter,
    )
    core.head.open_harness = Stalling
    core.head_process = True
    core.build()
    try:
        live(core, 'I', until=lambda c: c.head.state == 'IDLE', limit=200)
        live(core, 'E', until=lambda c: c.session.lifecycle.state == 'HOLD' and c.head.state == 'HOLD', limit=200)
        # Its word says HOLD while Enable's arm may still be on its way: a stall then stops a receiver still idle,
        # which disarms the head (limp), and no restart re-arms that (seen under the gate's load). Hold first.
        live(core, limit=30)
        flag.write_text('stall')
        live(core, until=lambda c: c.head.fault, limit=300)
        # Its 150 ms took the lease (200 ms, renewed by the hold before) or the command: either way, held.
        assert 'expired' in core.head.fault and core.view()['head']['restartable'] is True
        assert core.restart_head() == {'restarting': True}
        assert core.view()['head']['restarting'] is True
        with pytest.raises(ValueError, match='restarting'):
            core.restart_head()
        live(core, until=lambda c: not c._head_restarting, limit=300)
        assert core.head.fault is None and core.head.state == 'HOLD' and 're-armed' in core.message
        live(core, 'T', until=lambda c: c.head.state in ('ENGAGING', 'TELEOP'), limit=300)  # It takes Engage again.
        assert core.head.fault is None and core.session.lifecycle.state in ('ENGAGING', 'TELEOP')
    finally:
        core.close()
