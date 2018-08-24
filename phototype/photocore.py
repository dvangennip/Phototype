#!/usr/bin/python3
# coding: utf-8

# ----- IMPORT LIBRARIES ------------------------------------------------------

from hashlib import md5
from math import sqrt, pi, cos, sin, atan2
from multiprocessing import Process, Queue
import os
import pickle
from PIL import Image as PIL_Image, ExifTags
import psutil
import pygame
from pygame.locals import *
from queue import Empty as QueueEmpty
import random
import requests
from shutil import chown
import signal
from socket import gethostname
import sys
import time
import traceback
from simpleserver import SimpleServer
import qrcode

if (sys.platform == 'darwin'):
	# simulate touches by masquerading pointer movements and clicks
	from mocking import Touchscreen, Touch, TS_PRESS, TS_RELEASE, TS_MOVE
else:
	import RPi.GPIO as GPIO
	from ft5406 import Touchscreen, TS_PRESS, TS_RELEASE, TS_MOVE
	# set display explicitly to allow starting this script via SSH with output on Pi display
	# not necessary otherwise. requires running with sudo on the remote terminal.
	os.environ['SDL_VIDEODRIVER'] = 'fbcon'

# ----- TODO ------------------------------------------------------------------
"""
# DualDisplay: give some rating feedback (pickers moving up or down, fading out)

# check data export and logging abilities
--- any distance sensor judgements of watching/paying attention?

"""
# ----- GLOBAL FUNCTIONS ------------------------------------------------------

version = 9

""" globally available logging code for debugging purposes """
def logging (message):
	print(message)
	with open('errors.log','a') as f:
		t = time.strftime("%Y-%m-%d %H:%M:%S - ", time.localtime())
		f.write(t + str(message) + '\n')

""" calling this is the default way of making the script do its magic """
def main ():
	# first check if start is not blocked
	if (os.path.exists('nostart.txt')):
		print('Lock file present, will not start photocore.')
		exit(0)
		
	# define here so it's available later, also in case of exception handling
	core = None
	try:
		# initialise all components
		core = Photocore()

		# program stays in this loop unless called for exit
		while (True):
			t0 = time.time()
			core.update()
				
			# exit flag set?
			if (core.do_exit):
				core.close()
				break
			else:
				# pause between frames
				t1 = time.time()
				dt = round((t1 - t0) * 1000)  # in millis
				# pause for a minimum of 10 ms and max of 40 ms (25fps)
				pygame.time.wait( max(40 - dt, 10) )
	except Exception as e:
		with open('errors.log', 'a') as f:
			traceback.print_exc(file=f)  #sys.stdout
		# make a final attempt to close gracefully
		if (core is not None):
			core.close(1)
	finally:
		# if all else fails, quit pygame to get out of fullscreen
		pygame.quit()

		# trigger a system shutdown if requested
		if (core.do_shutdown):
			time.sleep(1)
			os.system('sudo shutdown now')


# ----- CLASSES ---------------------------------------------------------------


class Photocore ():
	def __init__ (self):
		# prepare for a systemd-initiated run
		# systemd may send SIGHUP signals which, if unhandled, gets the process killed
		signal.signal(signal.SIGHUP,  self.handle_signal)
		signal.signal(signal.SIGTSTP, self.handle_signal)  # Stop (^Z)
		signal.signal(signal.SIGINT,  self.handle_signal)  # Interrupt (^C)

		# init variables to default values
		self.do_exit      = False
		self.do_shutdown  = False
		self.is_debug     = False
		self.use_network  = True   # can any web, import, or update services be run?
		self.last_update  = 0
		self.memory_usage = 0
		self.memory_total = round(psutil.virtual_memory().total / (1024*1024))

		# check for arguments passed in
		for argument in sys.argv:
			if (argument == '-debug'):
				self.is_debug = True
			elif (argument == '-nonet'):
				self.use_network = False

		# initiate all subclasses
		self.data     = DataManager(core=self)
		self.network  = NetworkManager()
		self.updater  = SelfUpdater(core=self, use_updater=self.use_network)
		self.display  = DisplayManager()
		self.distance = DistanceSensor()
		self.images   = ImageManager('../images', '../uploads', core=self, use_import=self.use_network)
		self.gui      = GUI(core=self)
		self.input    = InputHandler(core=self)
		
		# init programs
		self.programs                = []
		self.program_active_index    = 0
		self.program_preferred_index = 0
		self.max_time_for_program    = time.time() + 30
		self.switch_requested        = False
		self.add_program('BlankScreen')
		self.add_program('DualDisplay')
		self.add_program('PhotoSoup')
		self.add_program('PhotoPatterns')

		self.data.log('Photocore started.')

		if len(self.programs) < 1:
			print('No programs to run, will exit')
			self.do_exit = True
		else:
			# begin with a program
			self.set_active(self.program_active_index, force=True)

	def update (self):
		now = time.time()

		# update self
		if (self.last_update < now - 1):
			# track memory usage
			mem_available = round(psutil.virtual_memory().available / (1024*1024))
			self.memory_usage = round(100 * (1 - (mem_available / self.memory_total) ))

			# deal with potential memory leak of images not unloading after use
			if (mem_available < 500):
				self.images.check_use()

			self.last_update = now
		
		# update all subclasses
		self.data.update()
		self.network.update()
		self.updater.update()
		self.display.update()
		self.distance.update()
		self.input.update()
		self.images.update()

		# decide on active program  - - - - - - - - - - - - - - - - -

		# check if time is up for current program
		# or, if at night, see if program has been active for some time before forcing a switch
		if (now > self.max_time_for_program or (self.get_active().get_active_time() > 600 and self.get_time_is_night()) ):
			# first check if state has not been interactive for past minute (if it was, don't switch yet)
			if (self.input.get_last_touch() < now - 60):
				self.switch_requested = True

		# pick another program if a switch is desired (but no preference was indicated)
		if (self.switch_requested):
			# at night, stick with a blank screen
			if (self.get_time_is_night()):
				if (self.program_active_index == 0):
					pass  # do nothing, remain in night mode
				else:
					self.program_preferred_index = 0
			else:
				# pick another program (but avoid blank program, so index >= 1)
				# and make sure the new pick isn't similar to the current program
				while True:
					self.program_preferred_index = random.randint(1, len(self.programs) - 1)
					if (self.program_preferred_index != self.program_active_index):
						break

		# switch over if desired program does not match current
		if (self.program_preferred_index != self.program_active_index):
			switch_success = self.set_active(self.program_preferred_index)

			if (switch_success):
				# decide on the time the next program will be active
				# uses the program's max time as a basis, with some added randomness [0.75, 1.25]
				random_time = ((random.random() / 2) + 0.75) * self.get_active().get_max_time()
				# at night, intervals are shorter (to be able to revert to rest sooner)
				if (self.get_time_is_night()):
					random_time /= 3

				self.max_time_for_program = now + random_time
				self.switch_requested = False
			else:
				# add another minute to time allowance to avoid trying once again on next loop
				self.max_time_for_program += 60

		# update active program  - - - - - - - - - - - - - - - - -
		self.programs[self.program_active_index].update()

		# last, update GUI
		self.gui.update()

	def close (self, exit_code=0):
		if (exit_code == 0):
			if (self.do_shutdown):
				self.data.log('Photocore closing, device shutting down.')
			else:
				self.data.log('Photocore closing.')
		else:
			self.data.log('Photocore closing, with errors.')

		# close in reverse order from update
		for program in self.programs:
			program.close()

		# close subclasses
		self.data.close()
		self.updater.close()
		self.gui.close()
		self.images.close()
		self.input.close()
		self.distance.close()
		self.display.close()
		self.network.close()

	def set_exit (self, shutdown=False):
		self.do_exit     = True
		self.do_shutdown = shutdown

	""" handler for system signals """
	def handle_signal (self, signum, frame):
		if (signum == signal.SIGTSTP or signum == signal.SIGINT):
			self.set_exit()

	""" Returns reference to active program """
	def get_active (self):
		return self.programs[self.program_active_index]

	""" Returns True if switched, False otherwise """
	def set_active (self, index=0, force=False):
		# set within bounds of [0,highest possible index]
		new_index = min(max(index, 0), len(self.programs)-1)

		# only switch when index has changed
		if (force or new_index != self.program_active_index):
			# check if prospective program can be run
			if (self.programs[new_index].can_run()):
				# cleanup
				self.get_active().make_inactive()
				self.images.check_use(0)

				# switch
				self.program_active_index    = new_index
				self.program_preferred_index = new_index
				self.get_active().make_active()

				self.data.log('Switching to program ' + self.get_active().get_name())

				return True
			else:
				# cannot switch, so refrain from trying on next run
				self.program_preferred_index = self.program_active_index

		return False

	def set_preferred (self, index=0):
		self.program_preferred_index = index

	def add_program (self, name):
		# create instance of program class (based on name)
		program = globals()[name](core=self)

		# check for any prior data
		prior_data = self.data.get_program_match( program.get_name() )
		if (prior_data is not None):
			program.set_shown(prior_data['shown'])

		# add to list
		self.programs.append(program)

	def set_next_program (self):
		# set preferred to next, or back to zero if at limits
		self.program_preferred_index += 1
		if (self.program_preferred_index >= len(self.programs)):
			self.program_preferred_index = 0

		#self.set_active(self.program_preferred_index)

	def request_switch (self):
		self.switch_requested = True

	def toggle_status_panel (self):
		self.get_active().toggle_status_panel()

	def get_images_count (self):
		return self.images.get_count()

	""" Returns timestamp of last user interaction """
	def get_last_ix (self):
		return self.input.get_last_touch()

	def get_memory_usage (self):
		return self.memory_usage

	def get_distance (self):
		return self.distance.get()

	def get_display_brightness (self):
		return self.display.get_brightness()

	def set_display_brightness (self, brightness=100, user_initiated=False):
		self.display.set_brightness(brightness, user_initiated)

	""" Returns time as a string: 15:45:23  10/08 """
	def get_time (self):
		return time.strftime("%H:%M:%S  %d/%m", time.localtime())

	""" Returns time as a float between [0-24)"""
	def get_time_24h (self):
		tl = time.localtime()
		return tl.tm_hour + tl.tm_min/60.0 + tl.tm_sec/3600.0

	""" Returns False at night, True otherwise """
	def get_time_is_night (self):
		t = self.get_time_24h()
		if (t < 6.0):  # 00.00 to 06.00
			return True
		return False

	""" Returns disk space usage in percentage """
	def get_disk_space (self):
		return psutil.disk_usage('/').percent

	def get_temperature (self):
		if (sys.platform == 'darwin'):
			return 0
		else:
			# update CPU temperature -----
			#   call returns CPU temperature as a character string (> temp=42.8'C)
			try:
				temp = os.popen('vcgencmd measure_temp').readline()
				return float(temp.replace("temp=","").replace("'C\n",""))
			except Exception:
				# most likely a memory allocation issue if low on memory
				# it's not critical to the functioning though, so warn and continue
				print('Warning: temperature cannot be read')
				return 0

	def get_network_state (self):
		return self.network.get_state_summary()

