#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

import os
import pickle
import psutil
import pygame
from pygame.locals import *
import random
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
		self.is_debug = True

		# initiate all subclasses
		self.data     = DataManager(core=self)
		self.network  = NetworkManager()
		self.display  = DisplayManager()
		self.distance = DistanceSensor()
		self.images   = ImageManager('../DCIM', core=self)
		self.gui      = GUI(core=self)
		self.input    = InputHandler(core=self)
		
		# init programs
		self.programs                = []
		self.program_active_index    = 0
		self.program_preferred_index = 0
		self.programs.append( StatusProgram(core=self) )
		self.programs.append( DualDisplay(core=self) )
		self.programs.append( PhotoSoup(core=self) )

		if len(self.programs) < 1:
			print('No programs to run, will exit')
			self.do_exit = True
		else:
			# begin with a program
			self.set_active(self.program_active_index)

	def update (self):
		# update self
		
		# update all subclasses
		self.data.update()
		self.network.update()
		self.display.update()
		self.distance.update()
		self.input.update()
		self.images.update()

		# decide on active program
		if (self.program_preferred_index != self.program_active_index):
			self.set_active(self.program_preferred_index)

		# update active program
		self.programs[self.program_active_index].update()

		# last, update GUI
		self.gui.update()

	def close (self):
		# close in reverse order from update
		for program in self.programs:
			program.close()

		# close subclasses
		self.data.close()
		self.gui.close()
		self.images.close()
		self.input.close()
		self.distance.close()
		self.display.close()
		self.network.close()

	""" Returns reference to active program """
	def get_active (self):
		return self.programs[self.program_active_index]

	def set_active (self, index=0):
		# set within bounds of [0,highest possible index]
		new_index = min(max(index, 0), len(self.programs)-1)

		# only switch when index has changed
		if (new_index != self.program_active_index):
			self.get_active().make_inactive()
			self.program_active_index    = new_index
			self.program_preferred_index = new_index
			self.get_active().make_active()

	def set_preferred (self, index=0):
		self.program_preferred_index = index

	def get_images_count (self):
		return self.images.get_count()

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
		if (sys.platform == 'darwin'):
			return 0
		else:
			# update CPU temperature -----
			#   call returns CPU temperature as a character string (> temp=42.8'C)
			temp = os.popen('vcgencmd measure_temp').readline()
			return float(temp.replace("temp=","").replace("'C\n",""))

	def get_network_state (self):
		return self.network.get_state_summary()


class DataManager ():
	def __init__ (self, core=None):
		self.core  = core
		self.data  = {
			'log': [],
			'images': []
		}
		self.dirty     = False
		self.last_save = 0  # timestamp
		self.min_time_between_saves = 120  # avoid excessive writing to disk

		try:
			with open('data.bin', 'rb') as f:
				self.data = pickle.load(f)
		except IOError as eio:
			pass  # called when file doesn't exist (yet), which is fine
		except Exception as e:
			raise e

	def update (self):
		if (self.dirty and self.last_save < time.time() - self.min_time_between_saves):
			self.data['images'] = self.core.images.images  # reference to a list
			self.save()
			self.dirty = False

	def close (self):
		self.save(export=True)

	def set_dirty (self, message=None):
		if (message is not None):
			t = time.strftime("%Y-%M-%d %H:%M:%S - ", time.localtime())
			self.data['log'].append(t + message)
		self.dirty = True

	def save (self, export=False):
		# regular save
		with open('data.bin', 'wb') as f:
			pickle.dump(self.data, f)
			self.last_save = time.time()

		# export to human-readable file
		if (export):
			with open('data.log', 'w') as f:
				f.write('LOG\n-----------------\n')
				for log in self.data['log']:
					f.write(log + '\n')

				f.write('\nIMAGES\n-----------------\n')
				for img in self.data['images']:
					f.write(str(img) + '\n')

	""" Return a matching image based on file path """
	def get_match (self, file_path):
		for img in self.data['images']:
			if (img.file == file_path):
				return img
		# without a match
		return None


