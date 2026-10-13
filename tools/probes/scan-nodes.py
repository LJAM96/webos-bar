#!/usr/bin/env python3
"""Scan every input node: name + whether bitmap has 773/1198/1206/1207."""
import fcntl
import glob
import os
import re

_E = ord('E')
_IOR = lambda grp, nr, size: (2 << 30) | ((size & 0x1FFF) << 16) | ((grp & 0xFF) << 8) | (nr & 0xFF)

names = {}
try:
    txt = open('/proc/bus/input/devices').read()
    for m in re.finditer(r'N: Name="([^"]+)".*?H: Handlers=.*?(event\d+)', txt, re.S):
        names['/dev/input/' + m.group(2)] = m.group(1)
except OSError as e:
    print('devices read failed: %s' % e, flush=True)

for path in sorted(glob.glob('/dev/input/event*'), key=lambda p: int(p.split('event')[1])):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        continue
    hits = []
    for size in (96, 192):
        try:
            buf = bytearray(size)
            fcntl.ioctl(fd, _IOR(_E, 0x20 + 1, size), buf)
            bits = [i for i in range(size * 8) if (buf[i // 8] >> (i % 8)) & 1]
            for c in (773, 1198, 1206, 1207):
                if c in bits:
                    hits.append(c)
            break
        except OSError:
            continue
    os.close(fd)
    print('%-22s %-28s high-codes=%s' % (path, names.get(path, '?'), hits), flush=True)
