#!/usr/bin/env python

import sys
import optparse
import telephonie.utils.daemonize as daemonize

def get_opt():
    parser = optparse.OptionParser()
    parser.add_option("-s", "--script", action="store", type="string",
                      dest="script", help="python script SCRIPT to run (argument is mandatory)", 
                      metavar="SCRIPT")
    parser.add_option("-p", "--pidfile", action="store", type="string",
                      dest="pidfile", help="write pid to PIDFILE (argument is mandatory)",
                      metavar="PIDFILE")
    parser.add_option("-u", "--user", action="store", type="string",
                      dest="user", help="set uid to USER (argument is mandatory)", 
                      metavar="USER")
    parser.add_option("-g", "--group", action="store", type="string",
                      dest="group", help="set gid to GROUP (argument is mandatory)", 
                      metavar="GROUP")
    parser.add_option("-G", "--groups", action="append", type="string", default=(),
                      dest="groups", help="set other groups gid to OTHERGROUP (can be added multiple times)", 
                      metavar="OTHERGROUP")
    parser.add_option("-P", "--pybin", action="store", type="string", default=None,
                      dest="pybin", help="set python binary PYBIN to run script", 
                      metavar="PYBIN")
    (options, args) = parser.parse_args()
    return (parser, options, args)

if __name__ == '__main__':
    parser, options, args = get_opt()
    script = options.script
    user = options.user
    group = options.group
    pidfile = options.pidfile 
    ogroups = options.groups
    pybin = options.pybin
    if not script or not user or not group or not pidfile:
      print "Missing argument(s)"
      parser.print_help()
      sys.exit(1)
    daemonize.daemon_script(script, user, group, pidfile=pidfile, other_groups=ogroups, python_bin=pybin)
