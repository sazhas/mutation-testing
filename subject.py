# Subject program for mutation testing and analysis

# In f1(), changing + to - will change the behavior of f1(2,2) but not
# f1(5,0). By contrast, changing + to * will not change the behavior of
# f1(2,2) but will change the behavior of f1(5,0). 
def f01(a,b):
        return a+b

# For the remainder of the functions, you will have to read them yourself and 
# think about which mutation operators you want to implement. Note that you
# should not "hard-code" associations between mutation operators and particular
# function names. 

def f02(c,d):
        if c <= d:
                return 123
        else:
                return 456

def f03(e,f):
        e = f 
        return e 
        
def f04(g,h):
        if True:
                return g
        else:
                return h 

def f05(i,j):
        i += j 
        j += i 
        return min(i,j) 
        
def f06(k,l):
        m = 0 
        while l > k:
                k += 1 
                m += 1 
        return m 

def helper(x):
        return x+1
        
def f07(m,n):
        a = helper(m)
        b = helper(helper(n))
        return a+b+0

def f08(o,p):
        result = 1 
        try:
                result = (result * 2) + 1
                raise Exception() 
                result = (result * 3) + 2
        except Exception as e:
                result = (result * 4) + 3
        return result 

def f09(q,r):
        if q <= 0:
                return r
        else:
                return r + f09(q-1,r) + f09(q-2,r) 
        
def f10(s,t):
	arr = s
	n = len(arr)
	for i in range(n - 1):
		swapped = False
		for j in range(0, n - i - 1):
			if arr[j] < arr[j + 1]:
				arr[j], arr[j + 1] = arr[j + 1], arr[j]
				swapped = True
		if not swapped:
			break
	return arr
