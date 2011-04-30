# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from gevent import monkey; monkey.patch_all()
import gevent
from gevent.wsgi import WSGIServer
import os
import sys
import signal
from flask import Flask
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger
from plivo.core.errors import ConnectError
from plivo.rest.freeswitch.rest_api import PlivoRestApi
from plivo.rest.freeswitch.inbound_socket import RESTInboundSocket
from plivo.rest.freeswitch import urls, helpers


class PlivoRestServer(PlivoRestApi):
    name = "PlivoRestServer"

    def __init__(self, configfile, daemon=False):
        self._daemon = daemon
        self._run = False
        # load config
        self._config = helpers.get_config(configfile)
        # create flask app
        self.app = Flask(self.name)
        self.app.secret_key = helpers.get_conf_value(self._config, 'rest_server', 'SECRET_KEY')
        # create logger
        self.create_logger()
        # create rest server
        self.fs_inbound_address = helpers.get_conf_value(self._config, 'freeswitch', 'FS_INBOUND_ADDRESS')
        fs_host, fs_port = self.fs_inbound_address.split(':', 1)
        fs_port = int(fs_port)
        fs_password = helpers.get_conf_value(self._config, 'freeswitch', 'FS_PASSWORD')
        self._rest_inbound_socket = RESTInboundSocket(fs_host, fs_port, fs_password, filter='ALL', log=self.log)
        fs_out_address = helpers.get_conf_value(self._config, 'freeswitch', 'FS_OUTBOUND_ADDRESS')
        self._rest_inbound_socket.fs_outbound_address = fs_out_address
        # expose api functions to flask app
        for path, func_desc in urls.URLS.iteritems():
            func, methods = func_desc
            fn = getattr(self, func.__name__)
            self.app.add_url_rule(path, func.__name__, fn, methods=methods)
        # create wsgi server
        self.http_address = helpers.get_conf_value(self._config, 'rest_server', 'HTTP_ADDRESS')
        http_host, http_port = self.http_address.split(':', 1)
        http_port = int(http_port)
        self.http_server = WSGIServer((http_host, http_port), self.app, log=self.log)

    def create_logger(self):
        if self._daemon is False:
            self.log = StdoutLogger()
            self.log.set_debug()
            self.app.debug = True
        else:
            logtype = helpers.get_conf_value(self._config, 'rest_server', 'LOG_TYPE')
            if logtype == 'file':
                logfile = helpers.get_conf_value(self._config, 'rest_server', 'LOG_FILE')
                self.log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = helpers.get_conf_value(self._config, 'rest_server', 'SYSLOG_ADDRESS')
                syslogfacility = helpers.get_conf_value(self._config, 'rest_server', 'SYSLOG_FACILITY')
                self.log = SysLogger(syslogaddress, syslogfacility)
            else:
                self.log = StdoutLogger()
            if helpers.get_conf_value(self._config, 'rest_server', 'DEBUG') == 'true':
                self.log.set_debug()
                self.app.debug = True
            else:
                self.log.set_info()
        self.log.name = self.name
        self.app._logger = self.log

    def do_daemon(self):
        # get user/group from config 
        try:
            user = helpers.get_conf_value(self._config, 'rest_server', 'REST_SERVER_USER')
            group = helpers.get_conf_value(self._config, 'rest_server', 'REST_SERVER_GROUP')
        # default is to get currents user/group
        except:
            uid = os.getuid()
            gid = os.getgid()
            user = pwd.getpwuid(uid)[0]
            group = grp.getgrgit(gid)[0]
        # get pidfile
        pidfile = helpers.get_conf_value(self._config, 'rest_server', 'REST_SERVER_PIDFILE')
        # daemonize now
        plivo.utils.daemonize.daemon(user,
                                     group,
                                     path='/',
                                     pidfile=pidfile,
                                     other_groups=()
                                    )

    def sig_term(self, *args):
        self.stop()
        self.log.warn("Shutdown ...")
        sys.exit(0)

    def stop(self):
        self._run = False
        self._rest_inbound_socket.exit()

    def start(self):
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        retry_seconds = 10.0
        # start http server
        self.http_proc = gevent.spawn(self.http_server.serve_forever)
        # start inbound socket
        try:
            while self._run:
                try:
                    self.log.info("Trying to connect to FreeSWITCH at: %s" % self.fs_inbound_address)
                    self._rest_inbound_socket.connect()
                    self.log.info("Connected to FreeSWITCH")
                    self.log.info("REST Server started at: 'http://%s'\n" % self.http_address)
                except ConnectError, e:
                    if self._run is False:
                        break
                    self.log.error("Connect failed: %s" % str(e))
                self.log.error("Reconnecting in %s seconds" % retry_seconds)
                gevent.sleep(retry_seconds)
                retry_seconds += 20.0
        except (SystemExit, KeyboardInterrupt):
            pass
        # kill http server
        self.http_proc.kill()
        # finish here
        self.log.info("REST Server Exited")


if __name__ == '__main__':
    server = PlivoRestServer(configfile='./plivo_rest.conf', daemon=False)
    server.start()
