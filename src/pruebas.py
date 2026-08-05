import numpy as np

x = np.array([[20,10,10],[1,1,2]])

print(x.sum(axis=1))
print(x.sum(axis=1, keepdims=True))   # shape (2,1) en vez de (2,)
print(x/ x.sum(axis=1, keepdims=True))