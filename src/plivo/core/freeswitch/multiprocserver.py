# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey; monkey.patch_all()
import socket
import sys
import os    
try:
    import multiprocessing
except ImportError:
    import processing as multiprocessing


BACKLOG = 2048


class Process(multiprocessing.Process):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}):
        multiprocessing.Process.__init__(self, group, target, name, args, kwargs)

    def run(self):
        if self._target:
            try:
                self._target(*self._args, **self._kwargs)
            except KeyboardInterrupt:
                raise SystemExit()


class OutboundServer(object):
    def __init__(self, address, handle_class, filter='ALL'):
        self.hostname, self.port = address
        self.running = False
        self._filter = filter
        # Define the Class that will handle process when receiving message
        self._handle_class = handle_class
        self._pid = int(os.getpid())
                                         
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.hostname, self.port))
        self.socket.listen(BACKLOG)

    def loop(self):
        self._run = True
        try:
            while self._run:
                conn, address = self.socket.accept()
                process = Process(target=self.do_handle, args=(conn, address))
                process.daemon = True
                process.start()
        except (SystemExit, KeyboardInterrupt):
            pass

    def kill(self):
        pass

    def do_handle(self, conn, address):
        self._handle_class(socket, address, self._filter)

