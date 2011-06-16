# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Outbound Event Socket class

This manage Event Socket communication with the Freeswitch Server
"""

import gevent
from gevent.server import StreamServer
from gevent.timeout import Timeout

from plivo.core.freeswitch.eventsocket import EventSocket
from plivo.core.freeswitch.transport import OutboundTransport
from plivo.core.errors import ConnectError


BACKLOG = 2048


class OutboundEventSocket(EventSocket):
    '''
    FreeSWITCH Outbound Event Socket.

    A new instance of this class is created for every call/ session from FreeSWITCH.
    '''
    def __init__(self, socket, address, filter="ALL",
                 connect_timeout=60, eventjson=True, 
                 pool_size=5000, trace=False):
        EventSocket.__init__(self, filter, eventjson, pool_size, trace=trace)
        self.transport = OutboundTransport(socket, address, connect_timeout)
        self._uuid = None
        self._channel = None
        # Runs the main function .
        try:
            self.trace("run now")
            self.run()
            self.trace("run done")
        finally:
            self.trace("disconnect now")
            self.disconnect()
            self.trace("disconnect done")

    def connect(self):
        super(OutboundEventSocket, self).connect()
        # Starts event handler for this client/session.
        self.start_event_handler()

        # Sends connect and sets timeout while connecting.
        timer = Timeout(self.transport.get_connect_timeout())
        timer.start()
        try:
            connect_response = self._protocol_send("connect")
            if not connect_response.is_success():
                raise ConnectError("Error while connecting")
        except Timeout:
            raise ConnectError("Timeout connecting")
        finally:
            timer.cancel()

        # Sets channel and channel unique id from this event
        self._channel = connect_response
        self._uuid = connect_response.get_header("Unique-ID")

        # Set connected flag to True
        self.connected = True

        # Sets event filter or raises ConnectError
        if self._filter:
            if self._is_eventjson:
                self.trace("using eventjson")
                filter_response = self.eventjson(self._filter)
            else:
                self.trace("using eventplain")
                filter_response = self.eventplain(self._filter)
            if not filter_response.is_success():
                raise ConnectError("Event filter failure")

    def get_channel(self):
        return self._channel

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
    # Sets the maximum number of consecutive accepts that a process may perform on
    # a single wake up. High values give higher priority to high connection rates,
    # while lower values give higher priority to already established connections.
    max_accept = 50000

    # the number of seconds to sleep in case there was an error in accept() call
    # for consecutive errors the delay will double until it reaches max_delay
    # when accept() finally succeeds the delay will be reset to min_delay again
    min_delay = 0.001
    max_delay = 0.01

    def __init__(self, address, handle_class, filter="ALL"):
        self._filter = filter
        #Define the Class that will handle process when receiving message
        self._requestClass = handle_class
        StreamServer.__init__(self, address, self.do_handle, 
                        backlog=BACKLOG, spawn=gevent.spawn_raw)

    def do_handle(self, socket, address):
        try:
            self.handle_request(socket, address)
        finally:
            self.finish_request(socket, address)

    def finish_request(self, socket, address):
        try: 
            socket.shutdown(2)
        except:
            pass
        try: 
            socket.close()
        except:
            pass

    def handle_request(self, socket, address):
        self._requestClass(socket, address, self._filter)
        







if __name__ == '__main__':
    outboundserver = OutboundServer(('127.0.0.1', 8084), OutboundEventSocket)
    outboundserver.serve_forever()
