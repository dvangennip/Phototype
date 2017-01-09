#!/usr/bin/python3

# ----- IMPORT LIBRARIES ------------------------------------------------------

from hashlib import md5
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

	def update (self):
		self.load_list()

	def close (self):
		pass

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
	importer = None

	# initialise all components
	importer = PhotoImporter()

	# program stays in this loop unless called for exit
	while (True):
		print('Checking for new images...')
		importer.update()
		
		# pause n seconds after each update
		time.sleep(120)

	# finally
	importer.close()