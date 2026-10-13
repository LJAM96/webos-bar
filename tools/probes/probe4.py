#!/usr/bin/env python3
"""Try legacy uinput flow: write uinput_user_dev, UI_DEV_CREATE."""
import fcntl
import os
import struct
import time

_U = ord('U')
_IO = lambda grp, nr: (0 << 30) | ((grp & 0xFF) << 8) | (nr & 0xFF)
DEV_CREATE = _IO(_U, 1)
DEV_DESTROY = _IO(_U, 2)

# struct uinput_user_dev: name[80], input_id(4H), ff u32, absmax[64]i, absmin[64]i
name = b'barwatch-probe' + b'\x00' * (80 - len('barwatch-probe'))
udev = name + struct.pack('HHHHI', 0x3, 0x1234, 0x5678, 0x1, 0)
udev += struct.pack('64i', *([0] * 64)) + struct.pack('64i', *([0] * 64))
print('struct size %d (expect 604)' % len(udev), flush=True)

fd = os.open('/dev/uinput', os.O_WRONLY)
try:
    n = os.write(fd, udev)
    print('wrote %d bytes' % n, flush=True)
except OSError as e:
    print('write: ERRNO %d' % e.errno, flush=True)
try:
    fcntl.ioctl(fd, DEV_CREATE)
    print('DEV_CREATE: OK', flush=True)
except OSError as e:
    print('DEV_CREATE: ERRNO %d' % e.errno, flush=True)
time.sleep(1)
os.system("grep -A 3 'barwatch-probe' /proc/bus/input/devices")
try:
    fcntl.ioctl(fd, DEV_DESTROY)
    print('DEV_DESTROY: OK', flush=True)
except OSError as e:
    print('DEV_DESTROY: ERRNO %d' % e.errno, flush=True)
os.close(fd)
