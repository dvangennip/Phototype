#!/usr/bin/python

# Largely based on SimpleHTTPServer implementation
# via: http://www.opensource.apple.com/source/python/python-3/python/Lib/SimpleHTTPServer.py
# note: BaseHTTPServer is different in Python 3+

from http.server import BaseHTTPRequestHandler
from io import BytesIO
import json
import mimetypes
import os
import posixpath
import re
import shutil
import signal
import socketserver
from threading import Thread
import sys
import threading
import time
from urllib.parse import unquote as url_unquote

# ----- PRIMARY FUNCTIONS --------------------------------------------

class SimpleServer ():
	def __init__ (self, debug=True, port=None, use_signals=True, regular_run=True):
		self.is_debug    = debug
		self.regular_run = regular_run

		if (port is not None):
			self.server_port = port
		elif (len(sys.argv) >= 3 and '-p' in sys.argv[1]):
			# parse command line argument to set port (only -p or --port allowed)
			self.server_port = int(sys.argv[2])
		else:
			self.server_port = 8080  # note: ports < 1024 are not available to unprivileged users

		# initiate server
		print('HTTP server: starting on port ' + str(self.server_port))
		self.server = socketserver.TCPServer(("", self.server_port), ResponseHandler)
		# try to set reuse of the socket
		#  enabling faster restarts without 90sec cooldown
		#  before reuse of socket is allowed
		#server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		# before starting setup hanlding signals to be able to terminate gracefully
		if (use_signals):
			signal.signal(signal.SIGTERM, self.shutdown)  # Terminate
			signal.signal(signal.SIGTSTP, self.shutdown)  # Stop (^Z)
			signal.signal(signal.SIGINT,  self.shutdown)  # Interrupt (^C)

		# run server on separate thread
		self.server_thread = Thread(target=self.server.serve_forever)
		if (self.is_debug):
			print('HTTP server: starting server thread')
		self.server_thread.start()
		self.server.running = True
		
		# do nothing while server is running
		if (self.is_debug):
			print('HTTP server: waiting for requests')
		if (self.regular_run):
			while self.server.running:
				time.sleep(1)

			self.cleanup()

	def shutdown (self, signum=None, frame=None):
		if (self.is_debug):
			print('HTTP server: shutting down server thread')
		self.server.running = False
		self.server.shutdown()  # this stops serve_forever, this is a blocking function

		if (not self.regular_run):
			time.sleep(1)
			self.cleanup()

	def cleanup (self):
		# once running is False, we end up here and terminate the thread
		self.server_thread.join()
		if (self.is_debug):
			print('HTTP server: server thread terminated')

		# do some final cleanup (unbinding port, etc.)
		self.server.server_close()
		print('HTTP server: shut down on port ' + str(self.server_port))


