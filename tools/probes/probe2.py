#!/usr/bin/env python3
"""Validate ioctl plumbing: EVIOCGBIT on the RCU node + retry uinput variants."""
import fcntl
import os
import struct

_U = ord('U')
_E = ord('E')
_IOW = lambda grp, nr, size: (1 << 30) | ((size & 0x1FFF) << 16) | ((grp & 0xFF) << 8) | (nr & 0xFF)
_IOR = lambda grp, nr, size: (2 << 30) | ((size & 0x1FFF) << 16) | ((grp & 0xFF) << 8) | (nr & 0xFF)
print('UI_SET_EVBIT=0x%08x (expect 0x40045564)' % _IOW(_U, 100, 4), flush=True)

# EVIOCGBIT(EV_KEY=1, 96)
EVIOCGBIT_KEY = _IOR(_E, 0x20 + 1, 96)
print('EVIOCGBIT_KEY=0x%08x' % EVIOCGBIT_KEY, flush=True)
fd = os.open('/dev/input/event1', os.O_RDONLY | os.O_NONBLOCK)
buf = bytearray(96)
try:
    fcntl.ioctl(fd, EVIOCGBIT_KEY, buf)
    bits = [i for i in range(768) if (buf[i // 8] >> (i % 8)) & 1]
    print('event1 key bits: count=%d has773=%s has1206=%s max=%s' % (
        len(bits), 773 in bits, 1206 in bits,
        max([b for b in bits if b < 2000], default=None)), flush=True)
except OSError as e:
    print('EVIOCGBIT failed: %s' % e, flush=True)
os.close(fd)

# uinput variants
for label, nr, size in (('SET_EVBIT(1)', 100, 4), ('SET_KEYBIT?', 101, 4)):
    ufd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(ufd, _IOW(_U, nr, size), struct.pack('i', 1))
        print('uinput %s: OK' % label, flush=True)
    except OSError as e:
        print('uinput %s: ERRNO %d' % (label, e.errno), flush=True)
    os.close(ufd)
