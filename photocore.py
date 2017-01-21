#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

from hashlib import md5
from math import sqrt, pi, cos, sin, atan2
from multiprocessing import Process, Queue
import os
import pickle
import psutil
import pygame
from pygame.locals import *
from queue import Empty as QueueEmpty
import random
import serial
import sys
import time
import traceback

if (sys.platform == 'darwin'):
	from mocking import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE
else:
	from ft5406 import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE
	# set display explicitly to allow starting this script via SSH with output on Pi display
	# not necessary otherwise. requires running with sudo on the remote terminal.
	os.environ['SDL_VIDEODRIVER'] = 'fbcon'

#from subprocess import Popen


# ----- GLOBAL VARIABLES ---------------------------------------------

# make code to switch modes without user intervention

# DualDisplay: don't swap over if dragging/user interaction is active -> check again

# PhotoSoup: map out functionality and interactivity

# make an image reduction script that takes in new images and preps those
#   use pygame.image.save(surface, filename)
#   consider adding webserver along with this

# make wifi connecting

# ability to set display brightness (use dragging in Status display for brightness)

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
		self.images   = ImageManager('../images', '../uploads', core=self)
		self.gui      = GUI(core=self)
		self.input    = InputHandler(core=self)
		
		# init programs
		self.programs                = []
		self.program_active_index    = 1
		self.program_preferred_index = 1
		self.programs.append( BlankScreen(  core=self) )
		self.programs.append( StatusProgram(core=self) )
		self.programs.append( DualDisplay(  core=self) )
		self.programs.append( PhotoSoup(    core=self) )

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
	def __init__ (self, image_folder='', upload_folder='', core=None):
		self.core          = core
		self.images        = []
		self.recent        = []
		self.image_folder  = image_folder
		self.upload_folder = upload_folder

		# for importer process
		self.do_delete     = True
		self.last_update   = 0

		# start the importer process in another thread
		self.scanner_queue = Queue()
		self.process_queue = Queue()
		self.process       = Process(target=self.run_importer)
		self.process.start()

		# also manage a simple webserver interface for image uploads
		self.upload_server = SimpleServer(debug=True, port=80, use_signals=False, regular_run=False)

		# load images
		self.scan_folder(self.image_folder, 'append')

	def update (self):
		# check if scanner is triggered by importer process
		try:
			# get without blocking (as that wouldn't go anywhere)
			# raises Empty if no items in queue
			item = self.scanner_queue.get(block=False)
			if (item is not None):
				self.scan_folder(self.image_folder, 'append')
		except QueueEmpty:
			pass

	def close (self):
		self.check_use(0) # unload all images unused since now
		self.images = []  # reset to severe memory links

		# signal upload server to shutdown
		self.upload_server.shutdown()

		# signal to process it should close
		self.process_queue.put(True)
		# wait until it does so
		print('Signalled and waiting for importer to close...')
		self.process.join()

	""" Checks recent use of images, requests to unload those unused """
	def check_use (self, seconds_ago=5):
		recent = time.time() - seconds_ago  # n seconds ago
		for image in self.images:
			if (not image.check_use_since(recent)):
				image.unload()

	def scan_folder (self, folder=None, call='append'):
		num_of_files_found = 0

		for dirname, dirnames, filenames in os.walk(folder):
			# editing 'dirnames' list will stop os.walk() from recursing into there
			if '.git' in dirnames:
				dirnames.remove('.git')
			if '.DS_Store' in filenames:
				filenames.remove('.DS_Store')

			# check all filenames, act on valid ones
			for filename in filenames:
				if filename.endswith(('.jpg', '.jpeg')):
					if (call == 'append'):
						self.append(dirname, filename)
					elif (call == 'check_and_resize'):
						self.check_and_resize(dirname, filename)

					num_of_files_found += 1

		return num_of_files_found

	def append (self, dirname, filename):
		file_path = os.path.join(dirname, filename)
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
	def get_next (self, rated=False):
		# get an image to return, and make sure it wasn't returned recently
		acceptable = False
		while not acceptable:
			img = self.get_random()
			if (img.file not in self.recent):
				acceptable = True

				# also consider the image rating to determine whether to accept it
				# (so higher rating => higher chance of acceptance)
				if (rated):
					# do via a random check; default .5 chance yes/no, with changed odds based on rating
					r = random.random() + (img.rate / 3)
					if (r < 0.5):
						acceptable = False  # we'll stay in the loop and try again
		
		# keep track of which image gets returned
		self.recent.append(img.file)
		# make sure the tracking list is limited to avoid images not returning any time soon
		if (len(self.recent) > 10):
			self.recent.pop(0)  # remove first (oldest) element in list

		return img

	def get_count (self):
		return len(self.images)

	""" This is the code that the importer background process will run """
	def run_importer (self):
		# run this while loop forever, unless a signal tells otherwise
		while (True):
			try:
				# first, check if this process received a request to stop
				try:
					# get without blocking (as that wouldn't go anywhere)
					# raises Empty if no items in queue
					item = self.process_queue.get(block=False)
					if (item is not None):
						break
				except QueueEmpty:
					pass

				# check for new images
				if (time.time() > self.last_update + 10):
					new_images = self.scan_folder(self.upload_folder, 'check_and_resize')
					
					# indicate we have new images to scan
					if (new_images > 0):
						self.scanner_queue.put(True)

					self.last_update = time.time()

				time.sleep(5)
			# ignore any key input (handled by main thread)
			except KeyboardInterrupt:
				pass

		# finally, after exiting while loop, it ends here
		#print('Terminating importer process')

	""" Takes in an image filepath, checks if a resize is possible, then deletes original """
	def check_and_resize (self, dirname, filename):
		# decide on in/output path
		in_file_path        = os.path.join(dirname, filename)
		in_file_size        = os.stat(in_file_path).st_size
		marked_for_deletion = False

		# consider a unique filename based on original filename and filesize (to avoid same names across folders mixups)
		# use only the first 12 characters to keep it sane / legible
		out_filename = md5(filename.encode('utf-8') + str(in_file_size).encode('utf-8')).hexdigest()[:12] + '.jpg'
		out_file_path = os.path.join(self.image_folder, out_filename)

		# check if resized image already exists, otherwise take action
		if (os.path.exists(out_file_path) is True):
			marked_for_deletion = True
		else:
			# use photocore's Image class for resizing and saving
			p = Image(in_file_path)
			surface, size_string = p.get((800,480), fill_box=True)
			print('Resizing: ', in_file_path, surface.get_size())
			result = p.save_to_file(size_string, out_file_path)

			if (result is False):
				print('Warning, could not save: ', in_file_path)
			else:
				# the original may now be deleted
				marked_for_deletion = True

		if (self.do_delete and marked_for_deletion):
			# consider removing the original file
			try:
				print('Deleting:', in_file_path)
				os.remove(in_file_path)
				pass
			except OSError as ose:
				print(ose)


