# Phototype
Phototype was used for a research-through-design study into the use of personal photos to stimulate serendipitous reminiscing in everyday life. Simply put, Phototype is a photo viewer that turns a Raspberry Pi 3 into a digital photo frame (with some additional features and changes). For testing, it may also run on macOS or a linux computer with the relevant python modules installed.

![Overview of parts to make Phototype work][image-1]

I used Raspberry Pi 3 systems but it could equally work on other hardware. Additional hardware used includes a Pi 7” Touchscreen with a proprietary way of reading touch input, so that may not translate well to other systems without changes.

For the Phototypes I handed out to participants, a custom shell was 3D printed to wrap the display and parts and provide a way to keep it propped up like a photo frame. This repository includes the original [Blender][1] file and a ready to print `STL` file of the casing.

Phototype runs a web server to allow the upload of photos via a user’s web browser. Initial configuration has to be done on the Pi itself, afterwards it should need little attention.

## Setting up your system

### Raspberry Pi Operating System distribution
Developed on Raspbian Jessie Lite ([use the latest image][2]). After install, updates can be run through `sudo apt-get update|upgrade`. Default login info for user `pi` is `raspberry`.

### Login
Username: pi
Password: (omitted)
Hostname: (omitted)

Adjust password via the `passwd` command. Hostname can be set via the `raspi-config` tool.

### Configuration
Go through `raspi-config` options. First, make sure all disk space can be used. Auto-login should be enabled after setting a device name and password (this allows the device to restart without need for a keyboard to login). SSH needs to be enabled as well.

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
- [QRCode][5]

