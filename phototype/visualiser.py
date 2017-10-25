#!/usr/bin/python3
# coding: utf-8

# ----- IMPORT LIBRARIES ------------------------------------------------------

import os
import pickle
from photocore import Image

# ----- TODO ------------------------------------------------------------------
"""
all of it
"""
# ----- GLOBAL FUNCTIONS ------------------------------------------------------


folder = '../S4 Data/'

def main():
	current_directory = os.getcwd()
	for p in range (1,12):
		data_folder = os.path.join(current_directory, folder, 'p' + str(p))
		if os.path.exists(data_folder):
			# set current working directory (makes things easier down the track)
			os.chdir(data_folder)
			
			print('-> Visualising p' + str(p))
			
			dv = DataVisualiser(p, data_path='p' + str(p) + '_data.bin')
			#dv.visualise()
			
			print('Done with p' + str(p))

	print('==> DONE <==')


# ----- CLASSES ---------------------------------------------------------------


class DataVisualiser ():
	def __init__ (self, pp=0, data_path=None):
		self.data  = {
			'participant'     : pp,
			'programs'        : [],
			'program_history' : [],
			'images'          : [],
			'images_simple'   : [],
			'interactions'    : [],
			'counts': {
				'max_interactions': 0,
				'dd.rate'         : 0,
				'ps.flung'        : 0,
				'touches'         : 0,
				'images.scan'     : 0
			}
		}
		self.t0 = 0

		# import data
		if os.path.exists(data_path):
			try:
				with open(data_path, 'rb') as f:
					loaded_data = pickle.load(f)
					for key in ('programs', 'images', 'interactions'):
						if (key in loaded_data):
							self.data[key] = loaded_data[key]
			except IOError as eio:
				pass  # called when file doesn't exist (yet), which is fine
			except Exception as e:
				raise e

			# redo the way program data is kept
			#   now: programs: [{'name': 'BlankScreen|StatusProgram|DualDisplay|PhotoSoup', shown: [{'since': timestamp, 'duration': seconds}] }]
			#   thus, programs need sorting first or be drawn on top of each other (layered)
			self.data['program_history'] = []
			for p in self.data['programs']:
				# 4 programs, now iterate over shown list
				for pi in p['shown']:
					self.data['program_history'].append({
						'name'     : p['name'],
						'start'    : pi['since'],
						'timestamp': pi['since'],
						'duration' : pi['duration']
					})
			# sort the program history by start timestamp
			self.data['program_history'] = sorted(self.data['program_history'], key=lambda k: k['start'])

			# adjust data for p4 due to erronuous program entries
			#   those entries are likely from setting up or retrieving before/after deployment
			if (pp == 1):
				self.data['program_history'] = self.data['program_history'][4:]
			if (pp == 4):
				self.data['program_history'] = self.data['program_history'][10:]
			if (pp == 6):
				self.data['program_history'].pop()
			
			# readjust start times based on t0
			self.t0 = self.data['program_history'][0]['start']
			for p in self.data['program_history']:
				p['timestamp'] = p['start'] - self.t0

			# check here for odd starts to the sequence (due early booting being saved?)
			# if (pp==1):
			# 	for ph in self.data['program_history']:
			# 		print(ph['timestamp'])

			# same for interactions
			#   {'timestamp': timestamp, 'action': string, 'value': second|string}
			for i in self.data['interactions']:
				i['timestamp'] = i['timestamp'] - self.t0

				# also count each action towards totals
				if (i['action'] in self.data['counts']):
					self.data['counts'][i['action']] += 1

			# calculate activity intensity per time period, add as a number to program history
			max_interactions = 0
			for p in self.data['program_history']:
				p_start           = p['timestamp']
				p_end             = p['timestamp'] + p['duration']
				p['interactions'] = 0
				# iterate over all interactions, count those that fall within this program instance's duration
				for i in self.data['interactions']:
					if (p_start <= i['timestamp'] < p_end):
						p['interactions'] += 1

				if (p['interactions'] > max_interactions):
					max_interactions = p['interactions']
			# store the max interactions number for future scaling purposes
			self.data['counts']['max_interactions'] = max_interactions

			# use a simpler data structure for image data
			for img in self.data['images']:
				self.data['images_simple'].append({
					'file': img.file,
					'rate': img.rate
				})
			self.data['images_simple'] = sorted(self.data['images_simple'], key=lambda k: k['rate'])

			# exclude peculiar classes first to ease import elsewhere
			del self.data['images']

			# export the data to another pickled binary
			# export with protocol v2 for compatibility with python 2
			with open(data_path.replace('.bin','_processed.bin'), 'wb') as f:
				pickle.dump(self.data, f, protocol=2)
		else:
			print('No data for p' + str(self.data['participant']))

	def visualise (self):
		pass
		# note: skipped in favour of using processing.py


# ----- RUN AS MAIN ------------------------------------------------------------

""" Unless this script is imported, do the following """
if __name__ == '__main__':
	main()