"""Temporary CI diagnostic: what each gate worker holds, per test. Removed once the Linux runner's memory is explained."""

import collections
import ctypes
import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

MB = 2**20
DUMP_EVERY = 400
FOLDER = os.environ.get('RSS_PROBE_DIR')
LOG = Path(FOLDER).resolve() / 'all.jsonl' if FOLDER else None
WORKER = os.environ.get('PYTEST_XDIST_WORKER', 'main')

if os.name == 'nt':
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ('cb', wintypes.DWORD),
            ('faults', wintypes.DWORD),
            ('peak_ws', ctypes.c_size_t),
            ('ws', ctypes.c_size_t),
            ('pool_a', ctypes.c_size_t),
            ('pool_b', ctypes.c_size_t),
            ('pool_c', ctypes.c_size_t),
            ('pool_d', ctypes.c_size_t),
            ('pagefile', ctypes.c_size_t),
            ('peak_pagefile', ctypes.c_size_t),
            ('private', ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL('kernel32')
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL('psapi')
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]

    def memory():
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return {'rss': counters.ws // MB, 'anon': counters.private // MB, 'peak': counters.peak_ws // MB}

    def trim():
        return None

else:

    class MallInfo2(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_size_t)
            for name in (
                'arena',
                'ordblks',
                'smblks',
                'hblks',
                'hblkhd',
                'usmblks',
                'fsmblks',
                'uordblks',
                'fordblks',
                'keepcost',
            )
        ]

    libc = ctypes.CDLL(None)
    libc.mallinfo2.restype = MallInfo2

    def memory():
        fields = {}
        with open('/proc/self/status', encoding='ascii') as status:
            for line in status:
                key, _, value = line.partition(':')
                if key in ('VmRSS', 'VmHWM', 'RssAnon', 'VmSwap'):
                    fields[key] = int(value.split()[0]) // 1024
        info = libc.mallinfo2()
        return {
            'rss': fields['VmRSS'],
            'anon': fields['RssAnon'],
            'peak': fields['VmHWM'],
            'swap': fields.get('VmSwap', 0),
            'm_used': info.uordblks // MB,
            'm_free': info.fordblks // MB,
            'm_map': info.hblkhd // MB,
        }

    def trim():
        libc.malloc_trim(0)
        return memory()


def state():
    return {
        **memory(),
        'blocks': sys.getallocatedblocks(),
        'gc_on': gc.isenabled(),
        'frozen': gc.get_freeze_count(),
        'threads': threading.active_count(),
    }


def write(record):
    if LOG is None:
        return
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as log:
        log.write(json.dumps({'w': WORKER, **record}) + '\n')


def holdings():
    """What is still reachable: objects by type, array bytes by what holds them, and native objects by type."""
    gc.collect()
    numpy = sys.modules.get('numpy')
    kinds, arrays, native, biggest = (
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    seen = set()
    for holder in gc.get_objects():
        holder_type = type(holder)
        kinds[holder_type.__name__] += 1
        for item in gc.get_referents(holder):
            if id(item) in seen:
                continue
            seen.add(id(item))
            item_type = type(item)
            module = str(getattr(item_type, '__module__', ''))
            if module.split('.')[0] in ('mujoco', 'fcl', '_ctypes', 'ctypes', 'trimesh'):
                native[f'{module}.{item_type.__name__}'] += 1
            if numpy is not None and isinstance(item, numpy.ndarray) and item.base is None and item.nbytes >= 2**16:
                arrays[f'{holder_type.__module__}.{holder_type.__name__}'] += item.nbytes
                biggest[f'{item.shape}:{item.dtype}'] += 1
    return {
        'kinds': kinds.most_common(12),
        'array_mb': [(name, size // MB) for name, size in arrays.most_common(12)],
        'array_total_mb': sum(arrays.values()) // MB,
        'shapes': biggest.most_common(8),
        'native': native.most_common(10),
        'thread_names': collections.Counter(thread.name.split('-')[0] for thread in threading.enumerate()).most_common(
            8
        ),
    }


def dump(label):
    """A diagnostic must not change the gate's result."""
    try:
        write({'dump': label, 'state': state(), **holdings()})
    except Exception as exc:
        write({'dump': label, 'error': repr(exc)})


class Probe:
    count = 0

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(self, item):
        before, started = state(), time.monotonic()
        yield
        after = state()
        Probe.count += 1
        write({'id': item.nodeid.split('@')[0], 'dt': round(time.monotonic() - started, 2), 'b': before, 'a': after})
        if Probe.count % DUMP_EVERY == 0:
            dump(Probe.count)

    def pytest_sessionfinish(self):
        dump('end')
        write({'trimmed': trim(), 'state': state()})


def pytest_configure(config):
    if LOG is not None and not config.pluginmanager.hasplugin('rss_probe_instance'):
        config.pluginmanager.register(Probe(), 'rss_probe_instance')
