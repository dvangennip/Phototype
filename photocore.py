#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

import os
import psutil
import pygame
from pygame.locals import *
import serial
import sys
import time
import traceback

if (sys.platform == 'darwin'):
	from mocking import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE
else:
	from ft5406 import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE

#from subprocess import Popen


# ----- GLOBAL VARIABLES ---------------------------------------------

# 

# ----- CLASSES ---------------------------------------------------------------


class Photocore ():
	def __init__ (self):
		# init variables
		self.do_exit  = False

		# initiate all subclasses
		self.display  = DisplayManager()
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
		self.display.update()
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
		self.display.close()

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

	def get_images_count (self):
		return 0  #TODO

	def set_exit (self, state=True):
		self.do_exit = state

	def get_distance (self):
		return self.distance.get()

	def get_display_brightness (self):
		return self.display.get_brightness()

	def set_display_brightness (self, brightness=100, on=True):
		pass

	def get_time (self):
		return time.strftime("%H:%M:%S  %d %B %Y", time.localtime())

	def set_time (self):
		pass

	""" Returns disk space usage in percentage """
	def get_disk_space (self):
		return psutil.disk_usage('/').percent

	def get_temperature (self):
		# update CPU temperature -----
		#   call returns CPU temperature as a character string (> temp=42.8'C)
		temp = os.popen('vcgencmd measure_temp').readline()
		return float(temp.replace("temp=","").replace("'C\n",""))

	def get_network_state (self):
		# IP: psutil.net_if_addrs()['eth0'][0].address
		# IP: psutil.net_if_addrs()['wlan0'][0].address (just some hex/MAC key if unconnected)
		# SSID via iwlist wlan0 scan?
		return ('wifi', 'unconnected')  # TODO


class DisplayManager ():
	def __init__ (self):
		self.brightness = 100
		self.is_on      = True

	def update (self):
		pass

	def close (self):
		pass

	def is_on (self):
		return self.is_on

	def get_brightness (self):
		if (self.is_on is False):
			return 0
		else:
			return self.brightness

	def set_brightness (self, brightness):
		self.brightness = brightness
		if (self.brightness == 0):
			self.is_on = False
		else:
			self.is_on = True

		# set state accordingly

class DistanceSensor ():
	def __init__ (self):
		self.distance = 9.9  # in meters
		self.distance_direction = True  # True if >, False if <
		
		# setup serial connection
		self.use_serial = False
		self.connection = None
		if (self.use_serial):
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
		if (self.use_serial):
			# if incoming bytes are waiting to be read from the serial input buffer
			if (self.connection.is_open and self.connection.inWaiting()>0):
				# read the bytes and convert from binary array to ASCII
				data_str = ser.read(ser.inWaiting()).decode('ascii')
				# print the incoming string without putting a new-line ('\n') automatically after every print()
				print(data_str, end='')

				# parse data
			
				# update self.distance to new reading (moving average)
				#self.distance = temp
		else:
			# fake the distance going up and down over time
			if (self.distance_direction is True):
				self.distance = self.distance + 0.02
				if (self.distance > 9.9):
					self.distance = 9.9
					self.distance_direction = False
			elif (self.distance_direction is False):
				self.distance = self.distance - 0.02
				if (self.distance < 0.2):
					self.distance = 0.2
					self.distance_direction = True

	def close (self):
		# close serial connection
		if (self.use_serial):
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
			'foreground': pygame.Color(255, 255, 255),  # white
			'background': pygame.Color(  0,   0,   0),  # black
			'support'   : pygame.Color(200,  15,  10),  # red
			'good'      : pygame.Color(  0, 180,  25)   # green
		}

		pygame.init()
		# initialise differently per platform
		if (sys.platform == 'darwin'):
			self.gui_font       = pygame.font.Font('/Library/Fonts/Arial.ttf', 16)
			self.gui_font_large = pygame.font.Font('/Library/Fonts/Arial.ttf', 30)
			self.screen = pygame.display.set_mode(self.display_size)
		else:
			pygame.mouse.set_visible(False)
			self.gui_font       = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 16)
			self.gui_font_large = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 30)
			self.screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)

	def update (self):
		# core will already request active program to update, which may set dirty flag
		# once updated, check if redraw of GUI is necessary
		if (self.dirty):
			if (self.dirty_full):
				self.screen.fill(self.colors['background'])
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

	""" Set to true if full update is necessary """
	def set_dirty_full (self, state=True):
		self.dirty_full = state

	def draw_rectangle (self, o='center', x=-1, y=-1, w=50, h=50, c='support'):
		xpos = self.display_size[0]/2
		if (x != -1):
			xpos = x
		ypos = self.display_size[1]/2
		if (y != -1):
			ypos = y

		rectangle_surface     = pygame.Surface( (w,h) )
		rectangle_surface.fill(self.colors[c])
		rectangle_rect        = rectangle_surface.get_rect()
		if (o == 'left'):
			rectangle_rect.topleft  = (xpos, ypos)
		elif (o == 'right'):
			rectangle_rect.topright = (xpos, ypos)
		else:  # assume center
			rectangle_rect.center   = (xpos, ypos)
		self.screen.blit(rectangle_surface, rectangle_rect)
		
		# set flags
		self.dirty = True
		self.dirty_areas.append(rectangle_rect)

		# return surface and rectangle for future reference if need be
		return (rectangle_surface, rectangle_rect)

	def draw_slider (self, o='center', x=-1, y=-1, w=100, h=20, r=.5, fg='support', bg='background'):
		xpos = self.display_size[0]/2
		if (x != -1):
			xpos = x
		ypos = self.display_size[1]/2
		if (y != -1):
			ypos = y

		# draw background rectangle (whole width)
		self.draw_rectangle(o=o, x=xpos, y=ypos, w=w, h=h, c=bg)
		
		# draw foreground rectangle (partial width)
		self.draw_rectangle(o=o, x=xpos, y=ypos, w=r*w, h=h, c=fg)

		# set flags
		self.dirty = True

	""" Helper function to draw text on screen """
	def draw_text (self, text="", o='center', x=-1, y=-1, has_back=True, padding=2, fg='foreground', bg='background', s='small'):
		xpos = self.display_size[0]/2
		if (x != -1):
			xpos = x
		ypos = self.display_size[1]/2
		if (y != -1):
			ypos = y

		text_surface = None
		if (s == 'small'):
			text_surface = self.gui_font.render(text, False, self.colors[fg])
		else:
			text_surface = self.gui_font_large.render(text, False, self.colors[fg])
		
		text_rect = text_surface.get_rect()
		if (o == 'left'):
			text_rect.topleft  = (xpos - padding, ypos - padding)
		elif (o == 'right'):
			text_rect.topright = (xpos + padding, ypos - padding)
		else:  # assume center
			text_rect.center   = (xpos, ypos)

		# draw background first
		if (has_back):
			size = text_surface.get_size()  # base background size on text surface
			size_x = size[0] + padding
			size_y = size[1] + padding
			self.draw_rectangle(o=o, x=xpos, y=ypos, w=size_x, h=size_y, c=bg)

		# finally, draw text (onto background)
		self.screen.blit(text_surface, text_rect)

		# set flags
		self.dirty = True
		self.dirty_areas.append(text_rect)

