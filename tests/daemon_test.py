'''
Test for daemonizing : endless loop logging to syslog current time each 5 seconds.
'''

import datetime
import gevent
import telephonie.utils.logger as logger
import telephonie.utils.daemonize as daemonize

log = logger.SysLogger()

pidfile = '/tmp/daemon_test.pid'

print "starting with pidfile %s" % pidfile

daemonize.daemon('root', 'root', pidfile=pidfile)
while True:
  log.debug(str(datetime.datetime.now()))
  gevent.sleep(5.0)
