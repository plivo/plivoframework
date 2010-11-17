#!/usr/bin/env python

import sys
import telephonie.utils.daemonize as daemonize

try:
    script = sys.argv[1]
except:
    print "daemon.py SCRIPT"
    print "  Daemonize python script"
    print
    sys.exit(1)

daemonize.daemon_script(script, 'root', 'root')
