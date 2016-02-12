import re
import string
ethosconfig = open("/home/ethos/local", "r")
def setup ():
for line in ethosconfig:
    if re.match("(.*)(?<=proxypool1 )(.*)", line):
        proxypool1 = line.rstrip('\n').split(" ", 2)[1].split(":", 2)
#        myvar = line.split(" ", 2)
#       print line,
#       print myvar
#       print myvar2,
#       myvar3 = myvar[1].split(":", 2)
#       print myvar3
        mainpool = proxypool1[0]
        mainport = proxypool1[1]
#.rstrip('\n')
        print pool
        print port
    elif  re.match("(.*)(?<=proxypool2 )(.*)", line):
        proxypool2 = line.rstrip('\n').split(" ", 2)[1].split(":", 2)
#      backuppool = proxypool2[0]
#       backupport = proxypool2[1]
#        print backupport
#        print backuppool
    elif re.match("(.*)(?<=proxywallet )(.*)",line):
        proxywallet = line.rstrip('\n').split(" ", 2)[1]
#        print proxywallet

setup()
