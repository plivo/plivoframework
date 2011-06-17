# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Freeswitch Transport classes
"""

import gevent.socket as socket
from plivo.core.errors import ConnectError
from plivo.core.transport import Transport


class InboundTransport(Transport):
    def __init__(self, host, port, connect_timeout=5):
        self.host = host
        self.port = port
        self.timeout = connect_timeout
        self.sockfd = None
        self.closed = True

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.sockfd = self.sock.makefile()
        self.closed = False

    def write(self, data):
        if self.closed:
            raise ConnectError('not connected')
        self.sockfd.write(data)
        self.sockfd.flush()



class OutboundTransport(Transport):
    def __init__(self, socket, address, connect_timeout=5):
        inactivity_timeout = 3600
        self.sock = socket
        # safe guard inactivity timeout
        self.sock.settimeout(inactivity_timeout)
        self.sockfd = socket.makefile()
        self.address = address
        self.timeout = connect_timeout
        self.closed = False

