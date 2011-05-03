#!/usr/bin/env python

def setup():
    import sys
    import os
    import shutil
    prefix = sys.prefix
    # set plivo script
    f = open(prefix + '/bin/plivo', 'r')
    buff = f.read()
    f.close()
    new_buff = buff.replace('@PREFIX@', prefix)
    f = open(prefix + '/bin/plivo', 'w')
    f.write(new_buff)
    f.close()

if __name__ == '__main__':
    setup()
