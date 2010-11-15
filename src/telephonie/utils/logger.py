# -*- coding: utf-8 -*-
"""
Log classes : stdout, syslog and file loggers
"""

import gevent.monkey
gevent.monkey.patch_thread()

import logging
import logging.handlers
from logging import RootLogger
import sys
import os

LOG_DEBUG = logging.DEBUG
LOG_ERROR = logging.ERROR
LOG_INFO = logging.INFO
LOG_WARN = logging.WARN
LOG_WARNING = logging.WARNING
LOG_CRITICAL = logging.CRITICAL
LOG_FATAL = logging.FATAL
LOG_NOTSET = logging.NOTSET


__default_servicename__ = os.path.splitext(os.path.basename(sys.argv[0]))[0]


class StdoutLogger(object):
    def __init__(self, loglevel=LOG_DEBUG, servicename=__default_servicename__):
        self.loglevel = loglevel
        h = logging.StreamHandler()
        h.setLevel(loglevel)
        fmt = logging.Formatter("%(asctime)s "+servicename+"[%(process)d]: %(levelname)s: %(message)s")
        h.setFormatter(fmt)
        self._logger = RootLogger(loglevel)
        self._logger.addHandler(h)

    def set_debug(self):
        self.loglevel = LOG_DEBUG
        self._logger.setLevel(self.loglevel)
        
    def set_info(self):
        self.loglevel = LOG_INFO
        self._logger.setLevel(self.loglevel)

    def info(self, msg):
        self._logger.info(str(msg))

    def debug(self, msg):
        self._logger.debug(str(msg))

    def warn(self, msg):
        self._logger.warn(str(msg))

    def error(self, msg):
        self._logger.error(str(msg))

    def write(self, msg):
        self.info(msg)


class Syslog(logging.handlers.SysLogHandler):
    LOG_EMERG     = 0       #  system is unusable
    LOG_ALERT     = 1       #  action must be taken immediately
    LOG_CRIT      = 2       #  critical conditions
    LOG_ERR       = 3       #  error conditions
    LOG_WARNING   = 4       #  warning conditions
    LOG_NOTICE    = 5       #  normal but significant condition
    LOG_INFO      = 6       #  informational
    LOG_DEBUG     = 7       #  debug-level messages


    #  facility codes
    LOG_KERN      = 0       #  kernel messages
    LOG_USER      = 1       #  random user-level messages
    LOG_MAIL      = 2       #  mail system
    LOG_DAEMON    = 3       #  system daemons
    LOG_AUTH      = 4       #  security/authorization messages
    LOG_SYSLOG    = 5       #  messages generated internally by syslogd
    LOG_LPR       = 6       #  line printer subsystem
    LOG_NEWS      = 7       #  network news subsystem
    LOG_UUCP      = 8       #  UUCP subsystem
    LOG_CRON      = 9       #  clock daemon
    LOG_AUTHPRIV  = 10  #  security/authorization messages (private)

    #  other codes through 15 reserved for system use
    LOG_LOCAL0    = 16      #  reserved for local use
    LOG_LOCAL1    = 17      #  reserved for local use
    LOG_LOCAL2    = 18      #  reserved for local use
    LOG_LOCAL3    = 19      #  reserved for local use
    LOG_LOCAL4    = 20      #  reserved for local use
    LOG_LOCAL5    = 21      #  reserved for local use
    LOG_LOCAL6    = 22      #  reserved for local use
    LOG_LOCAL7    = 23      #  reserved for local use


    priority_names = {
        "alert":    LOG_ALERT,
        "crit":     LOG_CRIT,
        "critical": LOG_CRIT,
        "debug":    LOG_DEBUG,
        "emerg":    LOG_EMERG,
        "err":      LOG_ERR,
        "error":    LOG_ERR,        #  DEPRECATED
        "info":     LOG_INFO,
        "notice":   LOG_NOTICE,
        "panic":    LOG_EMERG,      #  DEPRECATED
        "notice":   LOG_NOTICE,
        "warn":     LOG_WARNING,    #  DEPRECATED
        "warning":  LOG_WARNING,
        "info_srv":  LOG_INFO,
        "error_srv":  LOG_ERR,
        "debug_srv":  LOG_DEBUG,
        "warn_srv":  LOG_WARNING,
        }

    facility_names = {
        "auth":     LOG_AUTH,
        "authpriv": LOG_AUTHPRIV,
        "cron":     LOG_CRON,
        "daemon":   LOG_DAEMON,
        "kern":     LOG_KERN,
        "lpr":      LOG_LPR,
        "mail":     LOG_MAIL,
        "news":     LOG_NEWS,
        "security": LOG_AUTH,       #  DEPRECATED
        "syslog":   LOG_SYSLOG,
        "user":     LOG_USER,
        "uucp":     LOG_UUCP,
        "local0":   LOG_LOCAL0,
        "local1":   LOG_LOCAL1,
        "local2":   LOG_LOCAL2,
        "local3":   LOG_LOCAL3,
        "local4":   LOG_LOCAL4,
        "local5":   LOG_LOCAL5,
        "local6":   LOG_LOCAL6,
        "local7":   LOG_LOCAL7,
        }


class SysLogger(StdoutLogger):
    def __init__(self, addr='/dev/log', syslogfacility="local0", \
                 loglevel=LOG_DEBUG, servicename=__default_servicename__):
        fac = Syslog.facility_names[syslogfacility]
        h = Syslog(address=addr, facility=fac)
        h.setLevel(loglevel)
        fmt = logging.Formatter(servicename+"[%(process)d]: %(levelname)s: %(message)s")
        h.setFormatter(fmt)
        self._logger = RootLogger(loglevel)
        self._logger.addHandler(h)


class FileLogger(StdoutLogger):
    def __init__(self, logfile='/tmp/%s.log' % __default_servicename__, \
                 loglevel=LOG_DEBUG, servicename=__default_servicename__):
        h = logging.FileHandler(filename=logfile)
        h.setLevel(loglevel)
        fmt = logging.Formatter("%(asctime)s "+servicename+"[%(process)d]: %(levelname)s: %(message)s")
        h.setFormatter(fmt)
        self._logger = RootLogger(loglevel)
        self._logger.addHandler(h)