class Image ():
	def __init__ (self, file=None, shown=[], rate=0):
		self.file      = file
		self.image     = {
		self.image     = {'full': None}  # only load when necessary
		self.size      = (0,0)           # in pixels x,y
		self.is_loaded = False
		self.last_use  = 0

		self.rate      = rate   # default is 0, range is [-1, 1]
		self.shown     = list(shown)  # list, each item denotes for how long image has been shown

	def get (self, size, fill_box=False, fit_to_square=False, circular=False, smooth=True):
		self.last_use = time.time()

		# load if necessary
		if (self.is_loaded is False):
			self.load()

		# check the required size and make it available
		if (size[0] < self.size[0] or size[1] < self.size[1]):
				# create unique identifier string for this size
				size_string = str(size[0]) + 'x' + str(size[1])
				if (circular):
					size_string = size_string.replace('x','c')
				elif (fit_to_square):
					size_string = size_string.replace('x','s')
				elif (fill_box):
					size_string = size_string.replace('x','f')

				# check if this resizing is cached already
				if (size_string in self.image):
					return self.image[size_string], size_string
				else:
					# scale and keep for future use
					img = None
					if (circular):
						img = self.scale(size, fill_box=True, fit_to_square=True, smooth=smooth)
						img = self.make_circular(img)
					else:
						img = self.scale(size, fill_box, fit_to_square, smooth)
					self.image[size_string] = img
					return img, size_string
		# without resize
		return self.image['full'], size_string

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
			if (s == 'full'):
				self.image[s] = None
			else:
				sizes_to_delete.append(s)
		# finally, delete sizes (separate loop avoids dict size changes during iteration)
		for sd in sizes_to_delete:
			del self.image[sd]

	""" Checks if image has been requested since threshold_time, False if not """
	def check_use_since (self, threshold_time):
		if (self.last_use < threshold_time):
			return True
		return False

	""" Save a version of this image to path. Size_string is assumed to exist, returns False otherwise. """
	def save_to_file (self, size_string, output_path):
		if (size_string in self.image):
			try:
				pygame.image.save(self.image[size_string], output_path)
				return True
			except Exception as e:
				print(e)
		# return here if saving fails
		return False

	""" Scales 'img' to fit into box bx/by.
		This method will retain the original image's aspect ratio
	    Based on: http://www.pygame.org/pcr/transform_scale/ """
	def scale (self, box_size, fill_box=False, fit_to_square=False, smooth=True):
		ix,iy = self.image['full'].get_size()
		bx,by = box_size
		fill_box = fill_box
		# square images always fill out the box, so make sure it's square in shape
		if (fit_to_square):
			fill_box = True
			bx = min(bx,by)
			by = min(bx,by)

		# determine scale factor
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

		if (fill_box):
			if (bx == sx and by == sy):
				pass  # s'all good man!
			elif (bx/sx > by/sy):
				sy = (bx / sx) * sy
				sx = bx
			else:
				sx = (by / sy) * sx
				sy = by

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

		#print((ix,iy), (bx,by), (sx,sy), scaled_img.get_size(), 'fill:'+str(fill_box), 'sq:'+str(fit_to_square))

		return scaled_img

	""" Returns a surface that is 'circular' (has a black background with image as circle in it) """
	def make_circular (self, img):
		size = img.get_size()

		# make a surface that is equal in size
		surface = pygame.Surface(size)
		# fill it black
		surface.fill([0,0,0])
		# draw white circle on top and set white color to transparent
		pygame.draw.circle(surface, [255,255,255], (int(size[0]/2), int(size[1]/2)), int(min(size)/2), 0)
		surface.set_colorkey([255,255,255])
		# draw the black 'vignette' on top of the image, white parts won't overwrite original
		surface_rect = surface.get_rect()
		surface_rect.topleft = (0,0)
		img.blit(surface, surface_rect)
		# set pure black as the transparent color
		img.set_colorkey([0,0,0])

		return img

	""" Up or downvotes an image """
	def do_rate (self, positive=True, delta=0.2):
		if (positive):
			self.rate += delta
		else:
			self.rate -= delta
		# limit to [0,1] range
		self.rate = max(min(self.rate, 1), -1)
		#print('rate', self.file, self.rate, positive)

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


class Vector4 ():
	def __init__ (self, x=0, y=0, z=0, w=0):
		self.set(x,y,z,w)

	def set (self, x=0, y=0, z=0, w=0):
		self.x = x
		self.y = y
		self.z = z
		self.w = w

	def copy (self):
		return Vector4(self.x, self.y, self.z, self.w)

	def __str__ (self):
		return '(x: {0.x}, y: {0.y}, z: {0.z}, w: {0.w})'.format(self)


class InputHandler ():
	def __init__ (self, core=None):
		self.core = core

		self.REST          = 0
		self.MOVING        = 1
		self.DRAGGING      = 2
		self.RELEASED      = 3
		self.RELEASED_TAP  = 4
		self.RELEASED_HOLD = 5
		self.RELEASED_DRAG = 6

		self.pos        = Vector4(0,0,0)  # x, y, timestamp
		self.state      = self.REST
		self.drag       = []  # list of positions, empty if no drag active
		self.last_touch = 0
		self.t          = time.time  # use a reference to avoid issues in touch_handler

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

		# run polling in another thread that calls touch_handler whenever an event comes in
		self.ts.run()

	def update (self):
		now = time.time()

		# handle touchscreen events
		# if last touch event was long ago (> n seconds), set to resting state
		if (self.last_touch < now - 0.25 and self.state != self.DRAGGING):
			self.state = self.REST
		else:
			# indicate to programs that a click occured, drag started, or ended
			pass

		# handle pygame event queue
		events = pygame.event.get()

		# for a mock run, send events also to touchscreen module
		# (as pygame events cannot be taken from its queue twice)
		if (sys.platform == 'darwin'):
			pass #self.ts.add_events(events)

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

	def touch_handler(self, event, touch):
		# touch.slot, touch.id (uniquem or -1 after release), touch.valid, touch.x, touch.y
		self.last_touch = self.t()
		
		# to simplify matters, limit scope to slot 0 (that is, the first finger to touch screen)
		if (touch.slot == 0):
			self.pos.set(touch.x, touch.y, 0)
			
			if event == TS_PRESS:
				# reset
				self.drag = []

				self.state = self.DRAGGING
				self.drag.append(self.pos.copy())
			elif event == TS_MOVE:
				if (self.state == self.REST or self.state >= self.RELEASED):  # presumably only the case on non-touch interfaces (e.g., a mouse)
					self.state = self.MOVING
				else:
					self.state = self.DRAGGING
					self.drag.append(self.pos.copy())
			elif event == TS_RELEASE:
				self.drag.append(self.pos.copy())

				# calculate info on now released drag
				distance = 0
				time     = 0

				if (len(self.drag) > 1):
					distance = sqrt(pow(self.drag[0].x - self.drag[len(self.drag)-1].x, 2) + pow(self.drag[0].y - self.drag[len(self.drag)-1].y, 2))
					time     = self.drag[len(self.drag)-1].z - self.drag[0].z

				# interpret the info
				if (distance > 50):
					# this was a drag, now released
					self.state = self.RELEASED_DRAG
				else:
					if (time < 1.5):
						# this was a tap / click
						self.state = self.RELEASED_TAP
					else:
						# this was a tap and hold
						self.state = self.RELEASED_HOLD


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
		if (self.dirty and self.core.is_debug):
			# draw distance slider
			self.draw_slider(o='left', x=0, y=0, w=800, h=3, r=(self.core.get_distance() / 6.5))
			# draw touch position
			if (self.core.input.state > self.core.input.REST):
				self.draw_circle(x=self.core.input.pos.x, y=self.core.input.pos.y, r=False)

	def draw_rectangle (self, o='center', x=-1, y=-1, w=20, h=20, c='support', a=1, r=True, surf=None):
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

		# create a new surface or use the one supplied
		rectangle_surface = None
		if (surf is None):
			rectangle_surface = pygame.Surface( (w,h) )
			rectangle_surface.fill(self.colors[c])
		else:
			rectangle_surface = surf 
		rectangle_rect = rectangle_surface.get_rect()
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

	def draw_surface (self, surf=None, o='center', x=-1, y=-1, a=1, r=True):
		return self.draw_rectangle(o=o, x=x, y=y, a=a, r=r, surf=surf)

	def draw_circle (self, o='center', x=-1, y=-1, rad=10, c='support', a=1, r=True):
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

		circle_rect = pygame.draw.circle(self.screen, self.colors[c], (int(xpos), int(ypos)), int(rad), 0)

		# set alpha
		#rectangle_surface.set_alpha(min(max(a*255,0),255))

		#self.screen.blit(rectangle_surface, rectangle_rect)
		
		# set flags
		self.dirty = True
		self.dirty_areas.append(circle_rect)

		# return surface and rectangle for future reference if need be
		return (circle_rect)

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

	def draw_image (self, img=None, o='center', pos=(0.5,0.5), size=(1,1), mask=None, a=1, rs=True, fill=False, sq=False, ci=False):
		# decide on place and size
		img_size = size
		if (rs):  # size is relative to screen
			img_size = (size[0] * self.display_size[0], size[1] * self.display_size[1])
		# get image (returns resized, size_string)
		img_scaled = img.get(img_size, fill_box=fill, fit_to_square=sq, circular=ci)[0]

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
		self.dirty       = True
		self.first_run   = True

	""" code to run every turn, needs to signal whether a gui update is needed """
	def update (self, dirty=True, full=False):
		# always trigger update in absence of better judgement
		if (full):
			self.gui.set_dirty_full()
		elif (dirty):
			self.gui.set_dirty()
		# update time since last update
		self.last_update = time.time()
		# set other variables
		self.dirty = False
		if (self.first_run):
			self.first_run = False

	""" code to run when program becomes active """
	def make_active (self):
		self.is_active = True
		self.dirty     = True
		self.first_run = True
		self.gui.set_dirty_full()

	""" code to run when this program ceases to be active """
	def make_inactive (self):
		self.is_active = False
		self.dirty     = False
		self.first_run = True
		self.gui.set_dirty_full()

	def close (self):
		if (self.is_active):
			self.make_inactive()

	def draw (self):
		pass


class BlankScreen (ProgramBase):
	def update (self):
		pass  # do nothing (relies on GUI class providing a blank canvas on first run)


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

		self.line_pos           = 0.5
		self.line_width         = 0
		self.line_pos           = 0.5
		self.last_line_pos      = 0.5
		self.picker_plus_surf_n = None
		self.picker_plus_surf_a = None
		self.picker_plus_pos    = 0.5
		self.picker_min_pos     = 0.5
		self.picker_min_surf_n  = None
		self.picker_min_surf_a  = None
		self.picker_alpha       = 1
		self.preferred_image    = None
		self.last_swap          = 0

	def update (self):
		self.dirty  = False
		interactive = False
		now         = time.time()
		check_for_swap_over = False
		settle_line_pos     = False

		# is state interactive?
		if (self.core.input.state > self.core.input.REST):
			self.dirty  = True
			interactive = True

		# pick position of line, based on input
		# if user drag action started near the line, drag it and let line follow
		if (self.core.input.state >= self.core.input.DRAGGING):
			# first check if all this actually started close to the line's resting position
			start_x = abs(self.core.input.drag[0].x - self.gui.display_size[0]/2)
			if (start_x < 50):
				self.line_pos = self.core.input.pos.x / self.gui.display_size[0]

				if (self.core.input.state == self.core.input.RELEASED_DRAG):
					# begin rating, feedback, swap over
					check_for_swap_over = True
			else:
				settle_line_pos = True
		else:
			settle_line_pos = True
		
		# bring line position back to normal, without abrupt change
		if (settle_line_pos):
			# get extra amount over .5, and take a portion of that off
			self.line_pos = self.line_pos + 0.2 * (0.5 - self.line_pos)

		# picker position depends on line
		self.picker_plus_pos = 0.5 + 0.8 * (self.line_pos - 0.5)
		self.picker_min_pos  = 0.5 + 1.2 * (self.line_pos - 0.5)

		# if user indicates a clear preference, go with that
		# this means a drag of the line crosses a threshold (position away from centre)
		if (self.line_pos < 0.15 or self.line_pos > 0.85):
			# set up for that
			self.preferred_image = int(self.line_pos < 0.5)  # 1 or 0, if line > 0.5

			# do actual rating and swap
			if (check_for_swap_over):
				# rate both images
				self.im[0]['image'].do_rate(self.preferred_image == 0)  # True if line is far right, False otherwise
				self.im[1]['image'].do_rate(self.preferred_image == 1)  # vice versa, True if far left
				self.core.data.set_dirty()
				# give feedback (both for rating, and swap)
				# get one image to fade quickly and swap over
				self.im[ abs(self.preferred_image - 1) ]['swap'] = True
				# reset drag of line (let it go back to default to avoid continued rating for a next duel)
				# TODO
				self.last_swap = now

			self.dirty = True
		else:
			self.preferred_image = None

		# make sure any change in line position is registered as change
		if (self.line_pos != self.last_line_pos):
			self.last_line_pos = self.line_pos
			self.dirty = True

		# decide if line should be shown
		new_line_width = max(min(20 / pow(self.core.get_distance() + 0.5, 3), 6), 0)
		if (interactive):
			# make it fade in
			new_line_width = min(self.line_width + 1, 6)
		elif (new_line_width < 0.8):  # no need to consider smaller than this
			new_line_width = 0
		# only update when necessary
		if (new_line_width != self.line_width):
			self.line_width = new_line_width
			
			self.dirty = True
		
		# decide if picker should be shown
		new_picker_alpha = max(min(-10/3 * self.core.get_distance() + 8/3, 1), 0)
		if (interactive):
			# make it fade in
			new_picker_alpha = min(self.picker_alpha + 0.1, 1)
		elif (new_picker_alpha < .004):  # no need to consider smaller than this
			new_picker_alpha = 0
		# only update when necessary
		if (new_picker_alpha != self.picker_alpha):
			self.picker_alpha = new_picker_alpha
			
			self.dirty = True

		# loop over two image slots to assign, swap, fade, etc.
		for index, i in enumerate(self.im):
			if (self.first_run):
				# make sure there is an image
				i['image']     = self.core.images.get_next(rated=True)
				i['image_new'] = self.core.images.get_next(rated=True)
				i['since']     = now
				if (index == 1):
					i['max_time'] *= 1.5

			# if an image has been on long enough, swap over
			# but don't do so if user is interacting with the device
			if (i['swap'] is False and interactive):
				# extend max time such that it lasts until now + 2 seconds (plus, take into account switch time)
				if (i['since'] + i['max_time'] < now + self.switch_time + 2):
					i['max_time'] = (now + self.switch_time + 2) - i['since']
					# also set alpha in case it was about to switch
					i['alpha']    = 0
			elif (i['swap'] or i['since'] < now - i['max_time'] + self.switch_time):
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
					i['image_new'] = self.core.images.get_next(rated=True)  # decide on new image early
					i['alpha']     = 0
					i['since']     = now
					i['max_time']  = self.default_time
					
					# adjust max time in case the two sides are too close together for swapping
					if (index == 1):
						t1 = self.im[0]['since'] + self.im[0]['max_time']
						t2 = self.im[1]['since'] + self.im[1]['max_time']
						if (abs(t1-t2) < self.default_time / 2):
							i['max_time'] += 1
					
				self.dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (self.dirty):
			super().update(full=True)

	def make_active (self):
		# draw the picker surfaces in advance for later reference
		self.picker_plus_surf_n = self.get_picker_surface(False, True)
		self.picker_plus_surf_a = self.get_picker_surface(True, True)
		self.picker_min_surf_n  = self.get_picker_surface(False, False)
		self.picker_min_surf_a  = self.get_picker_surface(True, False)

		super().make_active()

	def make_inactive (self):
		# reset variables to None to free memory
		self.picker_plus_surf_n = None
		self.picker_plus_surf_a = None
		self.picker_min_surf_n  = None
		self.picker_min_surf_a  = None

		for i in self.im:
			if (i['image'] is not None):
				i['image'].unload()
			if (i['image_new'] is not None):
				i['image_new'].unload()
		super().make_inactive()

	def get_picker_surface (self, armed=False, positive=False):
		back_color  = self.gui.colors['foreground']
		front_color = self.gui.colors['support']
		if (positive):
			front_color = self.gui.colors['good']
		if (armed):
			back_color = self.gui.colors['support']
			front_color = self.gui.colors['foreground']
		
		surface = pygame.Surface((60, 60))
		
		# fill black, then set black color as transparent
		surface.fill(self.gui.colors['background'])
		surface.set_colorkey(self.gui.colors['background'], pygame.RLEACCEL)

		# draw circle
		pygame.draw.circle(surface, back_color, (30,30), 30, 0)
		# draw a +/- signifier on top
		pygame.draw.circle(surface, front_color, (30,15), 4, 0)
		pygame.draw.circle(surface, front_color, (30,25), 4, 0)
		pygame.draw.circle(surface, front_color, (30,35), 4, 0)
		pygame.draw.circle(surface, front_color, (30,45), 4, 0)
		if (positive):
			# draw a positive signifier
			pygame.draw.circle(surface, front_color, (21,20), 4, 0)
			pygame.draw.circle(surface, front_color, (39,20), 4, 0)
		else:
			# idem, for negative
			pygame.draw.circle(surface, front_color, (21,40), 4, 0)
			pygame.draw.circle(surface, front_color, (39,40), 4, 0)
		
		return surface

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
		self.gui.draw_image(self.im[1]['image'], pos=(1 - 0.5 * (1 - self.line_pos), 0.5),
			size=(1,1),
			mask=(self.line_pos, 1, 0,1),
			a=1-self.im[1]['alpha'])
		# draw new image if available
		if (self.im[1]['alpha'] > 0):
			self.gui.draw_image(self.im[1]['image_new'], pos=(1 - 0.5 * (1 - self.line_pos), 0.5),
				size=(1,1),
				mask=(self.line_pos, 1, 0,1),
				a=self.im[1]['alpha'])
		
		# draw middle line
		if (self.line_width > 0):
			self.gui.draw_rectangle(x=self.line_pos, y=-1, w=self.line_width, h=480, c='foreground')

		# draw pickers
		if (self.picker_alpha != 0):
			# draw single line between pickers
			width = abs(self.picker_plus_pos - self.picker_min_pos) * self.gui.display_size[0]
			# only draw when it's necessary (line would be visible at all)
			if (width > self.line_width + 60):
				self.gui.draw_rectangle(x=self.line_pos, y=-1, w=width, h=2, c='foreground',
					a=self.picker_alpha)

			# draw pickers on top
			if (abs(0.5 - self.line_pos) < 0.35):
				# regular pickers
				self.gui.draw_surface(self.picker_min_surf_n,  x=self.picker_min_pos,  y=0.5, a=self.picker_alpha)
				self.gui.draw_surface(self.picker_plus_surf_n, x=self.picker_plus_pos, y=0.5, a=self.picker_alpha)
			else:
				# armed pickers
				self.gui.draw_surface(self.picker_min_surf_a,  x=self.picker_min_pos,  y=0.5, a=self.picker_alpha)
				self.gui.draw_surface(self.picker_plus_surf_a, x=self.picker_plus_pos, y=0.5, a=self.picker_alpha)


class PhotoSoup (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)

		self.base_size = 0.2

		self.images = []
		for n in range(0,9):
			self.images.append({
				'image': None,
				'since': 0,
				'v'    : Vector4(0, 0, 0, 0),
				'size' : self.base_size
			})

	def update (self):
		now = time.time()

		first=True
		print('update')

		for i in self.images:
			if (i['image'] is None or i['v'].x < -50 or i['v'].x > 850 or i['v'].y < -50 or i['v'].y > 530):
				i['image'] = self.core.images.get_next()
				i['since'] = now
				i['v'].set(
					0.5 * self.core.gui.display_size[0],
					0.5 * self.core.gui.display_size[1],
					2 * pi * random.random(),
					10 * random.random())
			else:
				# i['v'].x += -0.001 * cos(i['v'].z)
				# i['v'].y += -0.001 * sin(i['v'].z)

				""" --------
				there is the default force with (polar) direction i['v'].w and magnitude i['v'].w
				each other image has influence, through attraction Fa and repulsion Fr
				those two forces are from x,y towards the other x,y with radian angle ß and -ß
				so the sum of the two forces influence the default force """

				# calculate the base vector for this image (with magnitude w, angle z)
				vi_x = i['v'].w * cos(i['v'].z)
				vi_y = i['v'].w * sin(i['v'].z)
				#print('1', vi_x, vi_y)

				for img in self.images:
					# calculate influence
					f = self.get_force_attraction(i, img) - self.get_force_repulsion(i, img)
					a = self.get_angle(i, img)

					# add this vector to the base
					vi_x += f * cos(a)
					vi_y += f * sin(a)
					#print('2', vi_x, vi_y, f, a)

				# add the resultant vector to get the new position
				#print('3', vi_x, vi_y)
				i['v'].x += vi_x
				i['v'].y += vi_y

			if first:
				print(i['v'].x, i['v'].y)
				first=False

		self.dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (self.dirty):
			super().update(full=True)

	def get_angle (self, a, b):
		dx = b['v'].x - a['v'].x
		dy = a['v'].y - b['v'].y
		return atan2(dy, dx)

	def get_distance (self, a, b):
		return sqrt(pow(b['v'].x - a['v'].x,2) + pow(a['v'].y - b['v'].y ,2))

	def get_force_attraction (self, a, b):
		# TODO increase/reduce attraction based on image rating
		return 0.1 * self.get_distance(a, b)

	def get_force_repulsion (self, a, b):
		# TODO add check for overlapping, to increase repulsion in that case
		distance = max(self.get_distance(a, b), 0.01)  # avoid divide by zero problems
		return 0.002 / pow(distance, 2)

	def draw (self):
		for i in self.images:
			xpos = i['v'].x / self.core.gui.display_size[0]
			ypos = i['v'].y / self.core.gui.display_size[1]
			self.gui.draw_image(i['image'], pos=(xpos, ypos), size=(i['size'], i['size']), rs=False, ci=True)


# ----- MAIN ------------------------------------------------------------------


""" Unless this script is imported, do the following """
if __name__ == '__main__':
	# define here so it's available later, also in case of exception handling
	core = None

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
		# make a final attempt to close gracefully
		if (core is not None):
			core.close()
	finally:
		# if all else fails, quit pygame to get out of fullscreen
		pygame.quit()
