import urllib2
import sys

url = sys.argv[1]
req = urllib2.Request(url)
handler = urllib2.urlopen(req)
buffer = handler.read()
sys.stdout.write(buffer)
sys.stdout.flush()
