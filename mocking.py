# ----- MOCK FUNCTIONS --------------------------------------------------------

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
		self.touches = Touches([Touch(x, 0, 0) for x in range(10)])

	def run (self):
		pass

	def stop (self):
		pass

	def poll (self):
		return []

TS_PRESS   = 1
TS_RELEASE = 0
TS_MOVE    = 2