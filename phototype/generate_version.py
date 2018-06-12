#!/usr/bin/python3

from hashlib import md5
from photocore import version as photocore_version
from shutil import copy2

"""
This script saves a copy of the current photocore.py script
and renames that copy based on the version listed within.

The generated file can be uploaded to the designated online
versions folder such that a running Phototype can download and
install newer versions, in effect updating itself.

Note that the uploading step is manual for now. This script could
however be imported and used to automate the process.
"""

def generate ():
	# Copy file and save as latest version
	folder   = 'versions/'
	new_path = '{0}photocore_v{1}.py'.format(folder, photocore_version)

	copy2('photocore.py', new_path)
	print('Copied photocore.py to {0}'.format(new_path))

	# generate checksum and write to file
	with open(new_path) as file_to_check:
		data = file_to_check.read()    
		checksum = md5(data.encode('utf-8')).hexdigest()
		print('Checksum: {0}'.format(checksum))

		with open('{0}photocore_v{1}_checksum.txt'.format(folder, photocore_version), 'w') as f:
			f.write(checksum)

	print('==> DONE <==')


# ----- RUN AS MAIN ------------------------------------------------------------


def main ():
	generate()

""" Unless this script is imported, do the following """
if __name__ == '__main__':
	main()