# This class handles the server response
class ResponseHandler (BaseHTTPRequestHandler):
	global version

	server_version = "PiHTTP/" + str(0.1)

	extensions_map = mimetypes.types_map.copy()
	extensions_map.update({
		''     : 'application/octet-stream', # Default
		'.py'  : 'text/plain',
		'.c'   : 'text/plain',
		'.h'   : 'text/plain',
		'.js'  : 'application/javascript',
		'.json': 'application/json',
		'.html': 'text/html',
		'.css' : 'text/css',
		'.png' : 'image/png',
		'.jpg' : 'image/jpeg',
		'.webm': 'video/webm',
		'.mp4' : 'video/mp4',
		'.ogv' : 'video/ogg',
		'.mp3' : 'audio/mp3',
		'.ogg' : 'audio/ogg',
		'.vs'  : 'x-shader/x-vertex',
		'.fs'  : 'x-shader/x-fragment'
		})

	def do_HEAD (self):
		"""Serve a HEAD request. Identical to GET but omits content of file."""
		f = self.send_head()
		if f:
			f.close()

	def do_GET (self):
		"""Serve a GET request."""
		f = self.send_head()
		if f:
			self.copyfile(f, self.wfile)
			f.close()

	def send_head (self):
		"""Common code for GET and HEAD commands.

		This sends the response code and MIME headers.

		Return value is either a file object (which has to be copied
		to the outputfile by the caller unless the command was HEAD,
		and must be closed by the caller under all circumstances), or
		None, in which case the caller has nothing further to do.

		"""
		f              = None
		content_type   = 'text/plain'
		content_length = 0
		
		# decide on static or dynamic response
		if (self.path == '/upload' or self.path == '/upload/'):
			# handle a dynamic response
			f = BytesIO()
			f.write('<html><head><title>Status for %s</title></head>\n' % self.path)
			f.write('<body>\n<h2>Status update</h2>\n')
			f.write('<pre style="white-space: pre-wrap;"><code>%s</code></pre>\n' % json.dumps({'TODO': 'something'}).encode('utf-8') )
			f.write('</body>\n</html>')
			f.seek(0)
			content_type = 'text/html'
			content_length = len(f.getvalue())
		else:
			# handle a static response (return a file)
			path = self.translate_path(self.path)
			if ('/phototype' in path):
				path = path.replace('/phototype','/phototype/uploader')

			if os.path.isdir(path):
				for index in "index.html", "index.htm":
					index = os.path.join(path, index)
					if os.path.exists(index):
						path = index
						break
				else:
					return self.send_error(403, "Nothing to see here")
			content_type = self.guess_type(path)
			if content_type.startswith('text/'):
				mode = 'rb'
			else:
				mode = 'rb'
			try:
				f = open(path, mode)
				content_length = os.stat(path).st_size
			except IOError:
				self.send_error(404, "File not found")
				return None

		# common code to respond
		self.send_response(200)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(content_length))
		#self.send_header("Last-Modified", date_value)
		self.end_headers()
		return f

	def do_POST (self):
		"""Serve a POST request."""
		f = None
		content_type   = 'text/plain'
		content_length = 0

		# handle a dynamic response
		if (self.path == '/upload' or self.path == '/upload/'):
			# first, handle the uploaded data
			result, info = self.handle_post_data()
			#print(result, info)

			f = BytesIO()
			f.write( json.dumps({'success': result, 'info': info}).encode('utf-8') )
			f.seek(0)
			content_type = 'application/json'
			content_length = len(f.getvalue())

		# common code to respond
		self.send_response(200)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(content_length))
		#self.send_header("Last-Modified", date_value)
		self.end_headers()
		
		if f:
			self.copyfile(f, self.wfile)
			f.close()

	# via: see: https://gist.github.com/UniIsland/3346170
	def handle_post_data (self):
		content_type = self.headers['content-type']
		if not content_type:
			return (False, "Content-Type header doesn't contain boundary")
		
		boundary = content_type.split("=")[1].encode()
		remaining_bytes = int(self.headers['content-length'])
		line = self.rfile.readline()
		remaining_bytes -= len(line)
		if not boundary in line:
			return (False, "Content does NOT begin with boundary")
		
		line = self.rfile.readline()
		remaining_bytes -= len(line)
		filename = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
		if not filename:
			return (False, "Can't find out file name...")
		
		path = self.translate_path(self.path)
		#print(self.path, path)
		if (self.path == '/upload'):
			path = path.replace('/phototype/upload','/uploads')
		
		filename = os.path.join(path, filename[0])
		line = self.rfile.readline()
		remaining_bytes -= len(line)
		line = self.rfile.readline()
		remaining_bytes -= len(line)
		try:
			out = open(filename, 'wb')
		except IOError as ioe:
			#print(ioe)
			return (False, "Can't create file to write, do you have permission to write?")
				
		pre_line = self.rfile.readline()
		remaining_bytes -= len(pre_line)
		while remaining_bytes > 0:
			line = self.rfile.readline()
			remaining_bytes -= len(line)
			if boundary in line:
				pre_line = pre_line[0:-1]
				if pre_line.endswith(b'\r'):
					pre_line = pre_line[0:-1]
				out.write(pre_line)
				out.close()
				return (True, "File '%s' upload success!" % filename)
			else:
				out.write(pre_line)
				pre_line = line
		
		return (False, "Unexpected end of data.")

	def translate_path(self, path):
		"""Translate a /-separated PATH to the local filename syntax.

		Components that mean special things to the local file system
		(e.g. drive or directory names) are ignored.  (XXX They should
		probably be diagnosed.)

		"""
		path = posixpath.normpath(url_unquote(path))
		words = path.split('/')
		words = filter(None, words)
		path = os.getcwd()
		for word in words:
			drive, word = os.path.splitdrive(word)
			head, word = os.path.split(word)
			if word in (os.curdir, os.pardir): continue
			path = os.path.join(path, word)
		return path
	
	def copyfile(self, source, outputfile):
		"""Copy all data between two file objects.

		The SOURCE argument is a file object open for reading
		(or anything with a read() method) and the DESTINATION
		argument is a file object open for writing (or
		anything with a write() method).

		"""
		shutil.copyfileobj(source, outputfile)

	def guess_type(self, path):
		"""Guess the type of a file.

		Argument is a PATH (a filename).

		Return value is a string of the form type/subtype,
		usable for a MIME Content-type header.

		The default implementation looks the file's extension
		up in the table self.extensions_map, using text/plain
		as a default; however it would be permissible (if
		slow) to look inside the data to make a better guess.

		"""
		base, ext = posixpath.splitext(path)
		if ext in self.extensions_map:
			return self.extensions_map[ext]
		ext = ext.lower()
		if ext in self.extensions_map:
			return self.extensions_map[ext]
		else:
			return self.extensions_map['']


# ----- MAIN FUNCTION ------------------------------------------------

if __name__ == '__main__':
	SimpleServer()
