# -*- coding: utf-8 -*-
"""
Transport classes
"""

import gevent.socket as socket


class Transport(object):
    def write(self, data):
        self.sockfd.write(data)
        self.sockfd.flush()

    def readline(self):
        return self.sockfd.readline()

    def read(self, length):
        return self.sockfd.read(length)

    def close(self):
        try:
            self.sock.close()
        except:
            pass

    def getConnectTimeout(self):
        return self.timeout


class InboundTransport(Transport):
    def __init__(self, host, port, connectTimeout=5):
        self.host = host
        self.port = port
        self.timeout = connectTimeout

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.sockfd = self.sock.makefile()


class OutboundTransport(Transport):
    def __init__(self, socket, address, connectTimeout=5):
        self.sock = socket
        self.sockfd = socket.makefile()
        self.address = address
        self.timeout = connectTimeout

