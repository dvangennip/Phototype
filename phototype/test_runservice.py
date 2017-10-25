import os
import time

with open('run.log', 'a') as f:
	t = time.strftime("%Y-%m-%d %H:%M:%S - ", time.localtime())
	message = 'Running test_runservice.py, with user: ' + str(os.geteuid()) + ', cwd: ' + os.getcwd()
	f.write(t + message + '\n')