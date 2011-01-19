# -*- coding: utf-8 -*-
"""
Transport classes
"""

import gevent.socket as socket
from telephonie.core.errors import ConnectError


class Transport(object):
    def write(self, data):
        self.sockfd.write(data)
        self.sockfd.flush()

    def read_line(self):
        return self.sockfd.readline()

    def read(self, length):
        return self.sockfd.read(length)

    def close(self):
        try:
            self.sock.close()
        except:
            pass

    def get_connect_timeout(self):
        return self.timeout


class InboundTransport(Transport):
    def __init__(self, host, port, connect_timeout=5):
        self.host = host
        self.port = port
        self.timeout = connect_timeout
        self.sockfd = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.sockfd = self.sock.makefile()

    def write(self, data):
        if not self.sockfd:
            raise ConnectError('not connected')
        self.sockfd.write(data)
        self.sockfd.flush()
        


class OutboundTransport(Transport):
    def __init__(self, socket, address, connect_timeout=5):
        self.sock = socket
        self.sockfd = socket.makefile()
        self.address = address
        self.timeout = connect_timeout

