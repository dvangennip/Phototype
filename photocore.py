#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

import pygame
from pygame.locals import *
import serial
import sys

if (sys.platform == 'darwin'):
	from mocking import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE
else:
	from ft5406 import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE

#import os
#from subprocess import Popen


# ----- GLOBAL VARIABLES ---------------------------------------------

# 

# ----- CLASSES ---------------------------------------------------------------


class Photocore ():
	def __init__ (self):
		# init variables
		self.do_exit  = False

		# initiate all subclasses
		self.distance = DistanceSensor()
		self.input    = InputHandler(core=self)
		self.gui      = GUI(core=self)
		
		# init programs
		self.programs             = []
		self.program_active_index = 0
		self.programs.append( StatusProgram(core=self) )

		if len(self.programs) < 1:
			print('No programs to run, will exit')
			self.do_exit = True
		else:
			# begin with a program
			self.set_active(self.program_active_index)

	def update (self):
		# update self
		
		# update all subclasses
		self.distance.update()
		self.input.update()

		# update active program
		self.programs[self.program_active_index].update()

		# last, update GUI
		self.gui.update()

	def close (self):
		# close in reverse order from update
		for program in self.programs:
			program.close()

		# close subclasses
		self.gui.close()
		self.input.close()
		self.distance.close()

	""" Returns reference to active program """
	def get_active (self):
		return self.programs[self.program_active_index]

	def set_active (self, index=0):
		# set within bounds of [0,highest possible index]
		new_index = min(max(index, 0), len(self.programs)-1)

		# only switch when index has changed
		if (new_index != self.program_active_index):
			self.get_active().make_inactive()
			self.program_active_index = new_index
			self.get_active().make_active()

	def set_exit (self, state=True):
		self.do_exit = state

	def get_distance (self):
		return self.distance.get()

	def get_time (self):
		return system.time

	def set_time (self):
		pass

	def get_disk_space (self):
		# uses df command for /dev/root (mounted on /), in -human readable format
		temp = os.popen('df / -h').readline()

	def get_temperature (self):
		# update CPU temperature -----
		#   call returns CPU temperature as a character string (> temp=42.8'C)
		temp = os.popen('vcgencmd measure_temp').readline()
		self.info['cpu']['temperature'] = float(temp.replace("temp=","").replace("'C\n",""))
		pass

	def get_network_state (self):
		return ('connected', '127.0.0.1')  # TODO


class DistanceSensor ():
	def __init__ (self):
		self.distance = 10  # in meters
		# setup serial connection
		self.connection = None
		try:
			self.connection          = serial.Serial()
			self.connection.port     = '/dev/tty'
			self.connection.baudrate = 9600
			self.connection.timeout  = 1
			if (sys.platform != 'darwin'):
				self.connection.open()
			print('Serial: on ' + self.connection.name)  # check actual port used
		except:
			print('Serial: no serial connection')

	""" Read distance sensor data over serial connection """
	def update (self):
		# if incoming bytes are waiting to be read from the serial input buffer
		if (self.connection.is_open and self.connection.inWaiting()>0):
			# read the bytes and convert from binary array to ASCII
			data_str = ser.read(ser.inWaiting()).decode('ascii')
			# print the incoming string without putting a new-line ('\n') automatically after every print()
			print(data_str, end='')

			# parse data
		
			# update self.distance to new reading (moving average)
			#self.distance = temp

	def close (self):
		# close serial connection
		self.connection.close()

	""" Returns distance in meters """
	def get (self):
		return self.distance


class InputHandler ():
	def __init__ (self, core=None):
		self.core = core

		# init touchscreen
		self.ts = Touchscreen()

		for touch in self.ts.touches:
			touch.on_press   = self.touch_handler
			touch.on_release = self.touch_handler
			touch.on_move    = self.touch_handler

		self.ts.run()

	def update (self):
		# handle touchscreen events
		# incorporate outcome of handler events

		# handle pygame event queue
		events = pygame.event.get()
		for event in events:
			if (event.type is KEYDOWN):
				if (event.key == K_ESCAPE):
					self.core.set_exit(True)

	def close (self):
		self.ts.stop()

	def touch_handler(event, touch):
		touch_info = '(slot: ' + str(touch.slot) +', id: '+ str(touch.id) +', valid: '+ str(touch.valid) +', x: '+ str(touch.x) +', y: '+ str(touch.y) +')'
		if event == TS_PRESS:
			print("PRESS",   touch, touch_info)
		if event == TS_RELEASE:
			print("RELEASE", touch, touch_info)
		if event == TS_MOVE:
			print("MOVE",    touch, touch_info)


