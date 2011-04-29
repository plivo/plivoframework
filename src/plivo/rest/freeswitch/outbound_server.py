# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey; monkey.patch_all()
import os

from plivo.core.freeswitch.outboundsocket import OutboundServer
from plivo.utils.logger import StdoutLogger

from outbound_socket import PlivoOutboundEventSocket
import helpers


class PlivoOutboundServer(OutboundServer):
    def __init__(self, handle_class, configfile, filter=None, log = StdoutLogger()):
        self.config = helpers.get_config(configfile)
        self.log = log
        fs_outbound_address = helpers.get_conf_value(self.config, 'freeswitch', 'FS_OUTBOUND_ADDRESS')
        fs_host, fs_port = fs_outbound_address.split(':')
        fs_port = int(fs_port)
        self.log.info("Starting Outbound Server %s ..." % str(fs_outbound_address))
        self.default_answer_url = helpers.get_conf_value(self.config, 'freeswitch', 'DEFAULT_ANSWER_URL')
        OutboundServer.__init__(self, (fs_host,fs_port) , handle_class, filter)

    def do_handle(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._handle_class(socket, address, self.log, self.default_answer_url, filter=self._filter)


if __name__ == '__main__':
    outboundserver = PlivoOutboundServer(PlivoOutboundEventSocket, configfile='./plivo_rest.conf')
    outboundserver.serve_forever()
