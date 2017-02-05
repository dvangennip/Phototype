#!/usr/bin/python3

import serial  # install python-serial (https://pyserial.readthedocs.io/en/latest/)
import time

# for LV-MaxSonar-EZ the baud rate is 9600, 8 bits, no parity, with one stop bit.

t0 = time.time()

print('Opening serial connection')
serial_connection = serial.Serial(port="/dev/ttyS0", baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=0.5)
print(serial_connection)

while True:
	""" The output is an ASCII capital “R”, followed by three ASCII character digits
		representing the range in inches up to a maximum of 255, followed by a
		carriage return (ASCII 13). """
	response = serial_connection.read()
	print('{0} ({1})'.format(response, response.decode('utf-8')))
	time.sleep(0.5)

	# only read for n seconds
	if (time.time() > t0 + 15):
		break

serial_connection.close()
print('Closed serial connection')
