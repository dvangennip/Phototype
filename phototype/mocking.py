# ----- MOCK FUNCTIONS --------------------------------------------------------

# taken from: https://github.com/pimoroni/python-multitouch/blob/master/library/ft5406.py

from collections import namedtuple
from pygame.locals import *
import threading
import time
import queue

TOUCH_X = 0
TOUCH_Y = 1

TouchEvent = namedtuple('TouchEvent', ('timestamp', 'type', 'code', 'value'))

EV_SYN = 0
EV_ABS = 3

ABS_X = 0
ABS_Y = 1

ABS_MT_SLOT = 0x2f # 47 MT slot being modified
ABS_MT_POSITION_X = 0x35 # 53 Center X of multi touch position
ABS_MT_POSITION_Y = 0x36 # 54 Center Y of multi touch position
ABS_MT_TRACKING_ID = 0x39 # 57 Unique ID of initiated contact

TS_RELEASE = 0
TS_PRESS   = 1
TS_MOVE    = 2


class Touch(object):
	def __init__(self, slot, x, y):
		self.slot = slot

		self._x = x
		self._y = y
		self.last_x = -1
		self.last_y = -1

		self._id = -1
		self.events = []
		self.on_move = None
		self.on_press = None
		self.on_release = None

	@property
	def position(self):
		return (self.x, self.y)

	@property
	def last_position(self):
		return (self.last_x, self.last_y)

	@property
	def valid(self):
		return self.id > -1

	@property
	def id(self):
		return self._id

	@id.setter
	def id(self, value):
		if value != self._id:
			if value == -1 and not TS_RELEASE in self.events:
				self.events.append(TS_RELEASE)    
			elif not TS_PRESS in self.events:
				self.events.append(TS_PRESS)

		self._id = value

	@property
	def x(self):
		return self._x

	@x.setter
	def x(self, value):
		if value != self._x and not TS_MOVE in self.events:
			self.events.append(TS_MOVE)
		self.last_x = self._x
		self._x = value

	@property
	def y(self):
		return self._y

	@y.setter
	def y(self, value):
		if value != self._y and not TS_MOVE in self.events:
			self.events.append(TS_MOVE)
		self.last_y = self._y
		self._y = value

	def handle_events(self):
		"""Run outstanding press/release/move events"""
		for event in self.events:
			if event == TS_MOVE and callable(self.on_move):
				self.on_move(event, self)
			if event == TS_PRESS and callable(self.on_press):
				self.on_press(event, self)
			if event == TS_RELEASE and callable(self.on_release):
				self.on_release(event, self)

		self.events = []


class Touches(list):
	@property
	def valid(self):
		return [touch for touch in self if touch.valid]


class Touchscreen ():
	def __init__ (self):
		self._running     = False
		self._thread      = None
		self.position     = Touch(0,0,0)
		self.touches      = Touches([Touch(x, 0, 0) for x in range(10)])
		self._event_queue = queue.Queue()
		self._touch_slot  = 0

	def _run (self):
		self._running = True
		while self._running:
			self.poll()

	def run (self):
		if (self._thread is not None):
			return

		self._thread = threading.Thread(target=self._run)
		self._thread.start()

	def stop (self):
		if (self._thread is None):
			return

		self._running = False
		self._thread.join()
		self._thread  = None

	@property
	def _current_touch (self):
		return self.touches[self._touch_slot]

	""" added to be able to inject pygame mouse events instead of touchscreen events """
	def add_events (self, events):
		for event in events:
			if (event.type == MOUSEBUTTONDOWN):
				mousex, mousey = event.pos
			elif (event.type == MOUSEBUTTONUP):
				mousex, mousey = event.pos
			elif (event.type == MOUSEMOTION):
				mousex, mousey = event.pos
			#self._event_queue.put(TouchEvent(time.time(), type, code, value))

	def poll (self):
		# events should already be added via the above function

		# handle queue
		while not self._event_queue.empty():
			event = self._event_queue.get()
			self._event_queue.task_done()

			if event.type == EV_SYN: # Sync
				for touch in self.touches:
					touch.handle_events()
				return self.touches

			if event.type == EV_ABS: # Absolute cursor position
				if event.code == ABS_MT_SLOT:
					self._touch_slot = event.value

				if event.code == ABS_MT_TRACKING_ID: 
					self._current_touch.id = event.value

				if event.code == ABS_MT_POSITION_X:
					self._current_touch.x = event.value

				if event.code == ABS_MT_POSITION_Y:
					self._current_touch.y = event.value

				if event.code == ABS_X:
					self.position.x = event.value

				if event.code == ABS_Y:
					self.position.y = event.value

		return []
