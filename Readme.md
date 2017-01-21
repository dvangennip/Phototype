# Phototype code
This code turns a Raspberry Pi into a suitable platform for my prototype photo viewing system (a.k.a. phototype). For testing, it may also run on macOS with the relevant python modules installed.

## Prototypes on RPi3 info
I used Raspberry Pi 3 systems but it could equally work on other hardware. Additional hardware used includes a Pi 7” Touchscreen with a proprietary way of reading touch input, so that may not translate well to other systems without changes.

## Distribution
Raspbian Jessie Lite (use the latest)

## Login
Username: pi
Password: proto-one, proto-two, etc

_Adjust password via the `passwd` command._

## Dependencies to install
**via apt-get install:**
- git
- libjpeg-dev
- python3-dev
- python3-setuptools
- python3-serial
- python3-pygame
- python3-pip

**via pip3 install:**
- psutil
- wifi

**manual install:**
- python-multitouch ([https://github.com/pimoroni/python-multitouch][1])
- [DropzoneJS][2] (used for uploading images)

## Display backlight adjustments
Adjust the backlight with the following command:
`echo n > /sys/class/backlight/rpi_backlight/brightness`
See also [https://github.com/linusg/rpi-backlight/blob/master/rpi\_backlight.py][3].

Check the backlight permissions to be able to run the code.
`sudo nano /etc/udev/rules.d/backlight-permissions.rules`
Add the line:
`SUBSYSTEM=="backlight",RUN+="/bin/chmod 666 /sys/class/backlight/%k/brightness /sys/class/backlight/%k/bl_power"`

## WiFi
[By default on a RPi][4], scan available networks using
`sudo iwlist wlan0 scan`

To add a new network, open the `wpa_supplicant` file.
`sudo nano /etc/wpa_supplicant/wpa_supplicant.conf`
Add the network as follows:
	network={
	ssid="The_ESSID"
	psk="Your_wifi_password"
	}

### Using the [wifi module][5]
Use `sudo wifi scan` to find available networks. With `sudo wifi list` it shows the stored networks.

Connecting is done via `sudo wifi connect nickname SSID`. The SSID is optional and, if omitted, is guessed from the nickname.

## Development info
Code has to be run on the RPi itself as the screen is available there, unless the code explicitly sets `os.environ[‘SDL_VIDEODRIVER’] = ‘fbcon’` at the start of the file. In that case the code can run remotely with appropriate privileges. Still, with pygame it’s hard to get proper tracebacks when exceptions occur. To ease this, exceptions are logged in `errors.log`. Using the `tail -f errors.log` command a developer can follow once errors get appended to the file. This can of course be done via another terminal, ssh, etc.

### Killing a python process
If all else fails, this will do:
`sudo killall -vs SIGKILL python3`

[1]:	https://github.com/pimoroni/python-multitouch
[2]:	http://www.dropzonejs.com/
[3]:	https://github.com/linusg/rpi-backlight/blob/master/rpi_backlight.py
[4]:	https://www.raspberrypi.org/documentation/configuration/wireless/wireless-cli.md
[5]:	https://wifi.readthedocs.io/en/latest/wifi_command.html#tutorial