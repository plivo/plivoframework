# -*- coding: utf-8 -*-
"""
Outbound Event Socket class
"""

from gevent.server import StreamServer
from gevent.timeout import Timeout
from telephonie.core.eventsocket import EventSocket
from telephonie.core.transport import OutboundTransport
from telephonie.core.errors import ConnectError



class OutboundEventSocket(EventSocket):
    '''
    FreeSWITCH Outbound Event Socket
    '''
    def __init__(self, socket, address, filter="ALL", poolSize=500, connectTimeout=5):
        EventSocket.__init__(self, filter, poolSize)
        self.transport = OutboundTransport(socket, address, connectTimeout)
        self._uuid = None
        self._client = None
        # connect
        self.connect()
        # now run 
        try:
            self.run()
        finally:
            # finish
            self.disconnect()

    def connect(self):
        # start event handler for this client
        self.startEventHandler()

        # send connect and set timeout while connecting
        timer = Timeout(self.transport.getConnectTimeout())
        timer.start()
        try:
            connectResponse = self._protocolSend("connect")
            if not connectResponse.isSuccess():
                self.disconnect()
                raise ConnectError("Error while connecting")
        except Timeout:
            self.disconnect()
            raise ConnectError("Timeout connecting") 
        finally:
            timer.cancel()

        # set channel and channel unique id from this event
        self._channel = response
        self._uuid = response.getHeader("Channel-Unique-ID")

        # set event filter or raise ConnectError
        if self._filter:
            filterResponse = self.eventplain(self._filter)
            if not filterResponse.isSuccess():
                self.disconnect()
                raise ConnectError("Event filter failure")

        # set connected flag to True
        self.connected = True

    def getChannel(self):
        return self.client

    def getChannelUniqueID(self):
        return self._uuid

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