class NetworkManager ():
	def __init__ (self):
		self.net_types = ('eth0','wlan0')
		if (sys.platform == 'darwin'):
			self.net_types = ('en0','en1')

		self.state = {
			self.net_types[0]: {
				'connected': False,
				'ip'       : ''
			},
			self.net_types[1]: {
				'connected': False,
				'network'  : 'SSID',  # SSID
				'security' : '',      # WPA, etc.
				'ip'       : ''
			}
		}

	def update (self, regular=True):
		if (regular):
			pass  # no need to update all the time
		else:
			# update network state
			net_state = psutil.net_if_addrs()

			for net in self.net_types:
				ip      = net_state[net][0].address
				netmask = net_state[net][0].netmask
				# check 'symptoms' to deduce network status
				if ('.' in ip and netmask is not None):
					self.state[net]['connected'] = True
					self.state[net]['ip']        = ip
				else:
					self.state[net]['connected'] = False
					self.state[net]['ip']        = ''

	def close (self):
		pass

	def get_networks (self):
		wifi_network_list = []
		# SSID via `sudo iwlist wlan0 scan`
		return wifi_network_list

	def connect (self, wifi_network=None):
		pass

	def is_connected (self):
		if (self.state[self.net_types[0]]['connected'] or self.state[self.net_types[1]]['connected']):
			return True
		return False

	def get_state_summary (self):
		# first, force an update
		self.update(False)

		# generate a one line summary
		summary = ''
		if (self.state[self.net_types[1]]['connected']):
			summary = summary + "WiFi ({0[network]}, {0[ip]})".format(self.state[self.net_types[1]])
		else:
			summary = summary + "WiFi (unconnected)"
		if (self.state[self.net_types[0]]['connected']):
			summary = summary + ", Ethernet ({0[ip]})".format(self.state[self.net_types[0]])
		else:
			summary = summary + ", Ethernet (unconnected)"
		return summary


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
		self.distance = 6.5  # in meters
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
				if (self.distance > 6.5):
					self.distance = 6.5
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


class ImageManager ():
	def __init__ (self, input_folder='', core=None):
		self.core         = core
		self.images       = []
		self.recent       = []
		self.input_folder = input_folder
		self.load_list(self.input_folder)

	def update (self):
		pass

	def close (self):
		self.images = []  # reset to severe memory links

	def load_list (self, input_folder=None):
		for dirname, dirnames, filenames in os.walk(input_folder):
			# editing 'dirnames' list will stop os.walk() from recursing into there
			if '.git' in dirnames:
				dirnames.remove('.git')
			if '.DS_Store' in filenames:
				filenames.remove('.DS_Store')

			# check all filenames, act on valid ones
			for filename in filenames:
				if filename.endswith(('.jpg', '.jpeg')):
					file_path = os.path.join(dirname, filename)
					self.append(file_path)

	def append (self, file_path):
		# check if file_path is already in list
		duplicate = False

		for image in self.images:
			if (image.file == file_path):
				duplicate = True

		# if new, append the list
		if (duplicate == False):
			p = Image(file_path)
			# also check if data is available on this image
			file_match = self.core.data.get_match(file_path)
			if (file_match is not None):
				p.set_shown(file_match.shown)
				p.set_rate(file_match.rate)
			# add to list
			self.images.append(p)

	def get_images (self):
		return self.images

	def get_random (self):
		return self.images[ random.randint(0, len(self.images)-1) ]

	""" Returns an image and checks if it's not similar to recent images returned """
	def get_next (self):
		# get an image to return, and make sure it wasn't returned recently
		unique = False
		while not unique:
			img = self.get_random()
			if (img.file not in self.recent):
				unique = True
		
		# keep track of which image gets returned
		self.recent.append(img.file)
		# make sure the tracking is limited to avoid images not returning any time soon
		if (len(self.recent) > 10):
			self.recent.pop(0)  # remove first (oldest) element in list

		return img


	def get_count (self):
		return len(self.images)