""" SelfUpdater looks online for newer versions of this code and replaces itself with such a file.
	Upon a restart the new code should be used, thus establishing a simple update mechanism. """
class SelfUpdater ():
	def __init__ (self, core=None, use_updater=True):
		self.core            = core
		self.use_updater     = use_updater
		self.update_interval = 7200  # in seconds, how often does it check for updates?
		self.last_update     = time.time() - self.update_interval + 10  # allow the code to start before 1st update

		if (self.use_updater):
			# start the importer process in another thread
			self.updater_queue = Queue()
			self.process_queue = Queue()
			self.process       = Process(target=self.run_updater)
			self.process.start()

	def update (self):
		if (self.use_updater):
			# check if updater is triggered by importer process
			try:
				# get without blocking (as that wouldn't go anywhere)
				# raises Empty if no items in queue
				item = self.updater_queue.get(block=False)
				if (item is not None):
					# call for exit to trigger a restart
					# (relies on a systemd service that restarts this code upon closing)
					self.core.set_exit()
			except QueueEmpty:
				pass

	def close (self):
		if (self.use_updater):
			# signal to process it should close
			self.process_queue.put(True)
			# wait until it does so
			print('Signalled and waiting for self-updater to close...')
			self.process.join()

	""" This is the code that the updater background process will run """
	def run_updater (self):
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

				# check for updates to this code - - - - - - - - - -

				if (self.core.network.is_connected()):
					if (self.last_update < time.time() - self.update_interval):
						if (self.core.is_debug):
							print('Updater: looking for a newer version...')

						# do a request for a file with version number current + 1
						online_path = 'http://project.sinds1984.nl/phototype/'
						path        = 'photocore_v{0}.py'.format(version+1)
						r = requests.get(online_path + path, stream=True)

						# if successful, store the response as a file with the same name
						if (r.status_code == 200):
							success = False
							
							with open(path, 'wb') as f:
								r.raw.decode_content = True
								f.write(r.raw.read())
								success = True

							if (success):
								success = False  # assume the worst, again

								# check integrity of the file
								file_hash = 'something'
								checksum  = 'different'
								with open(path) as file_to_check:
									data = file_to_check.read()    
									file_hash = md5(data.encode('utf-8')).hexdigest()

								# get checksum
								rc = requests.get(online_path + path.replace('.py', '_checksum.txt'), stream=True)
								if (rc.status_code == 200):
									rc.raw.decode_content = True
									checksum = rc.raw.read().decode('utf-8')

									#print(file_hash, checksum)
									if (file_hash == checksum):
										success = True
							
							if (success):
								try:
									# if saving is also successful, set the proper privileges
									chown(path, user='pi', group='pi')
									os.chmod(path, 0o777)  # pass as octal
									
									# rename current photocore.py to photocore_vX.py, as a backup
									os.rename('photocore.py', 'photocore_v{0}.py'.format(version))
									# rename the new file to photocore.py, effectively replacing it
									os.replace(path, 'photocore.py')

									# log the successful update
									self.core.data.log('Updated photocore to version {0}.'.format(version+1))
									# notify main thread of successful update (should trigger a restart)
									self.updater_queue.put(True)
								except Exception as e:
									logging(e)
						else:
							if (self.core.is_debug):
								print('Updater: no new version found at this time.')

						# update the time
						self.last_update = time.time()

				# end of useful code - - - - - - - - - - - - - - - -

				# wait until next round (keep short to enable quick shutdown)
				time.sleep(3)
			# ignore any key input (handled by main thread)
			except KeyboardInterrupt:
				pass

		# finally, after exiting while loop, it ends here
		#print('Terminating updater process')


class DataManager ():
	def __init__ (self, core=None):
		self.core  = core
		self.data  = {
			'log':          [],
			'programs':     [],
			'images':       [],
			'interactions': []
		}
		self.dirty       = False
		self.last_save   = 0  # timestamp
		self.last_export = time.time()  # timestamp at now, to avoid immediate export
		self.min_time_between_saves  = 120  # avoid excessive writing to disk
		self.min_time_between_export = 7200  # once every 2 hours

		# os.uname().nodename
		try:
			with open('data.bin', 'rb') as f:
				loaded_data = pickle.load(f)
				for key in ('log', 'programs', 'images', 'interactions'):
					if (key in loaded_data):
						self.data[key] = loaded_data[key]
		except IOError as eio:
			pass  # called when file doesn't exist (yet), which is fine
		except EOFError as eof:
			pass  # called when file exists but is empty
		except Exception as e:
			raise e

	def update (self):
		if (self.dirty and self.last_save < time.time() - self.min_time_between_saves):
			# for images reference to a list
			self.data['images'] = self.core.images.images

			# programs do not get referenced/stored in full
			# instead, keep track through simpler objects
			for program in self.core.programs:
				match = False

				# attempt to match
				for item in self.data['programs']:
					if (program.get_name() == item['name']):
						match = True
						item['shown'] = program.shown

						# after a match, no need to continue this inner for loop
						break

				# else store a new item (that hopefully matches on future tries)
				if (not match):
					self.data['programs'].append({
						'name': program.get_name(),
						'shown': program.shown
					})

			# request save, and export if it has been a while
			if (self.last_export < time.time() - self.min_time_between_export):
				self.save(export=True)
			else:
				self.save()
			self.dirty = False

	def close (self):
		self.save(export=True)

	def log (self, message):
		self.set_dirty(message)

	def log_action (self, action, value=None):
		self.data['interactions'].append({'timestamp': int(time.time()), 'action': action, 'value': value})
		self.set_dirty()

	def set_dirty (self, message=None):
		if (message is not None):
			t = time.strftime("%Y-%m-%d %H:%M:%S - ", time.localtime())
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

				f.write('\nPROGRAMS\n-----------------\n')
				for program in self.data['programs']:
					f.write(program['name'] + '; shown: ' + str(program['shown']) + '\n')

				f.write('\nINTERACTIONS\n-----------------\n')
				for ix in self.data['interactions']:
					t = time.strftime("%Y-%m-%d %H:%M:%S - ", time.localtime(ix['timestamp']))
					f.write(t + ix['action'] + '; value: ' + str(ix['value']) + '\n')

				f.write('\nIMAGES ({}x)\n-----------------\n'.format(self.core.images.get_count()))
				for img in self.data['images']:
					f.write(str(img) + '\n')

			self.last_export = time.time()

			# also upload to external save
			#self.save_external()

	def save_external (self):
		pass  # TODO not implemented yet
		# with open('data.log', 'r') as f:
		# 	r = requests.post('http://project.sinds194.nl/upload/', files={'{0}_data.log'.format(os.uname().hostname): f})

	def get_program_match (self, name):
		for program in self.data['programs']:
			if program['name'] == name:
				return program
		# without a match
		return None

	""" Return a matching image based on file path """
	def get_image_match (self, file_path):
		for img in self.data['images']:
			if (img.file == file_path):
				return img
		# without a match
		return None


class NetworkManager ():
	def __init__ (self):
		self.last_update = 0
		self.net_types = ('eth0','wlan0')
		if (sys.platform == 'darwin'):
			self.net_types = ('en1','en0')

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
		now = time.time()

		if (not regular or self.last_update < now - 10):
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

			self.last_update = now

	def close (self):
		pass

	def get_networks (self):
		wifi_network_list = []
		# SSID via `sudo iwlist wlan0 scan`
		return wifi_network_list

	def connect (self, wifi_network=None):
		pass

	""" Returns True if any network is up and running, False if none are """
	def is_connected (self):
		# note: uses direct stats from psutil, as a call from another process has no
		#       access to live state info after it starts.
		state = psutil.net_if_stats()
		for net in self.net_types:
			if (state[net].isup):
				return True
		return False

	""" Returns wired IP if connected, or WiFI IP if connected, or False if unconnected """
	def get_ip_address (self):
		for s in self.state:
			if (self.state[s]['connected']):
				return self.state[s]['ip']
		return False

	def get_state_summary (self):
		# first, force an update
		self.update(False)

		# generate a one line summary
		summary = ''
		if (self.state[self.net_types[1]]['connected']):
			summary = summary + "WiFi ({0[ip]})".format(self.state[self.net_types[1]])
		else:
			summary = summary + "WiFi (unconnected)"
		if (self.state[self.net_types[0]]['connected']):
			summary = summary + ", Ethernet ({0[ip]})".format(self.state[self.net_types[0]])
		else:
			summary = summary + ", Ethernet (unconnected)"
		return summary


