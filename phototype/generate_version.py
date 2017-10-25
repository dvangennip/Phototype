#!/usr/bin/python3

from hashlib import md5
from photocore import version as photocore_version
from shutil import copy2

# copy file and save as latest version
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