class Image ():
	def __init__ (self, file=None, shown=[], rate=0):
		self.file      = file
		self.image     = {
			'full' : None,  # only load when necessary
			'thumb': None   # idem
		}
		self.size      = (0,0)  # pixels x,y
		self.is_loaded = False

		self.rate      = rate   # default is 0, range is [-1, 1]
		self.shown     = list(shown)  # list, each item denotes for how long image has been shown

	def get (self, size, fit_to_square=False, smooth=True):
		# load if necessary
		if (self.is_loaded is False):
			self.load()

		# check the required size and make it available
		if (size == 'thumb'):
			if (self.image['thumb'] is None):
				self.image['thumb'] = self.scale((100,100), True, smooth)
		elif (size[0] < self.size[0] or size[1] < self.size[1]):
				size_string = str(size[0]) + 'x' + str(size[1])
				# check if this resizing is cached already
				if (size_string in self.image):
					return self.image[size_string]
				else:
					# scale and keep for future use
					img = self.scale(size, fit_to_square, smooth)
					self.image[size_string] = img
					return img
		# without resize
		return self.image['full']

	def load (self):
		# load image
		self.image['full'] = pygame.image.load(self.file)
		self.size          = self.image['full'].get_size()
		self.is_loaded = True

	""" Free up memory by unloading an image no longer needed """
	def unload (self):
		self.is_loaded = False

		# set image to None if a default size
		# or delete if non-default
		sizes_to_delete = []
		for s in self.image:
			if (s == 'full' or s == 'thumb'):
				self.image[s] = None
			else:
				sizes_to_delete.append(s)
		# finally, delete sizes (separate loop avoids dict size changes during iteration)
		for sd in sizes_to_delete:
			del self.image[sd]

	""" Scales 'img' to fit into box bx/by.
		This method will retain the original image's aspect ratio
	    Based on: http://www.pygame.org/pcr/transform_scale/ """
	def scale (self, box_size, fit_to_square=False, smooth=True):
		ix,iy = self.image['full'].get_size()
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
		#print('scaling', box_size, '->', (sx, sy), self.file)

		scaled_img = None

		if (smooth is True):
			scaled_img = pygame.transform.smoothscale(self.image['full'], (int(sx), int(sy)))
		else:
			scaled_img = pygame.transform.scale(self.image['full'], (int(sx), int(sy)))
		
		# a to-be-squared image will get the excess part taken off
		if (fit_to_square and sx != sy):
			s_left, s_top, s_width, s_height = 0, 0, sx, sy
			if (sx > sy):
				s_width = sy
				s_left  = (sx - sy) / 2  # making sure we get the middle
			else:
				s_height = sx
				s_top    = (sy - sx) / 2
			scaled_img = scaled_img.subsurface( Rect(s_left, s_top, s_width, s_height) )

		return scaled_img

	""" Up or downvotes an image """
	def do_rate (self, positive=True, delta=0.1):
		if (positive):
			self.rate += delta
		else:
			self.rate -= delta
		# limit to [-1,1] range
		self.rate = max(min(self.rate, 1), 0)

		return self.rate

	def set_rate (self, rate=0):
		self.rate = rate

	""" Adds viewings of this image to a list """
	def was_shown (self, time=0):
		if (time > 0):
			self.shown.append(int(time))  # no need for more precision than int

	def set_shown (self, shown=[]):
		self.shown = list(shown)  # avoids referencing to inbound list object

	""" Gives a default str(this instance) output """
	def __str__ (self):
		return self.file + '; rate: ' + str(self.rate) + '; shown: ' + str(self.shown)


