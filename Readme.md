# Phototype code
This code turns a Raspberry Pi into a suitable platform for my prototype photo viewing system (a.k.a. phototype).

## Prototypes on RPi3 info
I used Raspberry Pi 3 systems but it could equally work on other hardware. Additional hardware used includes a Pi 7” Touchscreen with a proprietary way of reading touch input, so that may not translate well to other systems without changes.

## Distribution
Raspbian Jessie Lite

## Login
Username: pi
Password: proto-one, proto-two, etc

_Adjust password via the `passwd` command._

## Packages to install
**via apt-get install:**
- git
- libjpeg-dev
- python3-dev
- python3-setuptools
- python3-serial
- python3-pygame
- python3-pip

**via pip install:**
- pillow (not used yet)
- psutil

**manual install:**
- python-multitouch ([https://github.com/pimoroni/python-multitouch][1])

## Backlight info
`echo n > /sys/class/backlight/rpi_backlight/brightness`
See also [https://github.com/linusg/rpi-backlight/blob/master/rpi\_backlight.py][2]

## Development info
Code has to be run on the RPi itself as the screen is available there. However, with pygame it’s hard to get proper tracebacks when exceptions occur. To ease this, exceptions are logged in `errors.log`. Using the `tail -f errors.log` command a developer can follow once errors get appended to the file. This can of course be done via another terminal, ssh, etc.

[1]:	https://github.com/pimoroni/python-multitouch
[2]:	https://github.com/linusg/rpi-backlight/blob/master/rpi_backlight.py