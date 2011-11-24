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

from plivo.core.errors import ConnectError
from plivo.rest.freeswitch.api import PlivoRestApi
from plivo.rest.freeswitch.inboundsocket import RESTInboundSocket
from plivo.rest.freeswitch import urls, helpers
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger, DummyLogger, HTTPLogger


class PlivoRestServer(PlivoRestApi):
    """Class PlivoRestServer"""
    name = 'PlivoRestServer'
    default_http_method = 'POST'

    def __init__(self, configfile, daemon=False,
                        pidfile='/tmp/plivo_rest.pid'):
        """Initialize main properties such as daemon, pidfile, config, etc...

        This will init the http server that will provide the Rest interface,
        the rest server is configured on HTTP_ADDRESS

        Extra:
        * FS_INBOUND_ADDRESS : Define the event_socket interface to connect to
        in order to initialize CallSession with Freeswitch

        * FS_OUTBOUND_ADDRESS : Define where on which address listen to
        initialize event_socket session with Freeswitch in order to control
        new CallSession

        """
        self._daemon = daemon
        self._run = False
        self._pidfile = pidfile
        self.configfile = configfile
        self._wsgi_mode = WSGIServer
        self._ssl_cert = None
        self._ssl = False
        # create flask app
        self.app = Flask(self.name)

        # load config
        self._config = None
        self.cache = {}
        self.load_config()

        # create inbound socket instance
        self._rest_inbound_socket = RESTInboundSocket(server=self)
        # expose API functions to flask app
        for path, func_desc in urls.URLS.iteritems():
            func, methods = func_desc
            fn = getattr(self, func.__name__)
            self.app.add_url_rule(path, func.__name__, fn, methods=methods)
        # create WSGI Server
        if self._ssl and self._ssl_cert and helpers.file_exists(self._ssl_cert):
            self._wsgi_mode = PyWSGIServer
            self.log.info("Listening HTTPS")
            self.log.info("Force %s mode with HTTPS" % str(self._wsgi_mode))
            self.http_server = self._wsgi_mode((self.http_host, self.http_port),
                                               self.app, log=self.log,
                                               certfile=self._ssl_cert)
        else:
            self.log.info("Listening HTTP")
            self.log.info("%s mode set" % str(self._wsgi_mode))
            self.http_server = self._wsgi_mode((self.http_host, self.http_port),
                                               self.app, log=self.log)

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
            logtype = config.get('rest_server', 'LOG_TYPE')
            if logtype == 'dummy':
                new_log = DummyLogger()
            else:
                new_log = StdoutLogger()
            new_log.set_debug()
            self.app.debug = True
            self.log = new_log
        else:
            logtype = config.get('rest_server', 'LOG_TYPE')
            if logtype == 'file':
                logfile = config.get('rest_server', 'LOG_FILE')
                new_log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = config.get('rest_server', 'SYSLOG_ADDRESS')
                syslogfacility = config.get('rest_server', 'SYSLOG_FACILITY')
                new_log = SysLogger(syslogaddress, syslogfacility)
            elif logtype == 'dummy':
                new_log = DummyLogger()
            elif logtype == 'http':
                url = config.get('rest_server', 'HTTP_LOG_URL')
                method = config.get('rest_server', 'HTTP_LOG_METHOD')
                fallback_file = config.get('rest_server', 'HTTP_LOG_FILE_FAILURE')
                new_log = HTTPLogger(url=url, method=method, fallback_file=fallback_file)
            else:
                new_log = StdoutLogger()
            log_level = config.get('rest_server', 'LOG_LEVEL', default='INFO')
            if log_level == 'DEBUG' or self._trace is True:
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

            # set trace flag
            self._trace = config.get('rest_server', 'TRACE', default='false') == 'true'
            self.key = config.get('common', 'AUTH_ID', default='')
            self.secret = config.get('common', 'AUTH_TOKEN', default='')
            self.proxy_url = config.get('common', 'PROXY_URL', default=None)
            allowed_ips = config.get('rest_server', 'ALLOWED_IPS', default='')
            if allowed_ips:
                self.allowed_ips = allowed_ips.split(",")

            if not reload:
                # create first logger if starting
                self.create_logger(config=config)
                self.log.info("Starting ...")
                self.log.warn("Logger %s" % str(self.log))

                self.app.secret_key = config.get('rest_server', 'SECRET_KEY')
                self.app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
                self.http_address = config.get('rest_server', 'HTTP_ADDRESS')
                self.http_host, http_port = self.http_address.split(':', 1)
                self.http_port = int(http_port)

                self.fs_inbound_address = config.get('rest_server', 'FS_INBOUND_ADDRESS')
                self.fs_host, fs_port = self.fs_inbound_address.split(':', 1)
                self.fs_port = int(fs_port)

                self.fs_password = config.get('rest_server', 'FS_INBOUND_PASSWORD')

                # get outbound socket host/port
                self.fs_out_address = config.get('outbound_server', 'FS_OUTBOUND_ADDRESS')
                self.fs_out_host, self.fs_out_port  = self.fs_out_address.split(':', 1)

                # if outbound host is 0.0.0.0, send to 127.0.0.1
                if self.fs_out_host == '0.0.0.0':
                    self.fs_out_address = '127.0.0.1:%s' % self.fs_out_port
                # set wsgi mode
                _wsgi_mode = config.get('rest_server', 'WSGI_MODE', default='wsgi')
                if _wsgi_mode in ('pywsgi', 'python', 'py'):
                    self._wsgi_mode = PyWSGIServer
                else:
                    self._wsgi_mode = WSGIServer
                # set ssl or not
                self._ssl = config.get('rest_server', 'SSL', default='false') == 'true'
                self._ssl_cert = config.get('rest_server', 'SSL_CERT', default='')


            self.default_answer_url = config.get('common', 'DEFAULT_ANSWER_URL')

            self.default_hangup_url = config.get('common', 'DEFAULT_HANGUP_URL', default='')

            self.default_http_method = config.get('common', 'DEFAULT_HTTP_METHOD', default='')
            if not self.default_http_method in ('GET', 'POST'):
                self.default_http_method = 'POST'

            self.extra_fs_vars = config.get('common', 'EXTRA_FS_VARS', default='')

            # get call_heartbeat url
            self.call_heartbeat_url = config.get('rest_server', 'CALL_HEARTBEAT_URL', default='')

            # get record url
            self.record_url = config.get('rest_server', 'RECORD_URL', default='')

            # load cache params
            # load cache params
            self.cache['url'] = config.get('common', 'CACHE_URL', default='')
            self.cache['script'] = config.get('common', 'CACHE_SCRIPT', default='')
            if not self.cache['url'] or not self.cache['script']:
                self.cache = {}

            # get pid file for reloading outbound server (ugly hack ...)
            try:
                self.fs_out_pidfile = self._pidfile.replace('rest-', 'outbound-')
            except Exception, e:
                self.fs_out_pidfile = None

            # create new logger if reloading
            if reload:
                self.create_logger(config=config)
                self.log.warn("New logger %s" % str(self.log))

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
        self._rest_inbound_socket.log = self.log
        self.log.warn("Reload done")

    def do_daemon(self):
        """This will daemonize the current application

        Two settings from our configuration files are also used to run the
        daemon under a determine user & group.

        USER : determine the user running the daemon
        GROUP : determine the group running the daemon
        """
        # get user/group from config
        user = self._config.get('rest_server', 'USER', default=None)
        group = self._config.get('rest_server', 'GROUP', default=None)
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
        self._rest_inbound_socket.exit()

    def start(self):
        """start method is where we decide to :
            * catch term signal
            * run as daemon
            * start the http server
            * connect to Freeswitch via our Inbound Socket interface
            * wait even if it takes forever, ever, ever, evveeerrr...
        """
        self.log.info("RESTServer starting ...")
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        gevent.signal(signal.SIGHUP, self.sig_hup)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        # connection counter
        retries = 1
        # start http server
        self.http_proc = gevent.spawn(self.http_server.serve_forever)
        if self._ssl:
            self.log.info("RESTServer started at: 'https://%s'" % self.http_address)
        else:
            self.log.info("RESTServer started at: 'http://%s'" % self.http_address)
        # Start inbound socket
        try:
            while self._run:
                try:
                    self.log.info("Trying to connect to FreeSWITCH at: %s" \
                                            % self.fs_inbound_address)
                    self._rest_inbound_socket.connect()
                    # reset retries when connection is a success
                    retries = 1
                    self.log.info("Connected to FreeSWITCH")
                    # serve forever
                    self._rest_inbound_socket.serve_forever()
                except ConnectError, e:
                    if self._run is False:
                        break
                    self.log.error("Connect failed: %s" % str(e))
                # sleep after connection failure
                sleep_for = retries * 10
                self.log.error("Reconnecting in %d seconds" % sleep_for)
                gevent.sleep(sleep_for)
                # don't sleep more than 30 secs
                if retries < 3:
                    retries += 1
        except (SystemExit, KeyboardInterrupt):
            pass
        # kill http server
        self.http_proc.kill()
        # finish here
        self.log.info("RESTServer Exited")


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
        pidfile='/tmp/plivo_rest.pid'

    server = PlivoRestServer(configfile=configfile, pidfile=pidfile,
                                                        daemon=False)
    server.start()


if __name__ == '__main__':
    main()
