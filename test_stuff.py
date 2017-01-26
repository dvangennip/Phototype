import random

test = {
	'a': 1,
	'b': 2,
	'c': 3,
	'd': 4
}

del test['d']

for t in test:
	print(test[t])

print('d' in test)

test['a'] += 1
test['b'] *= 2
print(test['a'])
print(test['b'])

# ------

x = [
	'aaa',
	'bbb',
	'ccc',
	{
		'ddd': 'eee'
	}
]

for idx, item in enumerate(x):
	print(idx, item)

# ------

r = ['a','b','c','d','e']
s = ['a','d','f','g','e']
si = None
unique = False
while not unique:
	si = s[random.randint(0, len(s)-1)]
	if (si not in r):
		unique = True
print (si)

# ------

def power (a,b):
	return a**b, b**a

c, d = power(2,3)
print(c,d)

# ------

class TestClass ():
	def __str__ (self):
		return self.__class__.__name__

class_ = globals()['TestClass']
instance = class_()
print(instance)
