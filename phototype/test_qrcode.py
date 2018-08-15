#!/usr/bin/python3
# coding: utf-8

import qrcode
import psutil
import sys

# Querying network IP

net_type = 'wlan0'
if (sys.platform == 'darwin'):
	net_type = 'en0'

net_state = psutil.net_if_addrs()
ip = net_state[net_type][0].address

print(net_state)
print(ip)

# QRcode generation

qr = qrcode.QRCode(
	version=None,
	error_correction=qrcode.constants.ERROR_CORRECT_L,
	box_size=5,  # was 8
	border=4     # 4 is desired
)
qr.add_data('http://' + ip)
qr.make(fit=True)

img = qr.make_image(fill_color="white", back_color="black")
img.save('test_qrcode.png')