class ProgramBase ():
	def __init__ (self, core=None):
		self.core        = core
		self.gui         = core.gui
		self.is_active   = False
		self.last_update = 0  # seconds since epoch

	""" code to run every turn, needs to signal whether a gui update is needed """
	def update (self):
		# always trigger update in absence of better judgement
		self.gui.set_dirty()
		# update time since last update
		self.last_update = time.time()

	""" code to run when program becomes active """
	def make_active (self):
		self.is_active      = True
		self.gui.set_dirty_full()

	""" code to run when this program ceases to be active """
	def make_inactive (self):
		self.is_active      = False
		self.gui.dirty_full()

	def close (self):
		if (self.is_active):
			self.make_inactive()

	def draw (self):
		pass


class StatusProgram (ProgramBase):
	def update (self):
		# update every 1/4 second
		if (time.time() > self.last_update + 0.25):
			super().update()  # this call for update

	def draw (self):
		# identifier
		self.gui.draw_text("Status",      o='left', x=20, y=20, fg='support', s='large')

		# distance (+plus sensor state)
		self.gui.draw_text("Distance sensor", o='left', x=150, y=80)
		self.gui.draw_slider(o='left', x=350, y=102, w=450, h=5, r=(self.core.get_distance() / 10.0) )
		self.gui.draw_text("{0:.2f}".format(self.core.get_distance()) + "m", o='left', x=350, y=80)

		# number of photos in system
		self.gui.draw_text("Photos",      o='left', x=150, y=140)
		self.gui.draw_text(str(self.core.get_images_count()),       o='left', x=350, y=140)

		# storage (% available/used)
		self.gui.draw_text("Disk space",  o='left', x=150, y=200)
		self.gui.draw_slider(o='left', x=350, y=222, w=450, h=5, r=(self.core.get_disk_space() / 100.0), bg='good')
		self.gui.draw_text(str(self.core.get_disk_space()) + "%",         o='left', x=350, y=200)
		
		# display brightness
		self.gui.draw_text("Display brightness", o='left', x=150, y=260)
		self.gui.draw_slider(o='left', x=350, y=282, w=450, h=5, r=(self.core.get_display_brightness() / 100.0) )
		self.gui.draw_text(str(self.core.get_display_brightness()) + "%", o='left', x=350, y=260)

		# network (connected, IP)
		self.gui.draw_text("Network",     o='left', x=150, y=320)
		self.gui.draw_text(str(self.core.get_network_state()),      o='left', x=350, y=320)

		# time
		self.gui.draw_text("Time",        o='left', x=150, y=380)
		self.gui.draw_text(str(self.core.get_time()),               o='left', x=350, y=380)

		# temperature
		self.gui.draw_text("Temperature", o='left', x=150, y=440)
		self.gui.draw_text(str(self.core.get_temperature()) + "ºC", o='left', x=350, y=440)


class ImageHandler ():
	def __init__ (self):
		self.images = []

	def get_images (self):
		return self.images

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
	try:
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
	except Exception:
		f = open('errors.log', 'a')
		traceback.print_exc(file=f)  #sys.stdout
		f.close()
