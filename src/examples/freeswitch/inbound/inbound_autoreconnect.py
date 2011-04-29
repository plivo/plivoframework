# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import gevent
from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.errors import ConnectError
from plivo.utils.logger import StdoutLogger


class MyInboundEventSocket(InboundEventSocket):
    '''Inbound eventsocket connector that automatically reconnects
    when the freeswitch eventsocket module closed the connection
    '''
    def __init__(self, host, port, password, filter="ALL", pool_size=500, connect_timeout=5):
        InboundEventSocket.__init__(self, host, port, password, filter, pool_size, connect_timeout)
        self.log = StdoutLogger()

    def start(self):
        self.log.info("Start Inbound socket %s:%d with filter %s" \
            % (self.transport.host, self.transport.port, self._filter))
        while True:
            try:
                self.connect()
                self.log.info("Inbound socket connected")
                self.serve_forever()
            except ConnectError, e:
                self.log.error("ConnectError: %s" % str(e))
            except (SystemExit, KeyboardInterrupt):
                break
            self.log.error("Inbound socket closed, try to reconnect ...")
            gevent.sleep(1.0)
        self.log.info("Inbound socket terminated")


if __name__ == '__main__':
    c = MyInboundEventSocket('127.0.0.1', 8021, 'ClueCon')
    c.start()
