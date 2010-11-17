'''
Daemonize application.
'''


import os
import sys
import grp
import pwd


__default_servicename__ = os.path.splitext(os.path.basename(sys.argv[0]))[0]


def daemon(user, group, path='/', pidfile='/tmp/%s.pid' % __default_servicename__, other_groups=()):
    '''
    Daemonize current application.
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