class DisplayManager ():
	def __init__ (self):
		self.brightness  = 255
		self.is_on       = True
		self.path        = "/sys/class/backlight/rpi_backlight/"
		self.last_change = 0
		self.last_manual_change = 0

	def update (self):
		now = time.time()

		# only automatically adjust display brightness if user hasn't overridden this
		# this the past n seconds (30 min)
		if (self.last_manual_change < now - 1800):
			# only auto adjust when some time has passed since the last change
			if (self.last_change < now - 60):
				# derive value between high and low based on current time
				low             = 5
				high            = 70
				auto_brightness = low

				# take current time, convert to [0-pi], then take sin to get [20-80]
				current_time = time.localtime()
				tt = current_time.tm_hour + current_time.tm_min/60.0  # [0-23.98]

				# at night (22.5 -> 6) just use low value
				if (tt > 6 and tt < 22.5):
					auto_brightness = (high - low) * sin(((tt-6) / (22.5-6)) * pi) + low
				self.set_brightness(auto_brightness)

	def close (self):
		pass

	def is_on (self):
		self.is_on = not self._get_value("bl_power")
		return self.is_on

	def set_on (self, on=True):
		self._set_value("bl_power", int(not on))

	""" Returns brightness on a scale of [0,100] """
	def get_brightness (self):
		if (self.is_on is False):
			return 0
		else:
			self.brightness = int(self._get_value("actual_brightness"))
			return round(self.brightness / 2.55)

	""" Input is in range [0,100] """
	def set_brightness (self, brightness, user_initiated=False):
		self.brightness = round(max(min(2.55 * brightness, 255), 0))
		self.is_on = (self.brightness > 0)

		# set state accordingly
		self._set_value("brightness", self.brightness)

		if (user_initiated):
			self.last_manual_change = time.time()
		self.last_change = time.time()

	# ----- functions below via: https://github.com/linusg/rpi-backlight/ --------

	def _get_value (self, name):
		if (sys.platform == 'darwin'):
			return self.brightness
		else:
			try:
				with open(os.path.join(self.path, name), "r") as f:
					return f.read()
			except PermissionError:
				print('Error: No permission to read backlight values')

	def _set_value (self, name, value):
		if (sys.platform != 'darwin'):
			try:
				with open(os.path.join(self.path, name), "w") as f:
					f.write(str(value))
			except PermissionError:
				print('Error: No permission to set backlight values')
		