class InputHandler ():
	def __init__ (self, core=None):
		self.core = core

		# set up pygame events (block those of no interest to keep sanity/memory)
		# types kept: QUIT, KEYDOWN, KEYUP, MOUSEMOTION, MOUSEBUTTONDOWN, MOUSEBUTTONUP
		pygame.event.set_blocked(ACTIVEEVENT)
		pygame.event.set_blocked(JOYAXISMOTION)
		pygame.event.set_blocked(JOYBALLMOTION)
		pygame.event.set_blocked(JOYHATMOTION)
		pygame.event.set_blocked(JOYBUTTONUP)
		pygame.event.set_blocked(JOYBUTTONDOWN)
		pygame.event.set_blocked(VIDEORESIZE)
		pygame.event.set_blocked(VIDEOEXPOSE)
		pygame.event.set_blocked(USEREVENT)

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

		# for a mock run, send events also to touchscreen module
		# (as pygame events cannot be taken from its queue twice)
		if (sys.platform == 'darwin'):
			self.ts.add_events(events)

		# handle pygame events
		for event in events:
			if (event.type is QUIT):
				self.core.set_exit(True)
			elif (event.type is KEYDOWN):
				if (event.key == K_ESCAPE):
					self.core.set_exit(True)
				elif (event.key >= 48 and event.key <= 57):
					self.core.set_preferred(event.key - 48)  # adjust range [0-9]

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
			self.gui_font       = pygame.font.Font('/Library/Fonts/Arial Bold.ttf', 16)
			self.gui_font_large = pygame.font.Font('/Library/Fonts/Arial Bold.ttf', 30)
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

			# also call default draw function
			self.draw()

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
		pygame.quit()

	""" The dirty flag should be set if the GUI needs updating """
	def set_dirty (self, state=True):
		self.dirty = state

	""" Set to true if full update is necessary """
	def set_dirty_full (self, state=True):
		self.set_dirty()
		self.dirty_full = state

	""" Default draw function can be used for overlays, etc. """
	def draw (self):
		# for testing only
		if (self.dirty is True and self.core.is_debug):
			self.draw_slider(o='left', x=0, y=0, w=800, h=3, r=(self.core.get_distance() / 6.5))

	def draw_rectangle (self, o='center', x=-1, y=-1, w=50, h=50, c='support', a=1, r=True):
		xpos = self.display_size[0]/2
		if (x != -1):
			if (r):
				xpos = x * self.display_size[0]
			else:
				xpos = x
		ypos = self.display_size[1]/2
		if (y != -1):
			if (r):
				ypos = y * self.display_size[1]
			else:
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

		# set alpha
		rectangle_surface.set_alpha(min(max(a*255,0),255))

		self.screen.blit(rectangle_surface, rectangle_rect)
		
		# set flags
		self.dirty = True
		self.dirty_areas.append(rectangle_rect)

		# return surface and rectangle for future reference if need be
		return (rectangle_surface, rectangle_rect)

	def draw_slider (self, o='center', x=-1, y=-1, w=100, h=20, r=.5, fg='support', bg='background', a=1):
		xpos = self.display_size[0]/2
		if (x != -1):
			xpos = x
		ypos = self.display_size[1]/2
		if (y != -1):
			ypos = y

		# draw background rectangle (whole width)
		self.draw_rectangle(o=o, x=xpos, y=ypos, w=w, h=h, c=bg, a=a, r=False)
		
		# draw foreground rectangle (partial width)
		self.draw_rectangle(o=o, x=xpos, y=ypos, w=r*w, h=h, c=fg, a=a, r=False)

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
			text_surface = self.gui_font.render(text, True, self.colors[fg])
		else:
			text_surface = self.gui_font_large.render(text, True, self.colors[fg])
		
		text_rect = text_surface.get_rect()
		if (o == 'left'):
			text_rect.topleft  = (xpos, ypos)
		elif (o == 'right'):
			text_rect.topright = (xpos, ypos)
		else:  # assume center
			text_rect.center   = (xpos, ypos)

		# draw background first
		if (has_back):
			size   = text_surface.get_size()  # base background size on text surface
			size_x = size[0] + padding
			size_y = size[1] + padding
			pos_x  = xpos
			pos_y  = ypos
			if (o == 'left'):
				pos_x = xpos - padding
				pos_y = ypos - padding
			elif (o == 'right'):
				pos_x = xpos + padding
				pos_y = ypos - padding
			self.draw_rectangle(o=o, x=pos_x, y=pos_y, w=size_x, h=size_y, c=bg, r=False)

		# finally, draw text (onto background)
		self.screen.blit(text_surface, text_rect)

		# set flags
		self.dirty = True
		self.dirty_areas.append(text_rect)

	def draw_image (self, img=None, o='center', pos=(0.5,0.5), size=(1,1), mask=None, a=1, sq=False):
		# decide on place and size
		img_size = (size[0] * self.display_size[0], size[1] * self.display_size[1])
		# get image (resized)
		img_scaled = img.get(img_size, sq)

		# determine position
		xpos = int(pos[0] * self.display_size[0])
		ypos = int(pos[1] * self.display_size[1])
		if (o == 'center'):
			xpos = xpos - img_scaled.get_width() / 2
			ypos = ypos - img_scaled.get_height() / 2

		# set alpha (always set, to avoid remnant settings causing trouble)
		img_scaled.set_alpha(min(max(a*255,0),255))

		# draw to screen
		#print('draw_image', xpos, ypos, img_scaled.get_size())
		affected_rect = None
		if (mask == None):
			affected_rect = self.screen.blit(img_scaled, (xpos, ypos))
		else:
			# limit the blitting to a particular mask
			# default mask is (0,1,0,1) -> (x begin, x end, y begin, y end)
			left   = mask[0] * self.display_size[0]
			top    = mask[2] * self.display_size[1]
			width  = (mask[1] - mask[0]) * self.display_size[0]
			height = (mask[3] - mask[2]) * self.display_size[1]
			if (xpos < 0):
				left  -= xpos
				#width -= xpos
				xpos = 0
			elif (left > 0 and xpos > 0):
				left -= xpos
				xpos += left
			if (ypos < 0):
				top    -= ypos
				#height -= ypos
				ypos = 0
			elif (top > 0 and ypos > 0):
				top  -= ypos
				ypos += top

			mask_rect = Rect(left, top, width, height)
			#print('mask: ', left, top, width, height, 'x:', xpos,'y:', ypos)
			affected_rect = self.screen.blit(img_scaled, (xpos, ypos), area=mask_rect)
		
		# set flags
		self.dirty = True
		self.dirty_areas.append(affected_rect)


