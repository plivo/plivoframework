# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


from gevent import monkey
monkey.patch_all()

import grp
import os
import pwd
import signal
import sys

import gevent


from plivo.core.freeswitch import outboundsocket
from plivo.rest.freeswitch.outboundsocket import PlivoOutboundEventSocket
from plivo.rest.freeswitch import helpers
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger, DummyLogger

"""
PlivoOutboundServer is our event_socket server listening for connection
with Freeswitch.

This server is listening by default on 127.0.0.1:8084

"""


class PlivoOutboundServer(outboundsocket.OutboundServer):
    def __init__(self, configfile, daemon=False,
                    pidfile='/tmp/plivo_outbound.pid'):
        self._request_id = 0
        self._daemon = daemon
        self._run = False
        self._pidfile = pidfile
        # load config
        self._config = helpers.get_config(configfile)
        # set trace flag
        self._trace = helpers.get_conf_value(self._config,
                            'freeswitch', 'FS_OUTBOUND_TRACE') == 'true'
        # create logger
        self.create_logger()
        # create outbound server
        self.fs_outbound_address = helpers.get_conf_value(self._config,
                                        'freeswitch', 'FS_OUTBOUND_ADDRESS')
        fs_host, fs_port = self.fs_outbound_address.split(':', 1)
        fs_port = int(fs_port)
        self.default_answer_url = helpers.get_conf_value(self._config,
                                        'freeswitch', 'DEFAULT_ANSWER_URL')
        self.auth_id = helpers.get_conf_value(self._config,
                                        'rest_server', 'AUTH_ID')
        self.auth_token = helpers.get_conf_value(self._config,
                                        'rest_server', 'AUTH_TOKEN')
        self.default_hangup_url = helpers.get_conf_value(self._config,
                                        'freeswitch', 'DEFAULT_HANGUP_URL')
        self.default_http_method = helpers.get_conf_value(self._config,
                                        'rest_server', 'DEFAULT_HTTP_METHOD')
        if not self.default_http_method in ('GET', 'POST'):
            self.default_http_method = 'POST'

        # This is where we define the connection with the
        # Plivo XML element Processor
        outboundsocket.OutboundServer.__init__(self, (fs_host, fs_port),
                                PlivoOutboundEventSocket, filter=None)

    def _get_request_id(self):
        try:
            self._request_id += 1
        except OverflowError:
            self._request_id = 1
        return self._request_id

    def handle_request(self, socket, address):
        request_id = self._get_request_id()
        self.log.info("(%d) New request from %s" % (request_id, str(address)))
        self._requestClass(socket, address, self.log,
                           default_answer_url=self.default_answer_url,
                           default_hangup_url=self.default_hangup_url,
                           default_http_method = self.default_http_method,
                           auth_id=self.auth_id,
                           auth_token=self.auth_token,
                           request_id=request_id,
                           trace=self._trace
                           )
        self.log.info("(%d) End request from %s" % (request_id, str(address)))

    def create_logger(self):
        if self._daemon is False:
            logtype = helpers.get_conf_value(self._config,
                                                'freeswitch', 'LOG_TYPE')
            if logtype == 'dummy':
                self.log = DummyLogger()
            else:
                self.log = StdoutLogger()
            self.log.set_debug()
        else:
            logtype = helpers.get_conf_value(self._config,
                                                'freeswitch', 'LOG_TYPE')
            if logtype == 'file':
                logfile = helpers.get_conf_value(self._config,
                                                'freeswitch', 'LOG_FILE')
                self.log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = helpers.get_conf_value(self._config,
                                            'freeswitch', 'SYSLOG_ADDRESS')
                syslogfacility = helpers.get_conf_value(self._config,
                                            'freeswitch', 'SYSLOG_FACILITY')
                self.log = SysLogger(syslogaddress, syslogfacility)
            elif logtype == 'dummy':
                self.log = DummyLogger()
            else:
                self.log = StdoutLogger()
            debug_mode = helpers.get_conf_value(self._config,
                                                'freeswitch', 'DEBUG')
            if debug_mode == 'true' or self._trace is True:
                self.log.set_debug()
            else:
                self.log.set_info()

    def do_daemon(self):
        # get user/group from config
        user = helpers.get_conf_value(self._config,
                                    'freeswitch', 'FS_OUTBOUND_USER')
        group = helpers.get_conf_value(self._config,
                                    'freeswitch', 'FS_OUTBOUND_GROUP')
        if not user or not group:
            uid = os.getuid()
            user = pwd.getpwuid(uid)[0]
            gid = os.getgid()
            group = grp.getgrgid(gid)[0]
        # daemonize now
        plivo.utils.daemonize.daemon(user, group, path='/',
                                    pidfile=self._pidfile, other_groups=())

    def sig_term(self, *args):
        self.stop()
        self.log.warn("Shutdown ...")
        sys.exit(0)

    def start(self):
        self.log.info("Starting OutboundServer ...")
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        super(PlivoOutboundServer, self).start()
        self.log.info("OutboundServer started at '%s'" \
                                    % str(self.fs_outbound_address))
        self.serve_forever()
        self.log.info("OutboundServer Exited")


if __name__ == '__main__':
    outboundserver = PlivoOutboundServer(
                                configfile='./etc/plivo/default.conf',
                                daemon=False)
    outboundserver.start()
