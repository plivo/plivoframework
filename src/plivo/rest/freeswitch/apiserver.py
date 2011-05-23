# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from gevent import monkey
monkey.patch_all()

import grp
import os
import pwd
import signal
import sys

from flask import Flask
import gevent
from gevent.wsgi import WSGIServer

from plivo.core.errors import ConnectError
from plivo.rest.freeswitch.api import PlivoRestApi
from plivo.rest.freeswitch.inboundsocket import RESTInboundSocket
from plivo.rest.freeswitch import urls, helpers
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger


class PlivoRestServer(PlivoRestApi):
    """Class PlivoRestServer"""
    name = "PlivoRestServer"

    def __init__(self, configfile, daemon=False,
                        pidfile='/tmp/plivo_rest.pid'):
        """Constructor

        Initialize main properties such as daemon, pidfile, config, etc...

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
        # load config
        self._config = helpers.get_config(configfile)
        # create flask app
        self.app = Flask(self.name)
        self.app.secret_key = helpers.get_conf_value(self._config,
                                                'rest_server', 'SECRET_KEY')
        self.app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
        # create logger
        self.create_logger()
        # create rest server
        self.fs_inbound_address = helpers.get_conf_value(self._config,
                                        'freeswitch', 'FS_INBOUND_ADDRESS')
        fs_host, fs_port = self.fs_inbound_address.split(':', 1)
        fs_port = int(fs_port)
        fs_password = helpers.get_conf_value(self._config,
                                                'freeswitch', 'FS_PASSWORD')
        # get auth id and auth token
        self.auth_id = helpers.get_conf_value(self._config,
                                        'rest_server', 'AUTH_ID')
        self.auth_token = helpers.get_conf_value(self._config,
                                        'rest_server', 'AUTH_TOKEN')
        # get outbound socket host/port
        fs_out_address = helpers.get_conf_value(self._config,
                                        'freeswitch', 'FS_OUTBOUND_ADDRESS')
        fs_out_host, fs_out_port  = fs_out_address.split(':', 1)
        # if outbound host is 0.0.0.0, send to 127.0.0.1
        if fs_out_host == '0.0.0.0':
            fs_out_address = '127.0.0.1:%s' % fs_out_port

        default_http_method = helpers.get_conf_value(self._config,
                                        'rest_server', 'DEFAULT_HTTP_METHOD')
        if not default_http_method or \
                            default_http_method not in ('GET', 'POST'):
            self.default_http_method = 'POST'
        # create inbound socket instance
        self._rest_inbound_socket = RESTInboundSocket(fs_host, fs_port,
                            fs_password, outbound_address=fs_out_address,
                            auth_id=self.auth_id,
                            auth_token=self.auth_token,
                            filter='ALL', log=self.log,
                            default_http_method = self.default_http_method)
        # expose api functions to flask app
        for path, func_desc in urls.URLS.iteritems():
            func, methods = func_desc
            fn = getattr(self, func.__name__)
            self.app.add_url_rule(path, func.__name__, fn, methods=methods)
        # create wsgi server
        self.http_address = helpers.get_conf_value(self._config,
                                            'rest_server', 'HTTP_ADDRESS')
        http_host, http_port = self.http_address.split(':', 1)
        http_port = int(http_port)
        self.http_server = WSGIServer((http_host, http_port),
                                       self.app, log=self.log)

    def create_logger(self):
        """This will create a logger

        Based on the settings in the configuration file,
        LOG_TYPE will determine if we will log in file, syslog or stdout

        To log in file we use the following setting :
        LOG_FILE = /tmp/plivo-rest.log

        To log to syslog we have several settings to configure the logging :
            * LOG_TYPE = syslog
            * SYSLOG_ADDRESS = /dev/log
            * SYSLOG_FACILITY = local0
        """

        if self._daemon is False:
            self.log = StdoutLogger()
            self.log.set_debug()
            self.app.debug = True
        else:
            logtype = helpers.get_conf_value(self._config,
                                                'rest_server', 'LOG_TYPE')
            if logtype == 'file':
                logfile = helpers.get_conf_value(self._config,
                                                'rest_server', 'LOG_FILE')
                self.log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = helpers.get_conf_value(self._config,
                                            'rest_server', 'SYSLOG_ADDRESS')
                syslogfacility = helpers.get_conf_value(self._config,
                                            'rest_server', 'SYSLOG_FACILITY')
                self.log = SysLogger(syslogaddress, syslogfacility)
            else:
                self.log = StdoutLogger()

            debug_mode = helpers.get_conf_value(self._config,
                                                    'rest_server', 'DEBUG')
            if  debug_mode == 'true':
                self.log.set_debug()
                self.app.debug = True
            else:
                self.log.set_info()
        self.log.name = self.name
        self.app._logger = self.log

    def do_daemon(self):
        """This will daemonize the current application

        Two settings from our configuration files are also used to run the
        daemon under a determine user & group.

        REST_SERVER_USER : determine the user running the daemon
        REST_SERVER_GROUP : determine the group running the daemon
        """
        # get user/group from config
        user = helpers.get_conf_value(self._config,
                                        'rest_server', 'REST_SERVER_USER')
        group = helpers.get_conf_value(self._config,
                                        'rest_server', 'REST_SERVER_GROUP')
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
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        # connection counter
        retries = 1
        # start http server
        self.http_proc = gevent.spawn(self.http_server.serve_forever)
        self.log.info("RESTServer started at: 'http://%s'" % self.http_address)
        # start inbound socket
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
                # don't sleep more than 120 secs
                if retries < 12:
                    retries += 1
        except (SystemExit, KeyboardInterrupt):
            pass
        # kill http server
        self.http_proc.kill()
        # finish here
        self.log.info("RESTServer Exited")


if __name__ == '__main__':
    server = PlivoRestServer(configfile='../../../config/default.conf',
                                                                daemon=False)
    server.start()
