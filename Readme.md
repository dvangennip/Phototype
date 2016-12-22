# Prototypes on RPi3 info

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
- pillow

**manual install:**
- python-multitouch ([https://github.com/pimoroni/python-multitouch][1])

## Backlight info
`echo n > /sys/class/backlight/rpi_backlight/brightness`
See also [https://github.com/linusg/rpi-backlight/blob/master/rpi\_backlight.py][2]

[1]:	https://github.com/pimoroni/python-multitouch
[2]:	https://github.com/linusg/rpi-backlight/blob/master/rpi_backlight.py