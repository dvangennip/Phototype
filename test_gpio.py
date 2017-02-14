#!/usr/bin/python3

import os
import time
import RPi.GPIO as GPIO
import signal
from statistics import variance

# some variables to keep track of things
global do_exit

do_exit  = False

distance = 1  # in meters
past_measurements = [1]

# parameters for the low pass filter
# As k decreases, the low pass filter resolution improves but the bandwidth decreases.
acc = 0.5  # starting value
k   = 0.02

# choose BCM or BOARD numbering schemes. I use BCM
GPIO.setmode(GPIO.BCM)

# set pin to input
input_pin = 16
GPIO.setup(input_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# handle signals so we can exit
def handle_signal (signum, frame):
	global do_exit
	do_exit = True

signal.signal(signal.SIGTERM, handle_signal)  # Terminate
signal.signal(signal.SIGTSTP, handle_signal)  # Stop (^Z)
signal.signal(signal.SIGINT,  handle_signal)  # Interrupt (^C)

# helper function
def translate (value, inMin, inMax, outMin, outMax):
	# Figure out how 'wide' each range is
	inSpan = inMax - inMin
	outSpan = outMax - outMin

	# Convert the in range into a 0-1 range (float)
	valueScaled = float(value - inMin) / float(inSpan)

	# Convert the 0-1 range into a value in the out range.
	return outMin + (valueScaled * outSpan)

""" LV-MaxSonar data
	PW: This pin outputs a pulse width representation of range.
	The distance can be calculated using the scale factor of 147uS per inch.
	Range is (0.88, 37.5) in mS
"""

# begin
print('Reading from GPIO pin BCM{0}. Press ^Z, ^C, or use another signal to exit.\n'.format(input_pin))
time.sleep(1.5)

# continuously measure the input pin (albeit still too slow, so it's effectively undersampling)
while not do_exit:
	# read from input
	x = int(GPIO.input(input_pin))  # 1 or 0

	# apply IIR low pass filter (undersampling, so it requires an average)
	acc     += k * (x - acc)
	distance = translate(acc, 0, 1, 0.88, 37.5) / 0.147 * 2.51 / 100.0
	past_measurements.append(distance)
	if (len(past_measurements) > 10):
		past_measurements.pop(0)

	print('PWM: {0:.2f}\t\tDistance: {1:.2f}m\t\tVariance: {2:.2f}'.format(acc, distance, variance(past_measurements)))

	time.sleep(0.05)

GPIO.cleanup()
