from z3 import *
import requests
import time
from datetime import timedelta, datetime
import random
es_url = 'http://elastic:kOrgK7PIHc46n697bT9z333O@localhost:52625'

r = requests.get('http://elastic:kOrgK7PIHc46n697bT9z333O@localhost:52625')
# r = requests.get("http://localhost:52625"+"/", data=postData)
print(r)


'''a = set([2])
b = set([2, 3])
print(a < b)
x, y, z = Reals('x y z')
s = Solver()
s.add(x > 1, y > 1, x + y > 3, z - x < 10)
print(s.check())

m = s.model()
print(m)
print("x = %s" % m[x])

print("traversing model...")
for d in m.decls():
    print("%s = %s" % (d.name(), m[d]))

f = Function('f', IntSort(), IntSort())
x = Int('x')
s = Solver()
s.add(x > 0, x < 2, f(x) == 0)
print(s.check())

m = s.model()
for d in m.decls():
    print(d.name(), m[d])
for var in m:
    print(var)

x = Int('x')
y = Int('y')
f = Function('f', IntSort(), IntSort())
s = Solver()
s.add(f(f(x)) == x, f(x) == y, x != y)
print (s.check())
m = s.model()
print ("f(f(x)) =", m.evaluate(f(f(x))))
print( "f(x)    =", m.evaluate(f(x)))
grea=[]
for var in m:
    print(m[var])
    grea.append(var() != m[var])
print(grea)'''