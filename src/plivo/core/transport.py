# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


"""
Transport class
"""

class Transport(object):
    def __init__(self):
        self.closed = True

    def write(self, data):
        self.sockfd.write(bytearray(data, "utf-8"))
        self.sockfd.flush()

    def read_line(self):
        return self.sockfd.readline()

    def read(self, length):
        return self.sockfd.read(length)

    def close(self):
        if self.closed:
            return
        try:
            self.sock.shutdown(2)
        except:
            pass
        try:
            self.sock.close()
        except:
            pass
        self.closed = True

    def get_connect_timeout(self):
        return self.timeout
