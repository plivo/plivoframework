# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Transport class
"""

import gevent.socket as socket
from plivo.core.errors import ConnectError


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
