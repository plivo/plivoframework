# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Inbound Event Socket class
"""

import gevent
import gevent.event
from gevent.timeout import Timeout

from plivo.core.freeswitch.eventsocket import EventSocket
from plivo.core.freeswitch.transport import InboundTransport
from plivo.core.errors import ConnectError


class InboundEventSocket(EventSocket):
    '''
    FreeSWITCH Inbound Event Socket
    '''
    def __init__(self, host, port, password, filter="ALL",
             eventjson=True, pool_size=5000, trace=False, connect_timeout=20):
        EventSocket.__init__(self, filter, eventjson, pool_size, trace=trace)
        # add the auth request event callback
        self._response_callbacks['auth/request'] = self._auth_request
        self._wait_auth_event = gevent.event.AsyncResult()
        self.password = password
        self.transport = InboundTransport(host, port, connect_timeout=connect_timeout)

    def _auth_request(self, event):
        '''
        Receives auth/request callback.

        Only used by InboundEventSocket.
        '''
        # Wake up waiting request
        self._wait_auth_event.set(True)

    def _wait_auth_request(self):
        '''
        Waits until auth/request event is received.
        '''
        # Sets timeout to wait for auth/request
        timer = Timeout(self.transport.get_connect_timeout())
        timer.start()
        try:
            # When auth/request is received,
            # _auth_request method will wake up async result 
            # so we will just wait this event here.
            return self._wait_auth_event.get()
        except Timeout:
            raise ConnectError("Timeout waiting auth/request")
        finally:
            timer.cancel()

    def connect(self):
        '''
        Connects to mod_eventsocket, authenticates and sets event filter.

        Returns True on success or raises ConnectError exception on failure.
        '''
        try:
            self.run()
        except ConnectError, e:
            self.connected = False
            raise

    def run(self):
        super(InboundEventSocket, self).connect()
        # Connects transport, if connection fails, raise ConnectError
        try:
            self.transport.connect()
        except Exception, e:
            raise ConnectError("Transport failure: %s" % str(e))
        # Sets connected flag to True
        self.connected = True

        # Be sure command pool is empty before starting
        self._flush_commands()

        # Starts handling events
        self.start_event_handler()

        # Waits for auth/request, if timeout, raises ConnectError
        self._wait_auth_request()

        # We are ready now !
        # Authenticate or raise ConnectError
        auth_response = self.auth(self.password)
        if not auth_response.is_reply_text_success():
            raise ConnectError("Auth failure")

        # Sets event filter or raises ConnectError
        if self._filter:
            if self._is_eventjson:
                filter_response = self.eventjson(self._filter)
            else:
                filter_response = self.eventplain(self._filter)
            if not filter_response.is_reply_text_success():
                raise ConnectError("Event filter failure")
        return

    def serve_forever(self):
        """
        Starts waiting for events in endless loop.
        """
        while self.is_connected():
            gevent.sleep(0.1)
