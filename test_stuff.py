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