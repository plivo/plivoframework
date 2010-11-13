# -*- coding: utf-8 -*-
"""
Outbound Event Socket class
"""

import gevent.monkey
gevent.monkey.patch_all()
from gevent.server import StreamServer
from gevent.timeout import Timeout
from telephonie.core.eventsocket import EventSocket
from telephonie.core.transport import OutboundTransport
from telephonie.core.errors import ConnectError



class OutboundEventSocket(EventSocket):
    '''
    FreeSWITCH Outbound Event Socket
    '''
    def __init__(self, socket, address, filter="ALL", poolSize=50, connectTimeout=5):
        EventSocket.__init__(self, filter, poolSize)
        self._filter = filter
        self.transport = OutboundTransport(socket, address, connectTimeout)
        self.client = None
        # connect
        self.connect()
        # now run 
        self.run()
        # stop handler and close socket 
        self.disconnect()

    def connect(self):
        # start event handler for this client
        self.startEventHandler()

        # send connect and set timeout while connecting
        timer = Timeout(self.transport.getConnectTimeout())
        timer.start()
        try:
            self.client = self._protocolSend("connect")
        except Timeout:
            self.disconnect()
            raise ConnectError("Timeout connecting") 
        finally:
            timer.cancel()

        # set event filter or raise ConnectError
        response = self.eventplain(self._filter)
        if not response.getStatus():
            self.disconnect()
            raise ConnectError("Event filter failure")

        # set connected flag to True
        self.connected = True

    def run(self):
        '''
        This method must be implemented by subclass.

        This is the entry point for outbound application.
        '''
        pass


class OutboundServer(StreamServer):
    '''
    FreeSWITCH Outbound Event Server
    '''
    def __init__(self, address, handle, filter="ALL"):
        self._filter = filter
        self._handleClass = handle
        StreamServer.__init__(self, address, self.doHandle)

    def doHandle(self, socket, address):
        self._handleClass(socket, address, self._filter)




if __name__ == '__main__':
    outboundserver = OutboundServer(('127.0.0.1', 8084), OutboundEventSocket)
    outboundserver.serve_forever()

