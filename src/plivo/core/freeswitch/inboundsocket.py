# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Inbound Event Socket class
"""

import gevent
from gevent.timeout import Timeout
from plivo.core.freeswitch.eventsocket import EventSocket
from plivo.core.freeswitch.transport import InboundTransport
from plivo.core.errors import ConnectError


class InboundEventSocket(EventSocket):
    '''
    FreeSWITCH Inbound Event Socket
    '''
    def __init__(self, host, port, password, filter="ALL", 
                 pool_size=500, connect_timeout=5, eventjson=True):
        EventSocket.__init__(self, filter, pool_size, eventjson)
        self.password = password
        self.transport = InboundTransport(host, port, connect_timeout=connect_timeout)

    def _wait_auth_request(self):
        '''
        Waits until auth/request event is received.
        '''
        # Sets timeout to wait for auth/request
        timer = Timeout(self.transport.get_connect_timeout())
        timer.start()
        try:
            # When auth/request is received,
            # _authRequest method in EventSocket will push this event to queue
            # so we will just wait this event here.
            return self._response_queue.get()
        except Timeout:
            raise ConnectError("Timeout waiting auth/request")
        finally:
            timer.cancel()

    def connect(self):
        '''
        Connects to mod_eventsocket, authenticates and sets event filter.

        Returns True on success or raises ConnectError exception on failure.
        '''
        super(InboundEventSocket, self).connect()
        # Connects transport, if connection fails, raise ConnectError
        try:
            self.transport.connect()
        except Exception, e:
            raise ConnectError("Transport failure: %s" % str(e))

        # Be sure queue response is empty before starting
        for x in range(1000):
            if self._response_queue.empty():
                break
            self._response_queue.get_nowait()

        # Starts handling events
        self.start_event_handler()

        # Waits for auth/request, if timeout, raises ConnectError
        self._wait_auth_request()

        # We are ready now !
        # Authenticate or raise ConnectError
        auth_response = self.auth(self.password)
        if not auth_response.is_reply_text_success():
            self.disconnect()
            raise ConnectError("Auth failure")

        # Sets event filter or raises ConnectError
        if self._filter:
            #filter_response = self.eventplain(self._filter)
            filter_response = self.eventjson(self._filter)
            if not filter_response.is_reply_text_success():
                self.disconnect()
                raise ConnectError("Event filter failure")

        # Sets connected flag to True
        self.connected = True
        return True

    def exit(self):
        super(InboundEventSocket, self).exit()
        self.disconnect()

    def serve_forever(self):
        """
        Starts waiting for events in endless loop.
        """
        while self.is_connected():
            gevent.sleep(0.1)

