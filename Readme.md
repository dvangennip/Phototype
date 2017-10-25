# Phototype code
This code turns a Raspberry Pi into a suitable platform for my prototype photo viewing system (a.k.a. phototype). For testing, it may also run on macOS with the relevant python modules installed.

## Potential improvements to be made in future revisions
- Uploading photos:
	- Webpage URL should be more user-friendly: use some reverse look-up system to overcome IP issues, such that people can use a human-readable website URL.
	- Allow uploads of specific images to be cancelled (needs some optimisation in Dropzone.js).
	- The webpage may already reduce the file size before uploading, significantly reducing upload time. Ideally, all resizing is done browsers-side to capitalise on the additional processing power. Check [https://github.com/nodeca/pica][1].
- Turning on and off should be more straightforward.
- Implement a dropdown status screen, similar to iOS and Android smartphones. Thus should ease management by users.
- Redo the way the distance sensor is read. It is currently imprecise and slow, so it falls short of its intended use. If it works better, the effects of its use can be stronger.
- Test the shutdown procedure for robustness, as wonky WiFi and perhaps other factors (e.g., threads not terminating properly) can obstruct a proper shutdown and restart. This hinders automatic updating as it may brick the device.
- (bug) It appears possible for the same photo to appear next to itself in DualDisplay. Unloading then seems to cause trouble.

## Prototypes on RPi3 info
I used Raspberry Pi 3 systems but it could equally work on other hardware. Additional hardware used includes a Pi 7” Touchscreen with a proprietary way of reading touch input, so that may not translate well to other systems without changes.

## Distribution
Raspbian Jessie Lite ([use the latest image][2]). After install, updates can be run through `sudo apt-get update|upgrade`. Default login info for user `pi` is `raspberry`.

## Login
Username: pi
Password: proto-one, proto-two, etc.
Hostname: protopi1, protopi2, etc.

Adjust password via the `passwd` command. Hostname can be set via the `raspi-config` tool.

## Basic settings
Go through `raspi-config` options. First, make sure all disk space can be used. Auto-login should be enabled after setting a device name and password. SSH needs to be enabled as well.

## Dependencies to install
**via apt-get install:**
- libjpeg-dev
- python3-dev
- python3-setuptools
- python3-rpi.gpio
- python3-pygame
- python3-requests

**via pip install:**
- pip (`sudo easy_install3 -U pip`)
- [psutil][3] (`sudo pip3 install --upgrade psutil`)
- [Pillow][4]

**manual install:**
- python-multitouch ([https://github.com/pimoroni/python-multitouch][5])
- [DropzoneJS][6] (used for uploading images)

## Folder structure
The phototype code expects two additional folders to be available beside its own folder. These folders should be named `images` and `uploads`. Newly uploaded files will be placed in the latter folder and resized, adjusted, and finally moved to the former by the scanner part of `photocore.py`.

## Technical details
The text below covers several technical aspects that inform how the code functions or which additional functionality of the Raspberry Pi platform is useful to be aware of.

### Display backlight adjustments
Adjust the backlight with the following command:
`echo n > /sys/class/backlight/rpi_backlight/brightness`
See also [https://github.com/linusg/rpi-backlight/blob/master/rpi\_backlight.py][7].

Check the backlight permissions to be able to run the code.
`sudo nano /etc/udev/rules.d/backlight-permissions.rules`
Add the line:
`SUBSYSTEM=="backlight",RUN+="/bin/chmod 666 /sys/class/backlight/%k/brightness /sys/class/backlight/%k/bl_power"`

### WiFi
[By default on a RPi][8], scan available networks using
`sudo iwlist wlan0 scan`

To add a new network, open the `wpa_supplicant` file.
`sudo nano /etc/wpa_supplicant/wpa_supplicant.conf`
Add the network as follows:
	network={
	  ssid="The_ESSID"
	  psk="Your_wifi_password"
	}

Status can be checked using `sudo wpa_cli status`.

#### Using the [wifi module][9]
_Note: not installed in final version._
Use `sudo wifi scan` to find available networks. With `sudo wifi list` it shows the stored networks.

Connecting is done via `sudo wifi connect nickname SSID`. The SSID is optional and, if omitted, is guessed from the nickname.

### Bluetooth
This is not used, so it can be disabled via the `bluetoothctl` tool. Use the command `power off` to reduce power usage.

### Getting and setting date and time
Like every Debian distribution, get the time with just `date`. On boot, a RPi will attempt to use the network to set its date and time. When unavailable, it continues from the last known time. Setting is done as follows:
	sudo date --set 1998-11-02 
	sudo date --set 21:08:00

### Serial connection
_Note: not used in final version._
Before the serial (UART) connection can be used, the default terminal setup on those ports needs to be disabled ([as per online info][10]). This can be done via `rasp-config` (Disable terminal over serial). Then in `/boot/config.txt`, set `enable_uart=1`.

The default serial connection on a RPi3 is `/dev/ttyS0`. The LV-MaxSonar is connected to `3v3`, `GND`, `TX`, and `RX` [GPIO pins][11] (with the RX connected to TX on the other side and vice versa). Baud rate is 9600, with no parity, byte size of 8, and 1 stop bit. Because it runs in RS232 mode, not inverted RS232 as expected by UART, any binary signals need to be inverted.

### Running script at login
Make sure auto-login is enabled via `raspi-config`. This boots the device straight to the terminal. Second, copy the `photo core.service` file to `/lib/systemd/system/photocore.service`. Its owner should be `root` and the permissions should be adjusted to 644 (rw-r-r) using `chmod`. The permissions of the python script (`photocore.py`) also need to be adjusted to allow  the code to run with the necessary privileges. Set it to 777 (rwx-rwx-rwx), owner can remain `pi`.

Use `sudo systemctl enable|disable|start|stop|status photocore.service` to get the service going. After enabling and before starting, it’s necessary to call `sudo systemctl daemon-reload` first. A reboot may be necessary to check proper operation.

### Low voltage warnings
With less capable power adapters, the Pi may indicate that voltage drops below 4.65V with a lightning icon in the top-right of the screen. These warnings can be disabled by adding `avoid_warnings=1` to `/boot/config.txt`. Low voltage may still put the device at risk of data corruption.

### Development info
Code has to be run on the RPi itself as the screen is available there, unless the code explicitly sets `os.environ[‘SDL_VIDEODRIVER’] = ‘fbcon’` before any code uses the screen (e.g., before `pygame.init()`). In that case the code can run remotely with appropriate privileges. Still, with pygame it’s hard to get proper tracebacks when exceptions occur. To ease this, exceptions are logged in `errors.log`. Using the `tail -f errors.log` command a developer can follow once errors get appended to the file. This can of course be done via another terminal, ssh, etc.

#### Killing a python process
If all else fails, this will do:
`sudo killall -vs SIGKILL python3`

[1]:	https://github.com/nodeca/pica
[2]:	https://www.raspberrypi.org/downloads/raspbian/
[3]:	https://github.com/giampaolo/psutil/blob/master/INSTALL.rst
[4]:	http://pillow.readthedocs.io/en/latest/installation.html
[5]:	https://github.com/pimoroni/python-multitouch
[6]:	http://www.dropzonejs.com/
[7]:	https://github.com/linusg/rpi-backlight/blob/master/rpi_backlight.py
[8]:	https://www.raspberrypi.org/documentation/configuration/wireless/wireless-cli.md
[9]:	https://wifi.readthedocs.io/en/latest/wifi_command.html#tutorial
[10]:	http://elinux.org/RPi_Serial_Connection
[11]:	http://pinout.xyz/pinout/ground#