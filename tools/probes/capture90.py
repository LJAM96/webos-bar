#!/usr/bin/env python3
"""Capture key events for 20s so the user can press HOME (and VOL UP as reference)."""
import os, select, struct, sys, time, glob

LP = struct.calcsize('l')
EVT_FMT = 'qqHHI' if LP == 8 else 'llHHI'
EVT_SZ = struct.calcsize(EVT_FMT)
print('long size %d -> event size %d' % (LP, EVT_SZ), flush=True)

fds = []
for path in sorted(glob.glob('/dev/input/event*')):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        fds.append((path, fd))
    except OSError:
        pass
print('watching %d nodes' % len(fds), flush=True)

poll = select.poll()
for path, fd in fds:
    poll.register(fd, select.POLLIN)

seen = {}
t0 = time.time()
while time.time() - t0 < 90:
    for fd, ev in poll.poll(500):
        try:
            data = os.read(fd, EVT_SZ * 32)
        except OSError:
            continue
        for i in range(0, len(data) - EVT_SZ + 1, EVT_SZ):
            tv_s, tv_us, typ, code, val = struct.unpack(EVT_FMT, data[i:i + EVT_SZ])
            if typ == 1 and val in (0, 1, 2):
                key = (code, val)
                seen[key] = seen.get(key, 0) + 1
                print('code=%d value=%d count=%d' % (code, val, seen[key]), flush=True)

print('SUMMARY:', flush=True)
for (code, val), n in sorted(seen.items()):
    print('  code=%d value=%d x%d' % (code, val, n), flush=True)