class GUI ():
	def __init__ (self, core=None):
		self.core         = core
		self.dirty        = True  # True if display should be refreshed
		self.dirty_full   = True  # True if FULL display should be refreshed
		self.dirty_areas  = []    # partial display updates can indicate pygame rectangles to redraw
		self.display_size = (800,480)

		self.colors = {
			'white':   pygame.Color(255, 255, 255),
			'black':   pygame.Color(  0,   0,   0),
			'support': pygame.Color( 60,   0,   0)
		}

		pygame.init()
		# initialise differently per platform
		if (sys.platform == 'darwin'):
			self.gui_font = pygame.font.Font('/Library/Fonts/Georgia.ttf', 16)
			self.screen = pygame.display.set_mode(self.display_size)
		else:
			pygame.mouse.set_visible(False)
			self.gui_font = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 16)
			self.screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)

	def update (self):
		# core will already request active program to update, which may set dirty flag
		# once updated, check if redraw of GUI is necessary
		if (self.dirty) is True:
			# let active program draw itself
			self.core.get_active().draw()

			# update display: partial redraw only if rectangles indicated
			if (self.dirty_full or len(self.dirty_areas) == 0):
				pygame.display.update()
			else:
				pygame.display.update(self.dirty_areas)
			
		# reset for next round
		self.dirty       = False
		self.dirty_full  = False
		self.dirty_areas = []

	def close (self):
		# close all subguis
		pass

	""" The dirty flag should be set if the GUI needs updating """
	def set_dirty (self, state=True):
		self.dirty = state


class ProgramBase ():
	def __init__ (self, core=None):
		self.core      = core
		self.gui       = core.gui
		self.is_active = False

	def update (self):
		pass

	""" code to run when program becomes active """
	def make_active (self):
		self.is_active = True

	""" code to run when this program ceases to be active """
	def make_inactive (self):
		self.is_active = False

	def close (self):
		if (self.is_active):
			self.make_inactive()

	def draw (self):
		pass


class StatusProgram (ProgramBase):
	def update (self):
		pass

	def draw (self):
		# draw distance (+plus sensor state)
		# draw network (connected, IP)
		# draw storage (% available/used)
		# draw number of photos in system
		pass


class ImageHandler ():
	def load_list (input_folder=None):
		images = []  # reset first
		for file in os.listdir(input_folder):
			if (file.endswith('.jpg')):
				images.append(file)
		images.sort()

		return images

	""" Scales 'img' to fit into box bx/by.
		This method will retain the original image's aspect ratio
	    Based on: http://www.pygame.org/pcr/transform_scale/ """
	def aspect_scale(img, box_size, fast=False):
		
		ix,iy = img.get_size()
		bx,by = box_size

		if ix > iy:
			# fit to width
			scale_factor = bx/float(ix)
			sy = scale_factor * iy
			if sy > by:
				scale_factor = by/float(iy)
				sx = scale_factor * ix
				sy = by
			else:
				sx = bx
		else:
			# fit to height
			scale_factor = by/float(iy)
			sx = scale_factor * ix
			if sx > bx:
				scale_factor = bx/float(ix)
				sx = bx
				sy = scale_factor * iy
			else:
				sy = by

		if (fast is True):
			return pygame.transform.scale(img, (int(sx), int(sy)))
		return pygame.transform.smoothscale(img, (int(sx), int(sy)))

# ----- MAIN ------------------------------------------------------------------


""" Unless this script is imported, do the following """
if __name__ == '__main__':
	# initialise all components
	core = Photocore()

	# program stays in this loop unless called for exit
	while (True):
		core.update()
		
		# exit flag set?
		if (core.do_exit):
			core.close()
			break
		else:
			# pause between frames
			pygame.time.wait(50)