class ProgramBase ():
	def __init__ (self, core=None):
		self.core        = core
		self.gui         = core.gui
		self.is_active   = False
		self.last_update = 0  # seconds since epoch
		self.first_run   = True

	""" code to run every turn, needs to signal whether a gui update is needed """
	def update (self, full=False):
		# always trigger update in absence of better judgement
		if (full):
			self.gui.set_dirty_full()
		else:
			self.gui.set_dirty()
		# update time since last update
		self.last_update = time.time()
		# set other variables
		if (self.first_run):
			self.first_run = False

	""" code to run when program becomes active """
	def make_active (self):
		self.is_active = True
		self.first_run = True
		self.gui.set_dirty_full()

	""" code to run when this program ceases to be active """
	def make_inactive (self):
		self.is_active = False
		self.first_run = True
		self.gui.set_dirty_full()

	def close (self):
		if (self.is_active):
			self.make_inactive()

	def draw (self):
		pass


class StatusProgram (ProgramBase):
	def update (self):
		# update every 1/4 second
		if (time.time() > self.last_update + 0.25):
			super().update()  # this calls for update

	def draw (self):
		# identifier
		self.gui.draw_text("Status",      o='left', x=20, y=20, fg='support', s='large')

		# distance (+plus sensor state)
		self.gui.draw_text("Distance sensor", o='left', x=150, y=80)
		self.gui.draw_slider(o='left', x=350, y=102, w=450, h=5, r=(self.core.get_distance() / 6.5) )
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


