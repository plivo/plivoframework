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

from plivo.core.freeswitch.outboundsocket import OutboundServer
from plivo.rest.freeswitch.outbound_socket import PlivoOutboundEventSocket
from plivo.rest.freeswitch import helpers
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger


"""
PlivoOutboundServer is our event_socket server listening for connection 
with Freeswitch. 

This server is listening by default on 127.0.0.1:8084

"""


class PlivoOutboundServer(OutboundServer):
    def __init__(self, configfile, daemon=False,
                            pidfile='/tmp/plivo_outbound.pid', filter=None):
        self._request_id = 0
        self._daemon = daemon
        self._run = False
        self._pidfile = pidfile
        # load config
        self._config = helpers.get_config(configfile)
        # create logger
        self.create_logger()
        # create outbound server
        self.fs_outbound_address = helpers.get_conf_value(self._config,
                                        'freeswitch', 'FS_OUTBOUND_ADDRESS')
        fs_host, fs_port = self.fs_outbound_address.split(':', 1)
        fs_port = int(fs_port)
        self.default_answer_url = helpers.get_conf_value(self._config,
                                        'freeswitch', 'DEFAULT_ANSWER_URL')
        self.default_hangup_url = helpers.get_conf_value(self._config,
                                        'freeswitch', 'DEFAULT_HANGUP_URL')
        #This is where we define the connection with the
        #Plivo XML grammar Processor
        OutboundServer.__init__(self, (fs_host, fs_port),
                                            PlivoOutboundEventSocket, filter)

    def _get_request_id(self):
        try:
            self._request_id += 1
        except OverflowError:
            self._request_id = 1
        return self._request_id

    def do_handle(self, socket, address):
        request_id = self._get_request_id()
        self.log.info("(%d) New request from %s" % (request_id, str(address)))
        self._handle_class(socket, address, self.log, 
                           default_answer_url=self.default_answer_url,
                           default_hangup_url=self.default_hangup_url,
                           request_id=request_id,
                           filter=self._filter)
        self.log.info("(%d) End request from %s" % (request_id, str(address)))

    def create_logger(self):
        if self._daemon is False:
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
            else:
                self.log = StdoutLogger()
            debug_mode = helpers.get_conf_value(self._config,
                                                        'freeswitch', 'DEBUG')
            if debug_mode == 'true':
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

    def stop(self):
        self._run = False
        self.kill()

    def start(self):
        self.log.info("Starting OutboundServer ...")
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        super(PlivoOutboundServer, self).start()
        self.log.info("OutboundServer started at '%s'"
                                            % str(self.fs_outbound_address))
        try:
            while self._run:
                gevent.sleep(1.0)
        except (SystemExit, KeyboardInterrupt):
            pass
        self.log.info("OutboundServer Exited")


if __name__ == '__main__':
    outboundserver = PlivoOutboundServer(
                                configfile='../../../config/default.conf',
                                daemon=False)
    outboundserver.start()
