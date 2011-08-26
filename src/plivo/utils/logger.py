# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Log classes : stdout, syslog and file loggers
"""

from gevent import monkey
monkey.patch_all()

import logging
import logging.handlers
from logging import RootLogger
import sys
import os

from plivo.utils.encode import safe_str

monkey.patch_thread() # thread must be patched after import

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

    def set_error(self):
        self.loglevel = LOG_ERROR
        self._logger.setLevel(self.loglevel)

    def set_warn(self):
        self.loglevel = LOG_WARN
        self._logger.setLevel(self.loglevel)

    def info(self, msg):
        self._logger.info(safe_str(msg))

    def debug(self, msg):
        self._logger.debug(safe_str(msg))

    def warn(self, msg):
        self._logger.warn(safe_str(msg))

    def error(self, msg):
        self._logger.error(safe_str(msg))

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
        if ':' in addr:
            host, port = addr.split(':', 1)
            port = int(port)
            addr = (host, port)
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


class DummyLogger(object):
    def set_debug(self):
        pass

    def set_info(self):
        pass

    def set_error(self):
        pass

    def set_warn(self):
        pass

    def info(self, msg):
        pass

    def debug(self, msg):
        pass

    def warn(self, msg):
        pass

    def error(self, msg):
        pass

    def write(self, msg):
        pass

class HTTPHandler(logging.handlers.HTTPHandler):
    def __init__(self, host, url, method="GET"):
        logging.handlers.HTTPHandler.__init__(self, host, url, method)

    def emit(self, record):
        """
        Emit a record.

        Send the record to the Web server as a percent-encoded dictionary
        """
        try:
            import httplib, urllib
            host = self.host
            h = httplib.HTTP(host)
            url = self.url
            data = urllib.urlencode(self.mapLogRecord(record))
            if self.method == "GET":
                if (url.find('?') >= 0):
                    sep = '&'
                else:
                    sep = '?'
                url = url + "%c%s" % (sep, data)
            h.putrequest(self.method, url)
            # support multiple hosts on one IP address...
            # need to strip optional :port from host, if present
            i = host.find(":")
            if i >= 0:
                host = host[:i]
            h.putheader("Host", host)
            if self.method == "POST":
                h.putheader("Content-type",
                            "application/x-www-form-urlencoded")
                h.putheader("Content-length", str(len(data)))
            h.endheaders(data if self.method == "POST" else None)
            h.getreply()    #can't do anything with the result
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            raise



class HTTPLogger(object):
    def __init__(self, url, method='POST', fallback_file=None, loglevel=LOG_DEBUG, servicename=__default_servicename__):
        import urlparse
        self.loglevel = loglevel
        self.fallback_file = fallback_file
        p = urlparse.urlparse(url)
        netloc = p.netloc
        urlpath = p.path
        if p.query:
            urlpath += '?' + query
        h = HTTPHandler(host=netloc, url=urlpath, method=method)
        h.setLevel(loglevel)
        fmt = logging.Formatter(servicename+"[%(process)d]: %(levelname)s: %(message)s")
        h.setFormatter(fmt)
        self._logger = RootLogger(loglevel)
        self._logger.addHandler(h)
        if self.fallback_file:
            self._fallback = FileLogger(logfile=self.fallback_file,
                                        loglevel=self.loglevel,
                                        servicename=servicename)
        else:
            self._fallback = DummyLogger()

    def set_debug(self):
        self.loglevel = LOG_DEBUG
        self._logger.setLevel(self.loglevel)
        self._fallback.set_debug()

    def set_info(self):
        self.loglevel = LOG_INFO
        self._logger.setLevel(self.loglevel)
        self._fallback.set_info()

    def set_error(self):
        self.loglevel = LOG_ERROR
        self._logger.setLevel(self.loglevel)
        self._fallback.set_error()

    def set_warn(self):
        self.loglevel = LOG_WARN
        self._logger.setLevel(self.loglevel)
        self._fallback.set_warn()

    def info(self, msg):
        try:
            self._logger.info(safe_str(msg))
        except:
            self._fallback.info(safe_str(msg))

    def debug(self, msg):
        try:
            self._logger.debug(safe_str(msg))
        except:
            self._fallback.debug(safe_str(msg))

    def warn(self, msg):
        try:
            self._logger.warn(safe_str(msg))
        except:
            self._fallback.warn(safe_str(msg))

    def error(self, msg):
        try:
            self._logger.error(safe_str(msg))
        except:
            self._fallback.error(safe_str(msg))

    def write(self, msg):
        try:
            self.info(msg)
        except:
            self._fallback.info(safe_str(msg))

