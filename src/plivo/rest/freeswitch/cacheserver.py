# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from gevent import monkey
monkey.patch_all()

import grp
import os
import pwd
import signal
import sys
import optparse

from flask import Flask
import gevent
from gevent.wsgi import WSGIServer
from gevent.pywsgi import WSGIServer as PyWSGIServer

from plivo.rest.freeswitch.cacheapi import PlivoCacheApi
import plivo.utils.daemonize
from plivo.rest.freeswitch import cacheurls, helpers, cacheapi
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger, DummyLogger, HTTPLogger


class PlivoCacheServer(PlivoCacheApi):
    """Class PlivoCacheServer"""
    name = 'PlivoCacheServer'

    def __init__(self, configfile, daemon=False,
                        pidfile='/tmp/plivo_cache.pid'):
        self._daemon = daemon
        self._run = False
        self._pidfile = pidfile
        self.configfile = configfile
        self._wsgi_mode = WSGIServer
        # create flask app
        self.app = Flask(self.name)

        # load config
        self.cache = None
        self._config = None
        self.load_config()

        # expose API functions to flask app
        for path, func_desc in cacheurls.URLS.iteritems():
            func, methods = func_desc
            fn = getattr(self, func.__name__)
            self.app.add_url_rule(path, func.__name__, fn, methods=methods)

        self.log.info("Listening HTTP")
        self.log.info("%s mode set" % str(self._wsgi_mode))
        self.http_server = self._wsgi_mode((self.http_host, self.http_port),
                                            self.app, log=self.log)

    def create_cache(self, config):
        # load cache params
        self.redis_host = config.get('cache_server', 'REDIS_HOST', default='')
        self.redis_port = config.get('cache_server', 'REDIS_PORT', default='')
        self.redis_db = config.get('cache_server', 'REDIS_DB', default='')
        self.redis_pw = config.get('cache_server', 'REDIS_PASSWORD', default=None)
        self.proxy_url = config.get('cache_server', 'PROXY_URL', default=None)
        if self.redis_host and self.redis_port and self.redis_db:
            self.cache = cacheapi.ResourceCache(self.redis_host,
                                        int(self.redis_port),
                                        int(self.redis_db),
                                        self.redis_pw,
                                        self.proxy_url)
            return True

        self.log.error("Cannot run cache server, cache not set !")
        raise Exception("Cannot run cache server, cache not set !")


    def get_log(self):
        return self.log

    def get_config(self):
        return self._config

    def get_cache(self):
        return self.cache

    def create_logger(self, config):
        """This will create a logger using helpers.PlivoConfig instance

        Based on the settings in the configuration file,
        LOG_TYPE will determine if we will log in file, syslog, stdout, http or dummy (no log)
        """
        if self._daemon is False:
            logtype = config.get('cache_server', 'LOG_TYPE')
            if logtype == 'dummy':
                new_log = DummyLogger()
            else:
                new_log = StdoutLogger()
            new_log.set_debug()
            self.app.debug = True
            self.log = new_log
        else:
            logtype = config.get('cache_server', 'LOG_TYPE')
            if logtype == 'file':
                logfile = config.get('cache_server', 'LOG_FILE')
                new_log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = config.get('cache_server', 'SYSLOG_ADDRESS')
                syslogfacility = config.get('cache_server', 'SYSLOG_FACILITY')
                new_log = SysLogger(syslogaddress, syslogfacility)
            elif logtype == 'dummy':
                new_log = DummyLogger()
            elif logtype == 'http':
                url = config.get('cache_server', 'HTTP_LOG_URL')
                method = config.get('cache_server', 'HTTP_LOG_METHOD')
                fallback_file = config.get('cache_server', 'HTTP_LOG_FILE_FAILURE')
                new_log = HTTPLogger(url=url, method=method, fallback_file=fallback_file)
            else:
                new_log = StdoutLogger()
            log_level = config.get('cache_server', 'LOG_LEVEL', default='INFO')
            if log_level == 'DEBUG':
                new_log.set_debug()
                self.app.debug = True
            elif log_level == 'INFO':
                new_log.set_info()
                self.app.debug = False
            elif log_level == 'ERROR':
                new_log.set_error()
                self.app.debug = False
            elif log_level in ('WARN', 'WARNING'):
                new_log.set_warn()
                self.app.debug = False

        new_log.name = self.name
        self.log = new_log
        self.app._logger = self.log

    def load_config(self, reload=False):
        # backup config
        backup_config = self._config
        # create config
        config = helpers.PlivoConfig(self.configfile)

        try:
            # read config
            config.read()

            if not reload:
                # create first logger if starting
                self.create_logger(config=config)
                self.log.info("Starting ...")
                self.log.warn("Logger %s" % str(self.log))

                self.app.secret_key = config.get('cache_server', 'SECRET_KEY')
                self.app.config['MAX_CONTENT_LENGTH'] = 1024 * 10240
                self.http_address = config.get('cache_server', 'HTTP_ADDRESS')
                self.http_host, http_port = self.http_address.split(':', 1)
                self.http_port = int(http_port)

                # load cache params
                self.redis_host = config.get('cache_server', 'REDIS_HOST', default='')
                self.redis_port = config.get('cache_server', 'REDIS_PORT', default='')
                self.redis_db = config.get('cache_server', 'REDIS_DB', default='')
                # create new cache
                self.create_cache(config=config)
                self.log.warn("Cache %s" % str(self.cache))

                # set wsgi mode
                _wsgi_mode = config.get('cache_server', 'WSGI_MODE', default='wsgi')
                if _wsgi_mode in ('pywsgi', 'python', 'py'):
                    self._wsgi_mode = PyWSGIServer
                else:
                    self._wsgi_mode = WSGIServer

            if reload:
                # create new logger if reloading
                self.create_logger(config=config)
                self.log.warn("New logger %s" % str(self.log))
                # create new cache
                self.create_cache(config=config)
                self.log.warn("New cache %s" % str(self.cache))


            # allowed ips to access cache server
            allowed_ips = config.get('common', 'ALLOWED_IPS', default='')
            if not allowed_ips.strip():
                self.allowed_ips = []
            else:
                self.allowed_ips = [ ip.strip() for ip in allowed_ips.split(',') ]

            # set new config
            self._config = config
            self.log.info("Config : %s" % str(self._config.dumps()))

        except Exception, e:
            if backup_config:
                self._config = backup_config
                self.load_config()
                self.log.warn("Error reloading config: %s" % str(e))
                self.log.warn("Rollback to the last config")
                self.log.info("Config : %s" % str(self._config.dumps()))
            else:
                sys.stderr.write("Error loading config: %s" % str(e))
                sys.stderr.flush()
                raise e

    def reload(self):
        self.log.warn("Reload ...")
        self.load_config(reload=True)
        self.log.warn("Reload done")

    def do_daemon(self):
        """This will daemonize the current application

        Two settings from our configuration files are also used to run the
        daemon under a determine user & group.

        USER : determine the user running the daemon
        GROUP : determine the group running the daemon
        """
        # get user/group from config
        user = self._config.get('cache_server', 'USER', default=None)
        group = self._config.get('cache_server', 'GROUP', default=None)
        if not user or not group:
            uid = os.getuid()
            user = pwd.getpwuid(uid)[0]
            gid = os.getgid()
            group = grp.getgrgid(gid)[0]
        # daemonize now
        plivo.utils.daemonize.daemon(user, group, path='/',
                                     pidfile=self._pidfile,
                                     other_groups=())

    def sig_term(self, *args):
        """if we receive a term signal, we will shutdown properly
        """
        self.log.warn("Shutdown ...")
        self.stop()
        sys.exit(0)

    def sig_hup(self, *args):
        self.reload()

    def stop(self):
        """Method stop stop the infinite loop from start method
        and close the socket
        """
        self._run = False

    def start(self):
        """start method is where we decide to :
            * catch term signal
            * run as daemon
            * start the http server
        """
        self.log.info("CacheServer starting ...")
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        gevent.signal(signal.SIGHUP, self.sig_hup)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        # start http server
        self.log.info("CacheServer started at: 'http://%s'" % self.http_address)
        # Start cache server
        try:
            self.http_server.serve_forever()
        except (SystemExit, KeyboardInterrupt):
            pass
        # finish here
        self.log.info("CacheServer Exited")


def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--configfile", action="store", type="string",
                      dest="configfile",
                      help="use plivo config file (argument is mandatory)",
                      metavar="CONFIGFILE")
    parser.add_option("-p", "--pidfile", action="store", type="string",
                      dest="pidfile",
                      help="write pid to PIDFILE (argument is mandatory)",
                      metavar="PIDFILE")
    (options, args) = parser.parse_args()

    configfile = options.configfile
    pidfile = options.pidfile

    if not configfile:
        configfile = './etc/plivo/default.conf'
        if not os.path.isfile(configfile):
            raise SystemExit("Error : Default config file mising at '%s'. Please specify -c <configfilepath>" %configfile)
    if not pidfile:
        pidfile='/tmp/plivo_cache.pid'

    server = PlivoCacheServer(configfile=configfile, pidfile=pidfile,
                                                    daemon=False)
    server.start()


if __name__ == '__main__':
    main()
