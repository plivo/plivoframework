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
    FreeSWITCH Outbound Event Socket.
    
    A new instance of this class is created for every call/ session from FreeSWITCH.
    '''
    def __init__(self, socket, address, filter="ALL", pool_size=500, connect_timeout=5):
        EventSocket.__init__(self, filter, pool_size)
        self.transport = OutboundTransport(socket, address, connect_timeout)
        self._uuid = None
        self._client = None
        # Connects.
        self.connect()
        # Runs the main funtion .
        try:
            self.run()
        finally:
            # Disconnects.
            self.disconnect()

    def connect(self):
        # Starts event handler for this client/session.
        self.start_event_handler()

        # Sends connect and sets timeout while connecting.
        timer = Timeout(self.transport.get_connect_timeout())
        timer.start()
        try:
            connect_response = self._protocol_send("connect")
            if not connect_response.is_success():
                self.disconnect()
                raise ConnectError("Error while connecting")
        except Timeout:
            self.disconnect()
            raise ConnectError("Timeout connecting") 
        finally:
            timer.cancel()

        # Sets channel and channel unique id from this event
        self._channel = connect_response
        self._uuid = connect_response.get_header("Channel-Unique-ID")

        # Sets event filter or raises ConnectError
        if self._filter:
            filter_response = self.eventplain(self._filter)
            if not filter_response.is_success():
                self.disconnect()
                raise ConnectError("Event filter failure")

        # Set connected flag to True
        self.connected = True

    def get_channel(self):
        return self.client

    def get_channel_unique_id(self):
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
    def __init__(self, address, handle_class, filter="ALL"):
        self._filter = filter
        self._handle_class = handle_class
        StreamServer.__init__(self, address, self.do_handle)

    def do_handle(self, socket, address):
        self._handle_class(socket, address, self._filter)




if __name__ == '__main__':
    outboundserver = OutboundServer(('127.0.0.1', 8084), OutboundEventSocket)
    outboundserver.serve_forever()

