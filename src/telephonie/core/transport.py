# -*- coding: utf-8 -*-
"""
Transport class
"""

import gevent.socket as socket


class Transport(object):
    def __init__(self, host, port, connectTimeout=5):
        self.host = host
        self.port = port
        self.timeout = connectTimeout

    def getConnectTimeout(self):
        return self.timeout

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(None)
        self.sockfd = self.sock.makefile()

    def write(self, data):
        self.sockfd.write(data)
        self.sockfd.flush()

    def readline(self):
        return self.sockfd.readline()

    def read(self, length):
        return self.sockfd.read(length)

    def close(self):
        self.sock.close()

