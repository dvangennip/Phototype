#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

from hashlib import md5
from multiprocessing import Process, Queue
from queue import Empty as QueueEmpty
import os
from photocore import Image
import pygame
import time


# ----- CLASSES ---------------------------------------------------------------


class PhotoImporter ():
	def __init__ (self, input_folder='../uploads', output_folder='../images', do_delete=True):
		self.input_folder  = input_folder
		self.output_folder = output_folder
		self.do_delete     = do_delete
		self.last_update   = 0

		self.queue   = Queue()
		self.process = Process(target=self.update)
		self.process.start()

	def update (self):
		# run this while loop forever, unless a signal tells otherwise
		while (True):
			try:
				try:
					# get without blocking (as that wouldn't go anywhere)
					item = self.queue.get(block=False)
					if (item is not None):
						break
				except QueueEmpty:
					pass

				if (time.time() > self.last_update + 10):
					print('Checking for new images...')
					self.load_list()
					self.last_update = time.time()
					print('Waiting...')

				time.sleep(5)
			# ignore any key input (handled by main thread)
			except KeyboardInterrupt:
				pass

		# finally, after exiting while loop, it ends here
		print('Terminating process')

	def close (self):
		# signal it should close
		self.queue.put(True)
		# wait until it does so
		print('Signalled and waiting for importer to close...')
		self.process.join()

	def load_list (self):
		for dirname, dirnames, filenames in os.walk(self.input_folder):
			# editing 'dirnames' list will stop os.walk() from recursing into there
			if '.git' in dirnames:
				dirnames.remove('.git')
			if '.DS_Store' in filenames:
				filenames.remove('.DS_Store')

			# check all filenames, act on valid ones
			for filename in filenames:
				if filename.endswith(('.jpg', '.jpeg')):
					self.check_resize(dirname, filename)

	def check_resize (self, dirname, filename):
		# decide on in/output path
		in_file_path        = os.path.join(dirname, filename)
		in_file_size        = os.stat(in_file_path).st_size
		marked_for_deletion = False

		# consider a unique filename based on original filename and filesize (to avoid same names across folders mixups)
		# use only the first 12 characters to keep it sane / legible
		out_filename = md5(filename.encode('utf-8') + str(in_file_size).encode('utf-8')).hexdigest()[:12] + '.jpg'
		out_file_path = os.path.join(self.output_folder, out_filename)

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
				marked_for_deletion = True

		if (self.do_delete and marked_for_deletion):
			# consider removing the original file
			try:
				print('Deleting:', in_file_path)
				os.remove(in_file_path)
				pass
			except OSError as ose:
				print(ose)

# ----- MAIN ------------------------------------------------------------------


""" Unless this script is imported, do the following """
if __name__ == '__main__':
	print('PhotoImporter starts')
	importer = None
	do_exit  = False
	t = 0

	# initialise all components
	importer = PhotoImporter()

	# program stays in this loop unless called for exit
	while (not do_exit):
		try:
			# pause for a moment after each update
			time.sleep(1)
			
			t += 1
			if (t > 55):
				do_exit = True
		except KeyboardInterrupt:
			do_exit = True

	# finally
	importer.close()
	print('PhotoImporter closes')