class DistanceSensor ():
	def __init__ (self):
		self.distance = 2  # in meters
		self.distance_direction = True  # True if >, False if <
		
		# setup  connection
		self.use_sensor = True
		if (sys.platform == 'darwin'):
			self.use_sensor = False

		# start the input measurement process in another thread
		if (self.use_sensor):
			self.sensor_queue  = Queue()
			self.process_queue = Queue()
			self.process       = Process(target=self.run_sensor_input)
			self.process.start()

	""" Read distance sensor data over serial connection """
	def update (self):
		if (self.use_sensor):
			# check if sensor measurement process has left a new reading
			try:
				# get without blocking (as that wouldn't go anywhere)
				# raises Empty if no items in queue

				# get all items to avoid delays (as items are put in faster than handled here)
				while not self.sensor_queue.empty():
					item = self.sensor_queue.get(block=False)
					if (item is not None):
						self.distance = item
			except QueueEmpty:
				pass
		else:
			# without sensor, fake the distance going up and down over time
			if (self.distance_direction is True):
				self.distance = self.distance + 0.01
				if (self.distance > 6.5):
					self.distance = 6.5
					self.distance_direction = False
			elif (self.distance_direction is False):
				self.distance = self.distance - 0.01
				if (self.distance < 0.2):
					self.distance = 0.2
					self.distance_direction = True

	def close (self):
		# close serial connection
		if (self.use_sensor):
			# signal to process it should close
			self.process_queue.put(True)
			# wait until it does so
			print('Signalled and waiting for sensor process to close...')
			self.process.join()

	""" Returns distance in meters """
	def get (self):
		return self.distance

	""" This function is run as a separate process to avoid locking due to GPIO polling """
	def run_sensor_input (self):
		# setup variables
		distance = 2  # in meters

		# parameters for the low pass filter
		# As k decreases, the low pass filter resolution improves but the bandwidth decreases.
		acc = 0.5   # starting value
		k   = 0.005  # default is .01

		# initiate GPIO input
		GPIO.setmode(GPIO.BCM)  # choose BCM or BOARD numbering schemes
		# set pin to input
		input_pin = 16  # outer row, 3rd from USB ports
		if (gethostname() == 'protopi4'):
			input_pin = 12  # pin 16 broke off for this one :'(
		GPIO.setup(input_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

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

				# useful code - - - - - - - - - - - - - - - - - - - - - - - - -

				""" no analog or hardware PWM readings are possible on a RPi3.
					However, we can undersample the PWM signal and take an average,
					assuming we hit low and high measurements in a proportion approximating
					the true PWM high/low proportion. This is undersampling so requires
					averaging out over a period of time to get stable readings.
				"""

				# read from input
				x = int(GPIO.input(input_pin))  # 1 or 0

				# apply IIR low pass filter (undersampling, so it requires an average)
				acc += k * (x - acc)

				# convert from [0.1] to a value in meters
				""" LV-MaxSonar data
					PW: This pin outputs a pulse width representation of range.
					The distance can be calculated using the scale factor of 147uS per inch.
					PWM range is (0.88, 37.5) in mS
				"""
				distance = self.map_value(acc, 0, 1, 0.88, 37.5) / 0.147 * 2.51 / 100.0
				
				#print('PWM: {0:.2f}\t\tDistance: {1:.2f}m'.format(acc, distance))

				# send the new measure to queue
				self.sensor_queue.put(distance)

				# wait until next round
				time.sleep(0.02)
			# ignore any key input (handled by main thread)
			except KeyboardInterrupt:
				pass

		# finally, after exiting while loop, it ends here
		#print('Terminating sensor measurement process')
		GPIO.cleanup()

	def map_value (self, value, inMin, inMax, outMin, outMax):
		# Figure out how 'wide' each range is
		inSpan = inMax - inMin
		outSpan = outMax - outMin

		# Convert the in range into a 0-1 range (float)
		valueScaled = float(value - inMin) / float(inSpan)

		# Convert the 0-1 range into a value in the out range.
		return outMin + (valueScaled * outSpan)


class ImageManager ():
	def __init__ (self, image_folder='', upload_folder='', core=None, use_import=True):
		self.core          = core
		self.images        = []
		self.recent        = []
		self.image_folder  = image_folder
		self.upload_folder = upload_folder

		# for importer process
		self.use_importer  = use_import
		self.do_delete     = True
		self.last_update   = 0

		if (self.use_importer):
			# start the importer process in another thread
			self.scanner_queue = Queue()
			self.process_queue = Queue()
			self.process       = Process(target=self.run_importer)
			self.process.start()

			# also manage a simple webserver interface for image uploads
			if (os.geteuid() == 0):  # with root access
				self.upload_server = SimpleServer(debug=self.core.is_debug, port=80, use_signals=False, regular_run=False)
			else:
				self.upload_server = SimpleServer(debug=self.core.is_debug, use_signals=False, regular_run=False)

		# load images
		self.scan_folder(self.image_folder, 'append')

	def update (self):
		if (self.use_importer):
			# check if scanner is triggered by importer process
			try:
				# get without blocking (as that wouldn't go anywhere)
				# raises Empty if no items in queue
				item = self.scanner_queue.get(block=False)
				if (item is not None):
					additions = abs(self.get_count() - self.scan_folder(self.image_folder, 'append'))
					self.core.data.log_action('images.scan', '+{0}, for a total of {1}'.format(additions, self.get_count()))
			except QueueEmpty:
				pass

	def close (self):
		self.check_use(0) # unload all images unused since now
		self.images = []  # reset to severe memory links

		if (self.use_importer):
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
				if filename.lower().endswith(('.jpg', '.jpeg')):
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
			file_match = self.core.data.get_image_match(file_path)
			if (file_match is not None):
				p.set_shown(file_match.shown)
				p.set_rate(file_match.rate)
				p.hide(file_match.hidden)
			# add to list
			self.images.append(p)

	def get_images (self):
		return self.images

	def get_random (self):
		return self.images[ random.randint(0, len(self.images)-1) ]

	""" Returns an image and checks if it's not similar to recent images returned """
	def get_next (self, rated=True):
		# get an image to return, and make sure it wasn't returned recently
		acceptable = False
		while not acceptable:
			img = self.get_random()
			if (img.hidden is False and img.file not in self.recent):
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
		# note: number ought to be sufficiently high such that no program would show a similar
		#       number of images on-screen at any time
		if (len(self.recent) > 15):
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
			surface, size_string = p.get((800,480), fill_box=True, remove_black=True, check_orientation=True)
			#print('Resizing: ', in_file_path, surface.get_size())
			result = p.save_to_file(size_string, out_file_path)

			if (result is False):
				print('Warning, could not save: ', in_file_path)
			else:
				# the original may now be deleted
				marked_for_deletion = True

		if (self.do_delete and marked_for_deletion):
			# consider removing the original file
			try:
				#print('Deleting:', in_file_path)
				os.remove(in_file_path)
				pass
			except OSError as ose:
				print(ose)


class Image ():
	def __init__ (self, file=None, shown=[], rate=0):
		self.file      = file
		self.image     = {'full': None}  # only load when necessary
		self.size      = (0,0)           # in pixels x,y
		self.is_loaded = False
		self.last_use  = 0

		self.hidden    = False
		self.rate      = rate   # default is 0, range is [-1, 1]
		self.shown     = list(shown)  # list, each item denotes for how long image has been shown

	def get (self, size, fill_box=False, fit_to_square=False, circular=False, smooth=True, remove_black=False, check_orientation=False):
		self.last_use = time.time()
		size        = (round(size[0]), round(size[1]))
		size_string = 'full'

		# if orientation needs checking, do it here before regular loading
		# as any changes are done to base file
		if (check_orientation):
			if (self.is_loaded):
				self.unload()
			self.correct_orientation()

		# load if necessary
		if (not self.is_loaded):
			self.load()

		# check the required size and make it available
		# a request size >= image size is normally ignored, unless it has to be made circular
		if (size[0] < self.size[0] or size[1] < self.size[1] or circular):
			# create unique identifier string for this size
			size_string = '{0}x{1}'.format(size[0], size[1])
			if (circular):
				size_string = size_string.replace('x','c')
			elif (fit_to_square):
				size_string = size_string.replace('x','s')
			elif (fill_box):
				size_string = size_string.replace('x','f')

			# check if this resizing is cached already
			# if so, ready to return that
			if (not size_string in self.image):
				# scale and keep for future use
				img = None
				if (circular):
					img = self.scale(size, fill_box=True, fit_to_square=True, smooth=smooth)
					img = self.make_circular(img)
				else:
					img = self.scale(size, fill_box, fit_to_square, smooth)
				self.image[size_string] = img.convert()
				# ready to return now

		# if pure blacks need to be removed, do it here after rescaling (smaller file = quicker)
		if (remove_black):
			self.image[size_string] = self.remove_pure_black(self.image[size_string])

		return self.image[size_string], size_string

	def load (self):
		# load image (also call convert for a speed-up)
		self.image['full'] = pygame.image.load(self.file).convert()
		self.size          = self.image['full'].get_size()
		self.is_loaded = True

	""" Free up memory by unloading an image no longer needed """
	def unload (self, since=None):
		self.is_loaded = False

		# also record time this image was shown
		if (since is not None):
			self.was_shown(time.time() - since)  # now - timestamp of its first showing

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

	""" Prepare image to avoid pure black parts being set to transparent elsewhere.
		This should only be done when files are first imported to reduce computation later on. """
	def remove_pure_black (self, img):
		size = img.get_size()
		grey_surface = pygame.Surface(size)
		# get a surface and fill it almost pure black (1/255)
		grey_surface.fill([1,1,1])
		# draw image on top with pure black set to transparent
		img.set_colorkey([0,0,0])
		img_rect = img.get_rect()
		img_rect.topleft = (0,0)
		grey_surface.blit(img, img_rect)
		img = grey_surface
		# all pure black pixels have now been replaced with almost black
		return img

	""" Opens a file, checks it orientation and rotates appropriately, saves, and closes.
		This should only be done when files are first imported, as it's unnecessary later. """
	def correct_orientation (self):
		try:
			image = PIL_Image.open(self.file)
			for orientation in ExifTags.TAGS.keys():
				if ExifTags.TAGS[orientation]=='Orientation':
					break
			exif = dict(image._getexif().items())

			if exif[orientation] == 3:
				image = image.rotate(180, expand=True)
			elif exif[orientation] == 6:
				image = image.rotate(270, expand=True)
			elif exif[orientation] == 8:
				image = image.rotate(90, expand=True)
			image.save(self.file)
			image.close()
		except (AttributeError, KeyError, IndexError):
			# cases: image don't have getexif
			pass

	""" Up or downvotes an image """
	def do_rate (self, positive=True, delta=0.2):
		if (positive):
			self.rate += delta
		else:
			self.rate -= delta
		# limit to [0,1] range
		self.rate = max(min(self.rate, 1), -1)

		return self.rate

	def set_rate (self, rate=0):
		self.rate = rate

	def hide (self, hide_state=True):
		self.hidden = hide_state

	""" Adds viewings of this image to a list """
	def was_shown (self, time=0):
		if (time > 0):
			self.shown.append(int(time))  # no need for more precision than int

	def set_shown (self, shown=[]):
		self.shown = list(shown)  # avoids referencing to inbound list object

	""" Gives a default str(this instance) output """
	def __str__ (self):
		return '{0}; rate: {1:.2f}; hidden: {2}; shown: {3}'.format(self.file, self.rate, self.hidden, self.shown)

	""" when pickling, this method provides an alternative to the regular __dict__ function """
	def __getstate__ (self):
		state = self.__dict__.copy()
		# get rid of any unpicklable elements (e.g., image objects, pygame surfaces, file handlers)
		state['image']     = {'full': None}
		state['is_loaded'] = False  # triggers a reload after unpickling
		return state


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
		return '(x: {0.x}, y: {0.y}, z: {0.z:.2f}, w: {0.w:.2f})'.format(self)


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

		self.pos            = Vector4(0,0,0,0)  # x, y, timestamp, magnitude
		self.last_pos       = Vector4(0,0,0,0)  # idem, for last time update() was called
		self.state          = self.REST
		self.drag           = []           # list of positions, empty if no drag active
		self.last_touch     = time.time()  # timestamp of last time user touched the screen (set to now)
		self.time_now       = time.time    # use a reference to avoid issues in touch_handler
		self.activity_start = None         # timestamp to track length of interacting with device
		#self.last_update    = 0            # timestamp of last time update() was called

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

		if (sys.platform == 'darwin'):
			self.mock_pos     = (0, 0)
			self.mock_pressed = False
			self.mock_event   = TS_RELEASE

		# run polling in another thread that calls touch_handler whenever an event comes in
		self.ts.run()

	def update (self):
		now = time.time()

		# handle touchscreen events

		# for a mock run, get input another way
		if (sys.platform == 'darwin'):
			self.mock_touch_generator()

		# if last touch event was long ago (> n seconds), set to resting state
		if (self.last_touch < now - 0.25 and self.state != self.DRAGGING):
			self.state = self.REST
		elif (self.state != self.REST and self.state < self.RELEASED):
			# begin activity tracking if not done yet
			if (self.activity_start is None):
				self.activity_start = now

			# calculate magnitude in pixels (essentially distance covered since last update)
			self.pos.w = sqrt(pow(self.last_pos.x - self.pos.x, 2) + pow(self.last_pos.y - self.pos.y, 2))
		
		# if no new activity is detected after n seconds, count the activity as over
		if (self.activity_start is not None and self.last_touch < now - 15):
			activity_length = self.last_touch - self.activity_start
			# if significant/long enough, log this activity
			if (activity_length > 2):
				self.core.data.log_action('touches', '{0} sec, in {1}'.format(int(activity_length), self.core.get_active().get_name()))
			# reset tracker
			self.activity_start = None
			
		# handle pygame event queue
		events = pygame.event.get()

		for event in events:
			if (event.type is QUIT):
				self.core.set_exit()
			elif (event.type is KEYDOWN):
				if (event.key == K_ESCAPE):
					self.core.set_exit()
				elif (event.key >= 48 and event.key <= 57):
					self.core.set_preferred(event.key - 48)  # adjust range [0-9]
				elif (event.key == K_s):
					self.core.gui.save_screen()
				elif (event.key == K_p):
					self.core.toggle_status_panel()

		# house keeping
		self.last_pos = self.pos.copy()

	def close (self):
		self.ts.stop()

	def get_last_touch (self):
		return self.last_touch

	""" Uses pygame mouse data to feed touch input """
	def mock_touch_generator (self):
		send_event = False

		# do we have focus? if not, let it all go
		if (pygame.mouse.get_focused()):  # True if window has focus
			# is there change?
			pos     = pygame.mouse.get_pos()  # (x, y)
			pressed = pygame.mouse.get_pressed()[0]  # button1
			
			# without change, skip
			if (pos != self.mock_pos or pressed != self.mock_pressed):
				# handle this event
				self.mock_pos     = pos
				self.mock_pressed = pressed
				
				if (pressed):
					if (self.mock_event == TS_RELEASE):
						self.mock_event = TS_PRESS
					elif (self.mock_event >= TS_PRESS):
						self.mock_event = TS_MOVE
					send_event = True
				elif (self.mock_event >= TS_PRESS):
					self.mock_event = TS_RELEASE
					send_event = True
		else:
			# without focus, release any ongoing touch (if active)
			if (self.mock_event >= TS_PRESS):
				self.mock_event = TS_RELEASE
				send_event = True

		if (send_event):
			#print(send_event, ['RELEASE','PRESS','MOVE'][self.mock_event], self.mock_pos, self.mock_pressed)
			mock_touch = Touch(0, self.mock_pos[0], self.mock_pos[1])  # slot, x, y
			self.touch_handler(self.mock_event, mock_touch)

	""" this method is called as an event handler """
	def touch_handler(self, event, touch):
		# data in touch: touch.slot, touch.id (uniquem or -1 after release), touch.valid, touch.x, touch.y
		self.last_touch = self.time_now()
		
		# to simplify matters, limit scope to slot 0 (that is, the first finger to touch screen)
		if (touch.slot == 0):
			self.pos.set(touch.x, touch.y, self.last_touch, self.pos.w)
			
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
					distance = sqrt(pow(self.drag[0].x - self.drag[-1].x, 2) + pow(self.drag[0].y - self.drag[-1].y, 2))
					time     = self.drag[-1].z - self.drag[0].z

				# interpret the info
				if (distance > 30):
					# this was a drag, now released
					self.state = self.RELEASED_DRAG
				else:
					if (time < 1.5):
						# this was a tap / click
						self.state = self.RELEASED_TAP
					else:
						# this was a tap and hold
						self.state = self.RELEASED_HOLD
		elif (touch.slot == 5 and event == TS_RELEASE):
				# a six finger press will go to the next program
				self.core.set_next_program()


"""
The GUI class abstracts away most of the particulars of the graphics stack.
This means that all programs should call methods of this class rather than
directly operating on the screen or using pygame methods.
"""
class GUI ():
	def __init__ (self, core=None):
		self.core         = core
		self.dirty        = True  # True if display should be refreshed
		self.dirty_full   = True  # True if FULL display should be refreshed
		self.dirty_areas  = []    # partial display updates can indicate pygame rectangles to redraw
		self.display_size = (800,480)
		self.screenshot_counter = 0

		self.colors = {
			'foreground'  : pygame.Color(255, 255, 255),  # white
			'background'  : pygame.Color(  0,   0,   0),  # black
			'support'     : pygame.Color(220,   0,   0),  # red
			'support-dark': pygame.Color(150,   0,   0),  # dark red
			'good'        : pygame.Color(  0, 180,  25),  # green
			'subtle'      : pygame.Color( 90,  90,  90)   # grey
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

	def draw_rectangle (self, o='center', x=-1, y=-1, w=20, h=20, c='support', a=1, r=True, surf=None, onto=None):
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

		if (onto != None):
			# draw onto the provided surface
			onto.blit(rectangle_surface, rectangle_rect)
		else:
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

	def draw_slider (self, o='center', x=-1, y=-1, w=100, h=20, r=.5, fg='support', bg='background', is_ui=False, a=1):
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

		# add handles if it's a UI slider
		if (is_ui and r*w > 20):
			handle_xpos = xpos + r*w
			handle_ypos = ypos + h/2
			self.draw_rectangle(o='center', x=handle_xpos -  5, y=handle_ypos, w=2, h=0.7*h, c='foreground', a=0.4, r=False)
			self.draw_rectangle(o='center', x=handle_xpos - 10, y=handle_ypos, w=2, h=0.7*h, c='foreground', a=0.4, r=False)
			self.draw_rectangle(o='center', x=handle_xpos - 15, y=handle_ypos, w=2, h=0.7*h, c='foreground', a=0.4, r=False)

		# set flags
		self.dirty = True

	""" Helper function to draw text on screen """
	def draw_text (self, text="", o='center', x=-1, y=-1, has_back=True, padding=2, fg='foreground', bg='background', s='small', onto=None):
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

		if (onto != None):
			# draw onto the provided surface
			onto.blit(text_surface, text_rect)
		else:
			# finally, draw text (onto background)
			self.screen.blit(text_surface, text_rect)

			# set flags
			self.dirty = True
			self.dirty_areas.append(text_rect)

	def draw_image (self, img=None, o='center', pos=(0.5,0.5), size=(1,1), mask=None, a=1, rs=True, fill=False, sq=False, ci=False, smooth=True):
		# decide on place and size
		img_size = size
		if (rs):  # size is relative to screen
			img_size = (size[0] * self.display_size[0], size[1] * self.display_size[1])
		# get image (returns resized, size_string)
		img_scaled = img.get(img_size, fill_box=fill, fit_to_square=sq, circular=ci, smooth=smooth)[0]

		# determine position
		xpos = int(pos[0] * self.display_size[0])
		ypos = int(pos[1] * self.display_size[1])
		if (o == 'center'):
			xpos = xpos - img_scaled.get_width() / 2
			ypos = ypos - img_scaled.get_height() / 2

		# set alpha (always set, to avoid remnant settings causing trouble)
		img_scaled.set_alpha(min(max(a*255,0),255), pygame.RLEACCEL)

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

	def open_simple_image (self, file, keep_transparency=False, remove_black=False):
		img = pygame.image.load(file)
		if (remove_black):
			img.set_colorkey([0,0,0], pygame.RLEACCEL)
		if (keep_transparency):
			return img.convert_alpha()
		# return converted to current display layout for improved performance
		return img.convert()

	def draw_simple_image (self, img=None, o='left', pos=(0.5,0.5), onto=None):
		size = (img.get_width(), img.get_height())
		
		# determine position
		xpos = int(pos[0] * self.display_size[0])
		ypos = int(pos[1] * self.display_size[1])
		# use target surface instead if specified
		if (onto != None):
			xpos = int(pos[0] * onto.get_width())
			ypos = int(pos[1] * onto.get_height())
		# adjust to position image relative to its center
		if (o == 'center'):
			xpos = xpos - size[0] / 2
			ypos = ypos - size[1] / 2

		if (onto != None):
			# draw onto the provided surface
			onto.blit(img, (xpos, ypos))
		else:
			# draw to screen
			affected_rect = self.screen.blit(img, (xpos, ypos))

			# set flags
			self.dirty = True
			self.dirty_areas.append(affected_rect)

	""" Returns pygame image of QR code """
	def get_qrcode_image (self, string="no-data"):
		qr = qrcode.QRCode(
			version=None,
			error_correction=qrcode.constants.ERROR_CORRECT_L,
			box_size=5,
			border=0
		)
		qr.add_data(string)
		qr.make(fit=True)

		# qr_image is a Pil Image object
		qr_image = qr.make_image(fill_color="white", back_color="black")

		# convert to pygame Surface and return
		return pygame.image.fromstring(qr_image.tobytes(), qr_image.size, qr_image.mode).convert()

	def save_screen (self):
		while (os.path.exists(str(self.screenshot_counter) + '.png')):
			self.screenshot_counter += 1
		
		pygame.image.save(self.screen, str(self.screenshot_counter) + '.png')


class ProgramBase ():
	def __init__ (self, core=None):
		# general variables
		self.core         = core
		self.gui          = core.gui
		self.dsize        = core.gui.display_size
		self.is_active    = False
		self.active_since = time.time()
		self.last_update  = 0  # seconds since epoch
		self.dirty        = True
		self.first_run    = True
		self.max_time     = 3600 # in seconds
		self.shown        = []   # list, each item denotes for how long program has been active

		# status panel variables
		self.current_address          = ''
		self.current_address_text     = ''
		self.address_qr_image         = self.gui.get_qrcode_image('http://project.sinds1984.nl')
		self.status_panel_pos         = -32
		self.status_panel_neutral_pos = -32
		self.status_panel_active      = False
		self.status_open              = False
		self.po                       = 0
		self.por                      = 0

	def get_name (self):
		return self.__class__.__name__

	""" any conditions that prevent this program from working should be checked prior to becoming active """
	def can_run (self):
		return True

	""" code to run every turn, needs to signal whether a gui update is needed """
	def update (self, dirty=True, full=False, ignore=False):
		# use local variables so these can be adjusted
		my_dirty  = dirty
		my_full   = full
		my_ignore = ignore

		# update the status panel state
		st = self.update_status_panel()

		# ensure the requested updates from the status panel are incorporated
		if (st > 0):
			my_dirty  = True
			my_ignore = False
		if (st == 2):
			my_full  = True

		# if this update is to be ignored, exit rightaway
		if (my_ignore):
			return

		# always trigger update in absence of better judgement
		if (my_full):
			self.gui.set_dirty_full()
		elif (my_dirty):
			self.gui.set_dirty()
		# update time since last update
		self.last_update = time.time()
		# set other variables
		self.dirty = False
		if (self.first_run):
			self.first_run = False

	""" updates logic for status panel """
	def update_status_panel (self):
		interactive           = False
		now                   = time.time()
		settle_status_panel_pos = False
		
		# is state interactive?
		if (self.core.input.state > self.core.input.REST):
			self.dirty  = True
			interactive = True

		# check if the bottom bar is used to drag
		if (self.core.input.state >= self.core.input.DRAGGING):
			relative_y = abs(self.core.input.drag[0].y - (self.status_panel_neutral_pos + 16))
			if (relative_y < 22):  # 16px (half height of bar) + 6px margin
				self.status_panel_active = True
				self.status_panel_pos    = 480 * (self.core.input.pos.y / self.gui.display_size[1]) - 16
				self.status_open       = (self.status_panel_pos > 0)

				# once released, ensure the bottom bar goes either up or down
				if (self.core.input.state == self.core.input.RELEASED_DRAG):
					settle_status_panel_pos = True
					
					# decide on neutral position - depends on the edge that is closer (values + 2px margin)
					self.status_panel_neutral_pos = 482 * round(self.core.input.pos.y / self.gui.display_size[1]) - 34
			else:
				if (self.status_panel_active):
					settle_status_panel_pos = True
		else:
			if (self.status_panel_active):
				settle_status_panel_pos = True

		# bring bottom bar position back to default position, without abrupt change
		if (self.status_panel_active and settle_status_panel_pos):
			# get extra amount over neutral position, and take a portion of that off
			self.status_panel_pos = self.status_panel_pos + 0.2 * (self.status_panel_neutral_pos - self.status_panel_pos)

			# set the status screen status based on the bottom bar position
			self.set_status_panel_state(self.status_panel_neutral_pos > 0)

			# implement a stopping rule
			if (abs(self.status_panel_pos - self.status_panel_neutral_pos) < 0.1):
				self.status_panel_pos = self.status_panel_neutral_pos
				self.status_panel_active = False

		# if the status panel is open, update its UI code
		if (self.status_open):
			# calculate y-position offset due to moving bar
			self.po  = round(self.status_panel_pos - 448)  # in pixels
			self.por = self.po / 480                     # relative: [0..1]
			
			# check if input is given to adjust screen brightness
			if (self.core.input.state >= self.core.input.DRAGGING):
				# first check if all this actually started close to the slider
				start_x = self.core.input.drag[0].x
				start_y = abs(self.core.input.drag[0].y - (54 + self.po))  # 54 is middle of slider y-position
				if (start_x > 459 and start_y < 15):
					# 459 is left edge, 331 is 341 range - 10 edge margin (so it's easier to get 100%)
					value = round(100 * max(min((self.core.input.pos.x - 459) / 331, 1), 0))
					self.core.set_display_brightness(value, True)

			# also check for button (128x128px) presses
			if (self.core.input.state == self.core.input.RELEASED_TAP):
				# first check if tap is within the vertical range
				if (self.core.input.pos.y > (288 + self.po) and self.core.input.pos.y < (416 + self.po)):
					# check for program buttons
					if (self.core.input.pos.x > 40 and self.core.input.pos.x < 168):
						self.core.set_preferred(1)
					elif (self.core.input.pos.x > 188 and self.core.input.pos.x < 316):
						self.core.set_preferred(2)
					elif (self.core.input.pos.x > 336 and self.core.input.pos.x < 464):
						self.core.set_preferred(3)
					elif (self.core.input.pos.x > 484 and self.core.input.pos.x < 612):
						self.core.set_preferred(0)

			if (self.core.input.state == self.core.input.RELEASED_HOLD):
				# first check if tap is within the horizontal range (with a 10px margin either way)
				if (self.core.input.pos.x > 670 and self.core.input.pos.x < 712):
					# check for restart button
					if (self.core.input.pos.y > (295 + self.po) and self.core.input.pos.y < (347 + self.po)):
						self.core.set_exit()
					# check for power button
					elif (self.core.input.pos.y > (357 + self.po) and self.core.input.pos.y < (409 + self.po)):
						self.core.set_exit(shutdown=True)

			# check if IP is still current
			new_address = self.core.network.get_ip_address()
			if (new_address != self.current_address):
				if (new_address is False):
					self.current_address      = 'project.sinds1984.nl'
					self.current_address_text = 'No network available'
				else:
					self.current_address      = new_address
					self.current_address_text = 'IP: ' + new_address
				self.address_qr_image = self.gui.get_qrcode_image('http://' + self.current_address)

		# update on change or every 1/4 second
		if (self.status_panel_active):
			return 2  # full update required
		elif (self.dirty or now > self.last_update + 0.25):
			return 1  # regular update required
		return 0      # no update required

	""" code to run when program becomes active """
	def make_active (self):
		self.is_active    = True
		self.active_since = time.time()  # now
		self.dirty        = True
		self.first_run    = True
		self.gui.set_dirty_full()

		# --- status panel surface initialisation
		
		self.status_panel = pygame.Surface((800, 480))
		self.status_panel.fill(self.gui.colors['background'])
		# because panel surface also includes the fullscreen black background, draw the bottom bar on top
		self.gui.draw_rectangle(o='left', x=0, y=448, w=800, h=32, r=False, onto=self.status_panel)
		# add identifier and version
		self.gui.draw_text("status", o='left', x=40, y=6+448, fg='foreground', has_back=False, onto=self.status_panel)
		self.gui.draw_text("v{0}".format(version), o='left', x=770, y=6+448, fg='support-dark', has_back=False, onto=self.status_panel)

		# draw status panel icons
		icon_clock       = self.gui.open_simple_image('assets/icon_clock_b.png')
		icon_crosshair   = self.gui.open_simple_image('assets/icon_crosshair_b.png')
		icon_dashboard   = self.gui.open_simple_image('assets/icon_dashboard_b.png')
		icon_diskette    = self.gui.open_simple_image('assets/icon_diskette_b.png')
		icon_half_moon   = self.gui.open_simple_image('assets/icon_half_moon_b.png')
		icon_image       = self.gui.open_simple_image('assets/icon_image_b.png')
		icon_sun         = self.gui.open_simple_image('assets/icon_sun_b.png')
		icon_thermometer = self.gui.open_simple_image('assets/icon_thermometer_b.png')
		icon_wifi        = self.gui.open_simple_image('assets/icon_wifi_b.png')
		icon_restart     = self.gui.open_simple_image('assets/icon_restart_b.png')
		icon_power       = self.gui.open_simple_image('assets/icon_power_b.png')
		button_128       = self.gui.open_simple_image('assets/button_128.png')
		handle           = self.gui.open_simple_image('assets/icon_more_r.png')

		self.gui.draw_simple_image(handle, o='center', pos=(0.5,  0.967), onto=self.status_panel)
		self.gui.draw_simple_image(icon_image,         pos=(0.05,  0.08), onto=self.status_panel)
		self.gui.draw_simple_image(icon_diskette,      pos=(0.05,  0.21), onto=self.status_panel)
		self.gui.draw_simple_image(icon_clock,         pos=(0.05,  0.34), onto=self.status_panel)
		self.gui.draw_simple_image(icon_crosshair,     pos=(0.295, 0.08), onto=self.status_panel)
		self.gui.draw_simple_image(icon_dashboard,     pos=(0.295, 0.21), onto=self.status_panel)
		self.gui.draw_simple_image(icon_thermometer,   pos=(0.295, 0.34), onto=self.status_panel)
		self.gui.draw_simple_image(icon_sun,           pos=(0.52,  0.08), onto=self.status_panel)
		self.gui.draw_simple_image(icon_wifi,          pos=(0.52,  0.34), onto=self.status_panel)

		# draw guidance for adding photos text
		self.gui.draw_text('To add photos, go to the address below', o='left', x=459, y=100, has_back=False, onto=self.status_panel)
		self.gui.draw_text('or scan the QR code with your phone',    o='left', x=459, y=120, has_back=False, onto=self.status_panel)

		# draw status panel permanent buttons
		self.gui.draw_simple_image(button_128,       pos=(0.05,  0.6), onto=self.status_panel)
		self.gui.draw_simple_image(button_128,       pos=(0.235, 0.6), onto=self.status_panel)
		self.gui.draw_simple_image(button_128,       pos=(0.42,  0.6), onto=self.status_panel)
		self.gui.draw_simple_image(button_128,       pos=(0.605, 0.6), onto=self.status_panel)
		self.gui.draw_simple_image(button_128,       pos=(0.79,  0.6), onto=self.status_panel)
		self.gui.draw_rectangle(x=0.87, y=0.734, w=118, h=2, onto=self.status_panel)

		self.gui.draw_simple_image(icon_half_moon, o='center', pos=(0.13,  0.734), onto=self.status_panel)
		self.gui.draw_simple_image(icon_half_moon, o='center', pos=(0.315, 0.734), onto=self.status_panel)
		self.gui.draw_simple_image(icon_half_moon, o='center', pos=(0.50,  0.734), onto=self.status_panel)
		self.gui.draw_simple_image(icon_half_moon, o='center', pos=(0.685, 0.734), onto=self.status_panel)
		self.gui.draw_simple_image(icon_half_moon, o='center', pos=(0.685, 0.734), onto=self.status_panel)
		self.gui.draw_simple_image(icon_restart,   o='center', pos=(0.87,  0.669), onto=self.status_panel)
		self.gui.draw_simple_image(icon_power,     o='center', pos=(0.87,  0.798), onto=self.status_panel)

	""" code to run when this program ceases to be active """
	def make_inactive (self):
		self.is_active = False
		# keep track of activity, no need for more precision than int
		time_active = int(time.time() - self.active_since)
		if (time_active > 0):  # avoid adding arbitrarily small moments of use
			self.shown.append({'since': int(self.active_since), 'duration': time_active})
		self.core.data.set_dirty()

		# reset status panel state and clear related surfaces
		self.set_status_panel_state(False, force=True)
		self.status_panel = None

		self.dirty     = False
		self.first_run = True
		self.gui.set_dirty_full()

	def close (self):
		if (self.is_active):
			self.make_inactive()

	""" by default, no draw calls are made except for the status panel """
	def draw (self):
		# status panel bottom bar
		if (self.status_panel_pos > -32):
			self.gui.draw_surface(self.status_panel, o='left', x=0, y=self.status_panel_pos - 448, r=False)

		if (self.status_open):
			# number of photos in system
			self.gui.draw_text(str(self.core.get_images_count()),       o='left', x=86, y=44 + self.po)

			# storage (% available/used)
			self.gui.draw_slider(o='left', x=86, y=128 + self.po, w=110, h=5, r=(self.core.get_disk_space() / 100.0), bg='subtle')
			self.gui.draw_text(str(self.core.get_disk_space()) + "%",   o='left', x=86, y=106 + self.po)

			# time
			self.gui.draw_text(str(self.core.get_time()),               o='left', x=86, y=169 + self.po)

			# distance (+plus sensor state)
			self.gui.draw_slider(o='left', x=283, y=66 + self.po, w=110, h=5, r=(self.core.get_distance() / 6.5), bg='subtle')
			self.gui.draw_text("{0:.2f} m".format(self.core.get_distance()), o='left', x=283, y=44 + self.po)

			# memory usage
			self.gui.draw_slider(o='left', x=283, y=128 + self.po, w=110, h=5, r=(self.core.get_memory_usage() / 100.0), bg='subtle')
			self.gui.draw_text(str(self.core.get_memory_usage()) + "%", o='left', x=283, y=106 + self.po)

			# temperature
			self.gui.draw_text(str(self.core.get_temperature()) + "ºC", o='left', x=283, y=169 + self.po)
			
			# display brightness
			self.gui.draw_slider(o='left', x=459, y=42 + self.po, w=341, h=24, r=(self.core.get_display_brightness() / 100.0), is_ui=True)
			self.gui.draw_text(str(self.core.get_display_brightness()) + "%", o='left', x=459, y=44 + self.po, has_back=False)

			# network (connected, IP)
			self.gui.draw_text(self.current_address_text,      o='left', x=459, y=169 + self.po)
			self.gui.draw_simple_image(self.address_qr_image, pos=(0.791, 0.313 + self.por))
			

	def get_max_time (self):
		return self.max_time

	""" returns the time this program has been active """
	def get_active_time (self):
		return time.time() - self.active_since

	def set_shown (self, shown=[]):
		self.shown = list(shown)  # list() avoids referencing to inbound list object

	def set_status_panel_state (self, panel_open=False, force=False):
		if (panel_open and (self.status_open is False or force)):
			self.status_panel_neutral_pos = 482 - 34
		if (panel_open is False and (self.status_open or force)):
			self.status_panel_neutral_pos = -34
		if (panel_open != self.status_open):
			self.status_open = panel_open
			self.status_panel_active = True
		if (force):
			self.status_panel_pos = self.status_panel_neutral_pos

	def toggle_status_panel (self):
		self.set_status_panel_state(not self.status_open)


class BlankScreen (ProgramBase):
	def update (self):
		# if user touches screen, get active again (so prepare to leave blank screen)
		# make sure this program gets some time to settle in (ignore input first n seconds)
		if (self.status_open is False and self.active_since < time.time() - 10 and self.core.input.state == self.core.input.RELEASED_TAP):
			self.core.request_switch()

		# generally, do nothing (relies on GUI class providing a blank canvas on first run)
		super().update(ignore=True)

	def draw (self):
		# call draw function to allow drawing default elements if any
		super().draw()


class DualDisplay (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)
		
		self.default_time    = 30  # seconds before switching to next photo
		self.switch_time     = 4   # seconds taken to switch between photos
		self.max_time        = 3.0 * 3600  # n hours
		if (self.core.is_debug):
			self.max_time = 600

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
		self.neutral_pos        = 0.5
		self.picker_plus_surf_n = None
		self.picker_plus_surf_a = None
		self.picker_plus_pos    = 0.5
		self.picker_min_pos     = 0.5
		self.picker_min_surf_n  = None
		self.picker_min_surf_a  = None
		self.picker_alpha       = 1
		self.preferred_image    = None
		self.last_swap          = 0

	def can_run (self):
		if (not self.core.get_images_count() > 20):
			return False
		return True

	def update (self):
		if (self.first_run or self.status_open is False):
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
				start_x = abs(self.core.input.drag[0].x / self.gui.display_size[0] - self.neutral_pos)
				if (start_x < 0.06):
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
				# decide on neutral position - depends on ratings of images
				# each image's rating can sway by [-.1, +.1]
				if (self.im[0]['image'] is not None and self.im[1]['image'] is not None):
					self.neutral_pos = 0.5 + self.im[0]['image'].rate / 10 - self.im[1]['image'].rate / 10
				# get extra amount over neutral position, and take a portion of that off
				self.line_pos = self.line_pos + 0.2 * (self.neutral_pos - self.line_pos)

			# picker position depends on line
			self.picker_plus_pos = self.neutral_pos + 0.8 * (self.line_pos - self.neutral_pos)
			self.picker_min_pos  = self.neutral_pos + 1.2 * (self.line_pos - self.neutral_pos)

			# if user indicates a clear preference, go with that
			# this means a drag of the line crosses a threshold (position away from centre)
			if (self.line_pos < 0.15 or self.line_pos > 0.85):
				# set up for that
				self.preferred_image = int(self.line_pos < self.neutral_pos)  # 1 or 0, if line > 0.5

				# do actual rating and swap (if at least some time has past to avoid glitches because of hanging input)
				if (check_for_swap_over and self.last_swap < now - 0.5):
					# rate both images
					self.im[0]['image'].do_rate(self.preferred_image == 0)  # True if line is far right, False otherwise
					self.im[1]['image'].do_rate(self.preferred_image == 1)  # vice versa, True if far left

					# log this action
					log_value = self.im[0]['image'].file
					log_value += (' > ',' < ')[self.preferred_image]
					log_value += self.im[1]['image'].file
					self.core.data.log_action('dd.rate', log_value)

					# give feedback (both for rating, and swap)
					# get one image to fade quickly and swap over
					self.im[ abs(self.preferred_image - 1) ]['swap'] = True
					self.last_swap = now

				self.dirty = True
			else:
				self.preferred_image = None

			# make sure any meaningful change in line position is registered as change
			# cutoff value is ~ 1.0/800
			if (abs(self.line_pos - self.last_line_pos) > 0.0015):
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
					i['image']     = self.core.images.get_next()
					i['image_new'] = self.core.images.get_next()
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
							self.core.data.set_dirty()
							# free memory and report time since it appeared
							i['image'].unload( i['since'] )
						
						# reassign and reset timers, etc.
						i['swap']      = False
						i['image']     = i['image_new']
						i['image_new'] = self.core.images.get_next()  # decide on new image early
						i['alpha']     = 0
						i['since']     = now
						i['max_time']  = self.default_time
						
						# adjust max time in case the two sides are too close together for swapping
						# ideal is for each side to swap at halfway duration of the other
						if (index == 1):
							t1 = self.im[0]['since'] + self.im[0]['max_time']
							t2 = self.im[1]['since'] + self.im[1]['max_time']
							if (abs(t1-t2) < self.default_time / 2):
								i['max_time'] += 1
					
					self.dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (self.dirty):
			super().update(full=True)
		else:
			super().update(ignore=True)

	def make_active (self):
		# draw the picker surfaces in advance for later reference
		self.picker_plus_surf_n = self.gui.open_simple_image('assets/icon_arrow_up_w.png',   remove_black=True)
		self.picker_plus_surf_a = self.gui.open_simple_image('assets/icon_arrow_up_r.png',   remove_black=True)
		self.picker_min_surf_n  = self.gui.open_simple_image('assets/icon_arrow_down_w.png', remove_black=True)
		self.picker_min_surf_a  = self.gui.open_simple_image('assets/icon_arrow_down_r.png', remove_black=True)

		super().make_active()

	def make_inactive (self):
		# reset variables to None to free memory
		self.picker_plus_surf_n = None
		self.picker_plus_surf_a = None
		self.picker_min_surf_n  = None
		self.picker_min_surf_a  = None

		for i in self.im:
			if (i['image'] is not None):
				i['image'].unload( i['since'] )
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
				self.gui.draw_rectangle(x=self.line_pos, y=-1, w=width, h=3, c='foreground',
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

		# call draw function to allow drawing default elements if any
		super().draw()


class PhotoSoup (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)

		self.max_time             = 3.0 * 3600  # n hours
		if (self.core.is_debug):
			self.max_time = 600

		self.base_constant        = 1
		self.base_size            = 1
		self.default_num_images   = 3
		self.goal_num_images      = 3    # starting number of images shown on-screen
		self.min_num_images       = 2    # minimum number of images shown on-screen
		self.max_num_images       = 6    # max number of images shown on-screen
		if (self.core.is_debug):
			self.max_num_images = 11
		self.last_image_addition  = 0    # timestamp
		self.time_to_pass_sans_ix = 900  # test 20, ideal 900
		self.time_before_addition = 2700 # test 30, was 1800
		if (self.core.is_debug):
			self.time_to_pass_sans_ix = 20
			self.time_before_addition = 45
		self.images               = []
		self.active_image         = None
		self.center               = Vector4(0.5*self.dsize[0], 0.5*self.dsize[1], 0, 0)
		self.button_add_photo     = self.gui.open_simple_image('assets/icon_plus.png', keep_transparency=True)

	def can_run (self):
		if (not self.core.get_images_count() > 20):
			return False
		return True

	def update (self):
		if (self.first_run or self.status_open is False):
			now = time.time()

			# determine base factor - - - - - - - - - - - - - - - - - - -

			# base factor is dependent on the number of images that have entered view
			# it will only increase significantly once images are reduced
			"""
			GUIDELINE:
			.8 ~  3 images
			.6 ~  5 images
			.4 ~  9 images
			.3 ~ 11 images
			"""
			# image factor --- simple linear relation to approximate guide values
			# use a minimum number of images of one, to avoid divide by zero
			self.base_constant = 2.3 / max(len(self.images),1) + 0.1

			# time factor --- base factor gets smaller as the time since the last interaction gets longer
			# uses the formula 60/x - 1, with outcome limited to [-1,0.5]
			# (although lower limit of formula only approaches -1)
			#self.base_constant += 0.15 * min(max(60.0 / (now - self.core.get_last_ix()) - 1, -0.7), 0.5)

			# distance factor --- base factor gets increased with low distance
			# uses the formula -.8*x + 1.2, with limits [0, 0.5]
			#self.base_constant += 0.3 * min(max(-0.8 * self.core.get_distance() + 1.2, 0), 0.5)

			# adjust base size (rescale from base factor, with limits to avoid sizing errors)
			new_size = min(max(0.8 * self.base_constant, 0.1), 2)
			# this line makes sure the base size gradually moves from one value to another
			self.base_size = self.base_size + 0.2 * (new_size - self.base_size)

			# adjust goal number of images (depends on time since last interaction)
			# also, this won't be done if user interaction was recent
			if (self.core.get_last_ix() < now - self.time_to_pass_sans_ix and self.last_image_addition < now - self.time_before_addition):
				# add one, but have an upper limit
				self.goal_num_images = min(self.goal_num_images + 1, self.max_num_images)

			# handle user interactivity - - - - - - - - - - - - - - - - -

			# handle add photo button tap
			if (self.core.input.state == self.core.input.RELEASED_TAP
				and self.core.input.pos.x < 90 and self.core.input.pos.y > 400):
				# ensure there is a little timeout before adding another photo
				if (self.last_image_addition < now - 0.5):
					self.goal_num_images = min(self.goal_num_images + 1, self.max_num_images)

					# log this action
					self.core.data.log_action('ps.add', 'new total of {0} images'.format(len(self.images)))
			
			# image interactions
			if (self.core.input.DRAGGING <= self.core.input.state < self.core.input.RELEASED):
				if (self.active_image is None):
					# 1. check if dragging started over image
					# find image closest to drag position
					closest_distance = 9999  # very high number that's sure to be met
					closest_image    = None
					for i in self.images:
						distance = self.get_distance(self.core.input.pos, i['v'])
						# if closest so far and distance < image radius, we have a match
						if (distance < closest_distance and distance < self.get_diameter(i)/2.0):
							closest_distance = distance
							closest_image    = i

					if (closest_image is not None):
						self.active_image = closest_image
						self.active_image['user_control'] = True
						self.active_image['user_last_ix'] = now

						# also put this image to the end of the images list, so it gets drawn on top
						swapIndex = self.images.index(self.active_image)
						self.images[-1], self.images[swapIndex] = self.images[swapIndex], self.images[-1]
				else:
					# so we already have an active image
					self.active_image['user_last_ix'] = now

					# 2. pull the center of that image towards user position (image follows touch)
					# set angle towards touch position
					self.active_image['v'].z = self.get_angle(self.active_image['v'], self.core.input.pos)
					# set speed to recent touch movement magnitude
					self.active_image['v'].w = self.core.input.pos.w
				
			elif (self.core.input.state >= self.core.input.RELEASED):
				if (self.active_image is not None):
					# 3. once drag is released, let angle and trajectory be the same as recent trajectory
					# ^ so don't update here
					self.active_image['user_control'] = False
					self.active_image = None
			
			# image updates below - - - - - - - - - - - - - - - - - - - -

			# if goal has increased, add an image slot
			if (self.goal_num_images > len(self.images)):
				self.images.append({
					'image'       : None,
					'since'       : now,
					'v'           : Vector4(0, 0, 0, 0),
					'size'        : 1,
					'user_control': False,  # False
					'user_last_ix': 0       # timestamp of last interaction
				})
				# keep track of time
				self.last_image_addition = now

			# do per image updating
			for i in self.images:
				# if new or moved out of screen range, renew
				if (i['image'] is None or not self.is_on_sceen(i)):
					if (self.goal_num_images >= len(self.images)):
						# cleanup if possible
						if (i['image'] is not None):
							i['image'].unload( i['since'] )  # report time since it appeared

						# a regular, non-user-touched image will just disappear and be renewed
						# an image that was recently touched (< n seconds ago) will disappear without replacement
						if (now - i['user_last_ix'] < 10):
							# avoid replacement by reducing desired number of images
							self.goal_num_images = max(self.goal_num_images - 1, self.min_num_images)
							
							# also rate this image down
							i['image'].do_rate(False, 0.1)

							# to maintain balance, the other images currently visible get uprated slightly
							uprating = 0.1 / (len(self.images) - 1)
							for other_img in self.images:
								if (other_img is not i):
									other_img['image'].do_rate(True, uprating)

							# log this action
							self.core.data.log_action('ps.flung', '{0}, amid {1} images'.format(i['image'].file, len(self.images)))

							# remove this image slot (mimics code below)
							i['image'].unload( i['since'] )  # report time since it appeared
							self.images.remove(i)

						else:
							# renew this image slot
							i['image'] = self.core.images.get_next()
							i['since'] = now
							# set x, y, direction, speed
							i['v'].set(
								random.random() * self.dsize[0],
								random.random() * self.dsize[1],
								2 * pi * random.random(),
								max(1.3 * random.random(), 0.15))
					else:
						# remove this image slot to free memory
						i['image'].unload( i['since'] )  # report time since it appeared
						self.images.remove(i)

					self.dirty = True
				# else, update the current image's position, size, etc.
				else:
					# adjust the size
					i['size'] = 1 + (i['image'].rate / 3.0)  # potential range is thus [0.66, 1.33]

					# non-user-controlled images update based on relative position to other images
					if (not i['user_control']):
						# adjust angle if far from center (aim to pull it in to avoid images huddling at edge)
						# this is primarily a problem with large images ~ a small number
						if (len(self.images) <= 4):
							# get angle towards the center of screen
							center_angle    = self.get_angle(i['v'], self.center)
							# distance from center -> factor of the current angle's adjustment to the center angle
							center_distance = self.get_distance(i['v'], self.center)
							# only continue to adjust if distance is close to edge
							if (center_distance > 0.9 * self.dsize[1]):
								# factor is limited to .01 to avoid abrupt changes
								center_factor   = min(max(1.0 * center_distance / self.dsize[1], 0), 0.01)
								# update the angle accordingly
								i['v'].z = (1 - center_factor) * i['v'].z + center_factor * center_angle

					# for all images, calculate the base vector (with magnitude w, angle z)
					vi_x = i['v'].w * cos(i['v'].z)
					vi_y = i['v'].w * sin(i['v'].z) * -1  # -1 because -y is up

					# calculate influence of other images
					if (not i['user_control']):
						"""
						each other image has influence, through attraction Fa and repulsion Fr
						those two forces are from x,y towards the other x,y with radian angle ß and -ß
						so the sum of the two forces influence the default force
						"""
						for img in self.images:
							if (img is not i):
								# calculate influence
								f = self.get_force_attraction(i, img) - self.get_force_repulsion(i, img)
								a = self.get_angle(i['v'], img['v'])

								# add this vector to the base
								vi_x += f * cos(a)
								vi_y += f * sin(a) * -1
								#print(round(vi_x), round(vi_y), f, a)

					# for all, add the resultant vector to get the new position
					#print('3', vi_x, vi_y)
					i['v'].x += vi_x
					i['v'].y += vi_y

					if (vi_x != 0 or vi_y != 0):
						self.dirty = True

		# indicate update is necessary, if so, always do full to avoid glitches
		if (self.dirty):
			super().update(full=True)
		else:
			super().update(ignore=True)

	def make_inactive (self):
		# reset variables to None to free memory
		for i in self.images:
			if (i['image'] is not None):
				i['image'].unload( i['since'] )
		self.images = []
		self.goal_num_images = self.default_num_images
		super().make_inactive()

	def is_on_sceen (self, a):
		arad = 0.5 * self.get_diameter(a)
		if (a['v'].x + arad < 0 or a['v'].x - arad > self.dsize[0] or a['v'].y + arad < 0 or a['v'].y - arad > self.dsize[1]):
			return False
		return True

	def get_angle (self, a, b):
		dx = b.x - a.x
		dy = a.y - b.y
		return atan2(dy, dx)

	def get_distance (self, a, b):
		return sqrt(pow(b.x - a.x,2) + pow(a.y - b.y ,2))

	def get_diameter (self, a):
		return a['size'] * self.base_size * self.dsize[1]

	""" attractive force scales linearly with the distance between a and b """
	def get_force_attraction (self, a, b):
		if (a['user_control'] or b['user_control']):
			return -0.0002 * self.get_distance(a['v'], b['v'])
		return 0.0001 * self.get_distance(a['v'], b['v'])

	def get_force_repulsion (self, a, b):
		distance = self.get_distance(a['v'], b['v'])
		# substract sum of radii in pixels, so distance is calculated for closest edges
		distance -= (self.get_diameter(a) + self.get_diameter(b)) / 2.0
		
		# avoid divide by zero problems (and very small distances, thus large forces)
		if (distance < 0.05):
			distance = 0.05

		# force is inversely related to distance
		return 0.005 / pow(distance, 2)

	def draw (self):
		for i in self.images:
			xpos = i['v'].x / self.dsize[0]
			ypos = i['v'].y / self.dsize[1]
			size = self.get_diameter(i)
			self.gui.draw_image(i['image'], pos=(xpos, ypos), size=(size, size), rs=False, ci=True, smooth=True)
		
		# draw button on top
		if (self.goal_num_images < self.max_num_images):
			self.gui.draw_simple_image(self.button_add_photo, pos=(0.01, 0.855))

		# call draw function to allow drawing default elements if any
		super().draw()


class PhotoPatterns (ProgramBase):
	def __init__ (self, core=None):
		super().__init__(core)

		self.max_time             = 3.0 * 3600  # n hours
		if (self.core.is_debug):
			self.max_time = 600

		self.default_time    = 30  # seconds before switching to next photo
		self.switch_time     = 4   # seconds taken to switch between photos
		self.im = [
			{
				'image'    : None,
				'image_new': None,
				'alpha'    : 0,
				'since'    : 0,
				'max_time' : self.default_time,
				'swap'     : False
			}
		]
		# add sufficient copies for all images
		for x in range(0,4):
			self.im.append( dict(self.im[0]) )

		self.last_swap = 0

	def can_run (self):
		if (not self.core.get_images_count() > 20):
			return False
		return True

	def update (self):
		if (self.first_run or self.status_open is False):
			interactive = False
			now         = time.time()

			# is state interactive?
			if (self.core.input.state > self.core.input.REST):
				self.dirty  = True
				interactive = True

			# --- default code above ----------

			swapped = False
			for i in self.im:
				if (i['image'] is None or self.first_run or (interactive and self.last_swap < now - 0.5)):
					i['image'] = self.core.images.get_next()
					i['since'] = now
					self.dirty = True
					swapped = True
			if (swapped):
				self.last_swap = now

				# log this action
				#self.core.data.log_action('pp.pick', '{0}, of {1} pattern'.format(i['image'].file, len(self.images)))

		# --- default code below ----------

		# indicate update is necessary, if so, always do full to avoid glitches
		if (self.dirty):
			super().update(full=True)
		else:
			super().update(ignore=True)

	def make_inactive (self):
		# reset variables to None to free memory
		for i in self.im:
			if (i['image'] is not None):
				i['image'].unload( i['since'] )
			if (i['image_new'] is not None):
				i['image_new'].unload()
			i['alpha']    = 0
			i['since']    = 0
			i['max_time'] = self.default_time
			i['swap']     = False
		super().make_inactive()

	def draw (self):
		# draw main image
		self.gui.draw_image(
			self.im[0]['image'],         pos=(0.4, 0.5),   size=(0.8, 1), mask=(0, 0.8125, 0,1), a=1-self.im[0]['alpha'])
		# draw new main image if available
		if (self.im[0]['alpha'] > 0):
			self.gui.draw_image(
				self.im[0]['image_new'], pos=(0.406, 0.5), size=(1,1),    mask=(0, 0.8125, 0,1), a=self.im[0]['alpha'])

		# draw side images
		for index, i in enumerate(self.im):
			if (index == 0):
				continue  # skip the main image
			# draw each image
			self.gui.draw_image(i['image'],         pos=(0.90625, 0.117 + (index-1) * 0.256), size=(0.1875, 0.234),	a=1-i['alpha'])
			if (i['alpha'] > 0):
				self.gui.draw_image(i['image_new'], pos=(0.90625, 0.117 + (index-1) * 0.256), size=(0.1875, 0.234), a=i['alpha'])

		# draw UI overlays if necessary

		# call draw function to allow drawing default elements if any
		super().draw()


# ----- RUN AS MAIN ------------------------------------------------------------

""" Unless this script is imported, do the following """
if __name__ == '__main__':
	main()