class DualDisplay (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)
		
		self.default_time    = 10
		self.switch_time     = 2

		self.im = [
			{  # one
				'image'    : None,
				'image_new': None,
				'alpha'    : 0,
				'since'    : 0,
				'max_time' : self.default_time,
				'swap'     : False
			},
			{  # two
				'image'    : None,
				'image_new': None,
				'alpha'    : 0,
				'since'    : 0,
				'max_time' : self.default_time,
				'swap'     : False
			}
		]

		self.line_pos        = 0.5
		self.line_width      = 0
		self.picker_pos      = 0.5
		self.picker_alpha    = 1

	def update (self):
		dirty = False
		now = time.time()

		# pick position of line and picker, based on input
		# if user drag action started on picker, drag it and let line follow
		# else, if drag action started elsewhere move the line but leave the picker at its resting position
		#self.picker_pos = 0.5
		#self.line_pos = 0.5

		# if user indicates a clear preference, go with that
		# this means a drag of the picker crosses a threshold (position away from centre)
		if (self.picker_pos < 0.3 or self.picker_pos > 0.8):
			# set up for that
			preferred_image = round(self.picker_pos)  # 0 or 1, if picker > 0.5
			# rate both images
			self.im[0].rate(preferred_image == 0)  # True if picker is far left, False otherwise
			self.im[1].rate(preferred_image == 1)  # vice versa, True if far right
			self.core.data.set_dirty()
			# give feedback (both for rating, and swap)
			# get one image to fade quickly and swap over
			self.im[ abs(preferred_image - 1) ]['swap'] = True
			# reset drag of picker (let it go back to default to avoid continued rating for a next duel)

		# decide if line should be shown
		new_line_width = max(min(25 / pow(self.core.get_distance() + 0.5, 3), 10), 0)
		if (new_line_width < 0.8):  # no need to consider smaller than this
			new_line_width = 0
		if (new_line_width != self.line_width):  # only update when necessary
			self.line_width = new_line_width
			dirty = True
		
		# decide if picker should be shown
		new_picker_alpha = max(min(-10/3 * self.core.get_distance() + 8/3, 1), 0)
		if (new_picker_alpha < .004):  # no need to consider smaller than this
			new_picker_alpha = 0
		if (new_picker_alpha != self.picker_alpha):
			self.picker_alpha = new_picker_alpha
			dirty = True

		# loop over two image slots to assign, swap, fade, etc.
		for index, i in enumerate(self.im):
			if (self.first_run):
				# make sure there is an image
				i['image']     = self.core.images.get_next()
				i['image_new'] = self.core.images.get_next()
				i['since']     = now
				if (index == 1):
					i['max_time'] *= 1.5

			# if an image has been on long enough, swap over
			if (i['swap'] or i['since'] < now - i['max_time'] + self.switch_time):
				# set alpha for new image fade-in
				i['alpha'] = max(min((now - (i['since'] + i['max_time'] - self.switch_time)) / self.switch_time, 1), 0)

				# once time for current image is up, switch over
				if (i['swap'] or i['since'] < now - i['max_time']):
					# unload current image
					if (i['image'] is not None):
						i['image'].was_shown(now - i['since'])  # report time since it appeared
						self.core.data.set_dirty()
						i['image'].unload()  # free memory
					
					# reassign and reset timers, etc.
					i['swap']      = False
					i['image']     = i['image_new']
					i['image_new'] = self.core.images.get_next()  # decide on new image early
					i['alpha']     = 0
					i['since']     = now
					i['max_time']  = self.default_time
					
					# adjust max time in case the two sides are too close together for swapping
					if (index == 1):
						t1 = self.im[0]['since'] + self.im[0]['max_time']
						t2 = self.im[1]['since'] + self.im[1]['max_time']
						if (abs(t1-t2) < self.default_time / 2):
							i['max_time'] += 1
					
				dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (dirty):
			super().update(full=True)

	def make_inactive (self):
		for i in self.im:
			if (i['image'] is not None):
				i['image'].unload()
			if (i['image_new'] is not None):
				i['image_new'].unload()
		super().make_inactive()

	def draw (self):
		# draw two images side-by-side
		# draw left image
		self.gui.draw_image(
			self.im[0]['image'], pos=(0.5 * self.line_pos, 0.5),
			size=(1,1),
			mask=(0, self.line_pos, 0,1),
			a=1-self.im[0]['alpha'])
		# draw new image if available
		if (self.im[0]['alpha'] > 0):
			self.gui.draw_image(self.im[0]['image_new'], pos=(0.5 * self.line_pos, 0.5),
				size=(1,1),
				mask=(0, self.line_pos, 0,1),
				a=self.im[0]['alpha'])
		
		# draw right image
		self.gui.draw_image(self.im[1]['image'], pos=(1 - 0.5 * self.line_pos, 0.5),
			size=(1,1),
			mask=(self.line_pos, 1, 0,1),
			a=1-self.im[1]['alpha'])
		# draw new image if available
		if (self.im[1]['alpha'] > 0):
			self.gui.draw_image(self.im[1]['image_new'], pos=(1 - 0.5 * self.line_pos, 0.5),
				size=(1,1),
				mask=(self.line_pos, 1, 0,1),
				a=self.im[1]['alpha'])
		
		# draw middle line
		if (self.line_width > 0):
			self.gui.draw_rectangle(o='center', x=self.line_pos, y=-1, w=self.line_width, h=480, c='foreground')

		# draw picker
		if (self.picker_alpha != 0):
			# draw picker background elements
			if (self.picker_pos != self.line_pos):
				# draw two dotted lines from picker to original spot
				# draw 'resting' picker in original spot
				self.gui.draw_rectangle(o='center', x=self.line_pos, y=-1, w=100, h=100, c='foreground',
					a=self.picker_alpha * 0.5)
			# draw picker on top
			self.gui.draw_rectangle(o='center', x=self.picker_pos, y=-1, w=100, h=100, c='foreground',
					a=self.picker_alpha)


class PhotoSoup (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)

		self.image = None

	def update (self):
		dirty = False
		now = time.time()

		if (self.image is None or now > self.last_update + 5):
			self.image = self.core.images.get_next()
			dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (dirty):
			super().update(full=True)

	def draw (self):
		self.gui.draw_image(self.image, pos=(0.5, 0.5), size=(1, 1), sq=False)


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
