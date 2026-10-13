#!/usr/bin/env python3
"""Probe: can uinput mirror LG-proprietary high key codes (773, 1198, 1206)?"""
import fcntl
import os
import struct
import errno

_U = ord('U')
_IOW = lambda grp, nr, size: (1 << 30) | ((size & 0x1FFF) << 16) | ((grp & 0xFF) << 8) | (nr & 0xFF)
_IO = lambda grp, nr: (0 << 30) | ((grp & 0xFF) << 8) | (nr & 0xFF)
UI_SET_EVBIT = _IOW(_U, 100, 4)
UI_SET_KEYBIT = _IOW(_U, 101, 4)

EV_KEY = 1


def try_key(fd, code):
    try:
        fcntl.ioctl(fd, UI_SET_KEYBIT, struct.pack('i', code))
        return 'OK'
    except OSError as e:
        return 'ERRNO %d (%s)' % (e.errno, errno.errorcode.get(e.errno, '?'))


fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
print('uinput opened', flush=True)
fcntl.ioctl(fd, UI_SET_EVBIT, struct.pack('i', EV_KEY))
for code in (28, 105, 108, 412, 767, 768, 773, 1140, 1198, 1206, 1207):
    print('keybit %d: %s' % (code, try_key(fd, code)), flush=True)
os.close(fd)
