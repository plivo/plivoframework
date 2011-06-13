# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Daemonize application.
"""

import os
import sys
import grp
import pwd
from subprocess import Popen
import optparse
import gevent


__default_servicename__ = os.path.splitext(os.path.basename(sys.argv[0]))[0]


def daemon(user, group, path='/', pidfile='/tmp/%s.pid' % __default_servicename__, other_groups=()):
    '''
    Daemonizes current application.
    '''
    # Get uid and gid from user and group names
    uid = int(pwd.getpwnam(user)[2])
    gid = int(grp.getgrnam(group)[2])
    # Get ID of other groups
    other_groups_id = []
    for name in other_groups:
        try:
            other_groups_id.append(int(grp.getgrnam(name)[2]) )
        except:
            pass
    # First fork
    pid = gevent.fork()
    if not pid == 0:
        os._exit(0)
    # Creates a session and sets the process group ID
    os.setsid()
    # Second fork
    pid = gevent.fork()
    if not pid == 0:
        os._exit(0)
    # Change directoty
    os.chdir(path)
    # Set umask
    os.umask(0)
    # Write pidfile
    open(pidfile, 'w').write(str(os.getpid()))
    # Set group and groups
    os.setgid(gid)
    if other_groups_id:
        os.setgroups(other_groups_id)
    # Set user
    os.setuid(uid)
    # Redirect stdout/stderr to /dev/null
    sys.stdout = sys.stderr = open(os.devnull, 'a+')
    gevent.reinit()


def daemon_script(script, user, group, path='/', pidfile=None, script_args=(), other_groups=(), python_bin=None):
    '''
    Daemonize a python script.
    '''
    # Autocreate path for pidfile (based on script arg) if not set
    if not pidfile:
        pidfile = '/tmp/' + os.path.splitext(os.path.basename(script))[0] + '.pid'
    # Get full/real path to script
    real_script = os.path.realpath(script)
    # Get uid and gid from user and group names
    uid = int(pwd.getpwnam(user)[2])
    gid = int(grp.getgrnam(group)[2])
    # Get ID of other groups
    other_groups_id = []
    for name in other_groups:
        try:
            other_groups_id.append(int(grp.getgrnam(name)[2]) )
        except:
            pass
    # First fork
    pid = os.fork()
    if not pid == 0:
        os._exit(0)
    # Creates a session and sets the process group ID
    os.setsid()
    # Second fork
    pid = os.fork()
    if not pid == 0:
        os._exit(0)
    # Change directoty
    os.chdir(path)
    # Set umask
    os.umask(0)
    # Set group and groups
    os.setgid(gid)
    if other_groups_id:
        os.setgroups(other_groups_id)
    # Set user
    os.setuid(uid)
    # Set python binary
    if not python_bin:
        cmd = ["/usr/bin/env", "python"]
    else:
        cmd = [python_bin]
    cmd.append(real_script)
    # Add script_args
    for arg in script_args:
        cmd.append(arg)
    # Run script
    pid = Popen(cmd).pid
    # Write pidfile
    open(pidfile, 'w').write(str(pid))
    # Redirect stdout/stderr to /dev/null
    sys.stdout = sys.stderr = open(os.devnull, 'a+')
    # Wait pid end
    os.waitpid(pid, 0)


def main():
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
    parser.add_option("-G", "--groups", action="append", type="string", default=[],
                      dest="groups", help="set other groups gid to OTHERGROUP (can be added multiple times)",
                      metavar="OTHERGROUP")
    parser.add_option("-P", "--pybin", action="store", type="string", default=None,
                      dest="pybin", help="set python binary PYBIN to run script",
                      metavar="PYBIN")
    parser.add_option("-a", "--scriptarg", action="append", type="string", default=[],
                      dest="scriptargs", help="add ARG to python script (can be added multiple times)",
                      metavar="ARG")
    (options, args) = parser.parse_args()

    script = options.script
    user = options.user
    group = options.group
    pidfile = options.pidfile
    ogroups = options.groups
    pybin = options.pybin
    scriptargs = options.scriptargs

    if not script or not user or not group or not pidfile:
        parser.print_help()
        sys.exit(1)

    daemon_script(script, user, group, pidfile=pidfile,
                  script_args=scriptargs, other_groups=ogroups,
                  python_bin=pybin)


if __name__ == '__main__':
    main()
