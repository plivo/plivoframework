# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.
from gevent import monkey; monkey.patch_all()

from plivo.core.freeswitch.outboundsocket import OutboundServer
from plivo.utils.logger import StdoutLogger

from outbound_socket import XMLOutboundEventSocket
import settings

class AsyncOutboundServer(OutboundServer):
    def __init__(self, address, handle_class, filter=None):
        self.log = StdoutLogger()
        self.log.info("Starting Outbound Server %s ..." % str(address))
        self.default_answer_url = getattr(settings, 'DEFAULT_ANSWER_URL', 'http://127.0.0.1:5000/answered/')
        OutboundServer.__init__(self, address, handle_class, filter)

    def do_handle(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._handle_class(socket, address, self.log, self.default_answer_url, filter=self._filter)


if __name__ == '__main__':
    fs_outbound_address = getattr(settings, 'FS_OUTBOUND_ADDRESS', '127.0.0.1:8084')
    fs_host, fs_port = fs_outbound_address.split(':')
    fs_port = int(fs_port)
    outboundserver = AsyncOutboundServer((fs_host, fs_port), XMLOutboundEventSocket)
    outboundserver.serve_forever()
