# -*- coding: utf-8 -*-
"""
Inbound Event Socket class
"""

import gevent
from gevent.timeout import Timeout
from telephonie.core.eventsocket import EventSocket
from telephonie.core.transport import InboundTransport
from telephonie.core.errors import ConnectError


class InboundEventSocket(EventSocket):
    '''
    FreeSWITCH Inbound Event Socket
    '''
    def __init__(self, host, port, password, filter="ALL", poolSize=1000, connectTimeout=5):
        EventSocket.__init__(self, filter, poolSize)
        self.password = password
        self._filter = filter
        self.transport = InboundTransport(host, port, connectTimeout=connectTimeout)

    def _waitAuthRequest(self):
        '''
        Wait until auth/request event was received.
        '''
        # set timeout waiting auth/request
        timer = Timeout(self.transport.getConnectTimeout())
        timer.start()
        try:
            # when auth/request is received, 
            # _authRequest method in BaseEventSocket push this event to queue
            # now we just wait this event
            return self.queue.get()
        except Timeout:
            raise ConnectError("Timeout waiting auth/request") 
        finally:
            timer.cancel()

    def connect(self):
        '''
        Connect to mod_eventsocket, authenticate and set event filter.

        Return True or raise ConnectError exception on failure
        '''
        # connect transport, if connection failed, raise ConnectError
        try:
            self.transport.connect()
        except Exception, e:
            raise ConnectError("Transport failure: %s" % str(e))

        # start handling events
        self.startEventHandler()

        # wait auth/request, if timeout, raise ConnectError
        self._waitAuthRequest()

        # we are ready now !
        # authenticate or raise ConnectError
        response = self.auth(self.password)
        if not response.getStatus():
            self.disconnect()
            raise ConnectError("Auth failure")

        # set event filter or raise ConnectError
        response = self.eventplain(self._filter)
        if not response.getStatus():
            self.disconnect()
            raise ConnectError("Event filter failure")

        # set connected flag to True
        self.connected = True
        return True

    def serve_forever(self):
        """Start waiting events in endless loop.
        """
        while self.isConnected(): 
            gevent.sleep(0.1)