**manual install:**
- python-multitouch ([https://github.com/pimoroni/python-multitouch][6])
- [DropzoneJS][7] (used for uploading images)

## Folder structure
The phototype code expects two additional folders to be available beside the `phototype` folder. These folders should be named `images` and `uploads`. Newly uploaded files will be placed in the `uploads` folder and resized, adjusted, and finally moved to the `images` folder by the scanner part of `photocore.py`.

The overall structure looks as follows:

	Phototype (root folder, goes into user folder (~))
	|
	|- casing                    (not required to run)
	|- images
	|- info                      (not required to run)
	|- phototype
	   |
	   |- assets
	   |- uploader
	   |- versions
	|- S4DataVisualiser          (not required to run)   
	|- S4DataVisualiserVertical  (not required to run)
	|- uploads

## Technical details
The text below covers several technical aspects that inform how the code functions or which additional functionality of the Raspberry Pi platform is useful to be aware of.

### Electrical wiring
The schematic below corresponds to the versions of the circuit boards that were used in this project. Future hardware may alter things, so check before connecting. The BCM16 input is referenced in the code, so when changing to another pin the code should be updated accordingly.

![Connecting the Pi to the touchscreen and sensor][image-2]

### Running the code
Navigate to the photocore directory and run
`sudo python3 photocore.py`

### Display backlight adjustments
Adjust the backlight with the following command:
`echo n > /sys/class/backlight/rpi_backlight/brightness`
See also [rpi-backlight documentation][8].

Check the backlight permissions to be able to run the code.
`sudo nano /etc/udev/rules.d/backlight-permissions.rules`

Add the line:
`SUBSYSTEM=="backlight",RUN+="/bin/chmod 666 /sys/class/backlight/%k/brightness /sys/class/backlight/%k/bl_power"`

The `photocore.py` script makes use of the above methods to automatically adjust the display brightness throughout the day.

### WiFi
[By default on a RPi][9], scan available networks using
`sudo iwlist wlan0 scan`

To add a new network, open the `wpa_supplicant` file.
`sudo nano /etc/wpa_supplicant/wpa_supplicant.conf`

Add a network as follows:

	network={
	  ssid="The_ESSID"
	  psk="Your_wifi_password"
	}

Status can be checked using `sudo wpa_cli status`.

#### Using the [wifi module][10]
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
Before the serial (UART) connection can be used, the default terminal setup on those ports needs to be disabled ([as per online info][11]). This can be done via `rasp-config` (Disable terminal over serial). Then in `/boot/config.txt`, set `enable_uart=1`.

The default serial connection on a RPi3 is `/dev/ttyS0`. The LV-MaxSonar is connected to `3v3`, `GND`, `TX`, and `RX` [GPIO pins][12] (with the RX connected to TX on the other side and vice versa). Baud rate is 9600, with no parity, byte size of 8, and 1 stop bit. Because it runs in RS232 mode, not inverted RS232 as expected by UART, any binary signals need to be inverted.

### Running script at login
Make sure auto-login is enabled via `raspi-config`. This boots the device straight to the terminal. Second, copy the `photo core.service` file to `/lib/systemd/system/photocore.service`. Its owner should be `root` and the permissions should be adjusted to 644 (rw-r-r) using `chmod`. The permissions of the python script (`photocore.py`) also need to be adjusted to allow  the code to run with the necessary privileges. Set it to 777 (rwx-rwx-rwx), owner can remain `pi`.

Use `sudo systemctl enable|disable|start|stop|status photocore.service` to get the service going. After enabling and before starting, it’s necessary to call `sudo systemctl daemon-reload` first. A reboot may be necessary to check proper operation.

To be able to set up things on the device without it continuously attempting to take over the screen, placing a file named `nostart.txt` into the `phototype` folder prevents `photocore.py` from running (it exists when it finds that file). Create such a file with `echo 'some text' > nostart.txt`

Removing the file with `rm nostart.txt` allows the code to run as intended.

### Low voltage warnings
With less capable power adapters, the RPi may indicate that voltage drops below 4.65V with a lightning icon in the top-right of the screen. These warnings can be disabled by adding `avoid_warnings=1` to `/boot/config.txt`. Low voltage may still put the device at risk of data corruption.

### Development info
Code has to be run on the RPi itself as the screen is available there, unless the code explicitly sets `os.environ[‘SDL_VIDEODRIVER’] = ‘fbcon’` before any code uses the screen (e.g., before `pygame.init()`). In that case the code can run remotely with appropriate privileges. Still, with pygame it’s hard to get proper tracebacks when exceptions occur. To ease this, exceptions are logged in `errors.log`. Using the `tail -f errors.log` command a developer can follow once errors get appended to the file. This can of course be done via another terminal, ssh, etc.

#### Killing a python process
If all else fails, this will do:
`sudo killall -vs SIGKILL python3`

## Visualising data
Phototype keeps track of user interactions with the device. This data is saved in `data.bin` and human-readable `data.log` files in the `phototype` folder (available when the script has run at least once). These files are not directly suitable for visual analysis. To help with this, a `visualiser.py` script prepares the data to be importing and visualised by a [Processing.py][13] script. Two scripts are included in the `S4DataVisualiser` folders.

The visualiser scripts expect that user data is provided in unique files, each named `pN_data.bin` (where N denotes a participant number, e.g., p1 or p2).

## License
The source code and models are available under a [CC-BY-NC 3.0 license][14]. You are free to share, copy and redistribute the material in any medium or format, and to adapt it for other uses. However, you must give credit and cannot use the code and materials for commercial purposes.

Note that [DropzoneJS][15] files are included in this repository for convenience but remain under the original MIT license.

Icons on the status pane by [hirschwolf][16] and [Freepik][17] from Flaticon are included in this repository for convenience but remain under the original Flaticon Basic license.

## Known issues and possible improvements for future revisions
- Uploading photos:
	- Webpage URL should be more user-friendly: use some reverse look-up system to overcome IP issues, such that people can use a human-readable website URL. Alternatively, work with a scannable QR code to ease navigating to the right url on another device.
- Turning on and off should be more straightforward (currently relies on a hidden button in the bottom-left corner of the status screen).
- Implement a dropdown status screen, similar to iOS and Android smartphones. This should ease management by users.
- Redo the way the distance sensor is read. It is currently imprecise and slow, so it falls short of its intended use. If it works better, the effects of its use can be stronger.
- Test the shutdown procedure for robustness, as wonky WiFi and perhaps other factors (e.g., threads not terminating properly) can obstruct a proper shutdown and restart. This hinders automatic updating as it may lock the device into a non-functional state.
- (bug) It appears possible for the same photo to appear next to itself in both modes. The image unloading routine then seems to cause trouble.

[1]:	https://www.blender.org/
[2]:	https://www.raspberrypi.org/downloads/raspbian/
[3]:	https://github.com/giampaolo/psutil/blob/master/INSTALL.rst
[4]:	http://pillow.readthedocs.io/en/latest/installation.html
[5]:	https://pypi.org/project/qrcode/
[6]:	https://github.com/pimoroni/python-multitouch
[7]:	http://www.dropzonejs.com/
[8]:	https://github.com/linusg/rpi-backlight/blob/master/rpi_backlight.py
[9]:	https://www.raspberrypi.org/documentation/configuration/wireless/wireless-cli.md
[10]:	https://wifi.readthedocs.io/en/latest/wifi_command.html#tutorial
[11]:	http://elinux.org/RPi_Serial_Connection
[12]:	http://pinout.xyz/pinout/ground#
[13]:	http://py.processing.org/
[14]:	https://creativecommons.org/licenses/by-nc/3.0/au/
[15]:	http://www.dropzonejs.com/
[16]:	https://www.flaticon.com/authors/hirschwolf
[17]:	https://www.flaticon.com/authors/freepik

[image-1]:	info/phototype-overview.png
[image-2]:	info/wiring-schematic.png