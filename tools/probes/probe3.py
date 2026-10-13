#!/usr/bin/env python3
"""uinput open-mode/ioctl matrix."""
import fcntl
import os
import struct

_U = ord('U')
_IOW = lambda grp, nr, size: (1 << 30) | ((size & 0x1FFF) << 16) | ((grp & 0xFF) << 8) | (nr & 0xFF)
_IO = lambda grp, nr: (0 << 30) | ((grp & 0xFF) << 8) | (nr & 0xFF)
SET_EV = _IOW(_U, 100, 4)
DEV_CREATE = _IO(_U, 1)

for label, flags in (('WRONLY', os.O_WRONLY), ('RDWR', os.O_RDWR),
                     ('WRONLY|NONBLOCK', os.O_WRONLY | os.O_NONBLOCK)):
    try:
        fd = os.open('/dev/uinput', flags)
    except OSError as e:
        print('%s open: ERRNO %d' % (label, e.errno), flush=True)
        continue
    try:
        fcntl.ioctl(fd, SET_EV, struct.pack('i', 1))
        print('%s SET_EVBIT(EV_KEY): OK' % label, flush=True)
    except OSError as e:
        print('%s SET_EVBIT(EV_KEY): ERRNO %d' % (label, e.errno), flush=True)
    try:
        fcntl.ioctl(fd, SET_EV, bytearray(struct.pack('i', 1)))
        print('%s SET_EVBIT mutable: OK' % label, flush=True)
    except OSError as e:
        print('%s SET_EVBIT mutable: ERRNO %d' % (label, e.errno), flush=True)
    os.close(fd)
