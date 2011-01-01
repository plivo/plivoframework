# -*- coding: utf-8 -*-
"""
Websocket server class
"""
from telephonie.utils.logger import StdoutLogger
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
import stderr2log
import os


class WebsocketServer(object):
    """
    Websocket server.
    """
    def __init__(self, host, port, log=None):
        self.running = False
        self.host = host
        self.port = port
        if not log:
            self.log = StdoutLogger()
        else:
            self.log = log
        stderr2log.patch(log)
        self.ws_server = pywsgi.WSGIServer((self.host, self.port), self.application, handler_class=WebSocketHandler, log=self.log)

    def is_running(self):
        """
        Check if server is running.
        """
        return self.running

    def start(self):
        """
        Start websocket server.
        """
        self.log.info("Start Websocket server %s:%d" % (self.host, self.port))
        try:
            self.running = True
            self.ws_server.serve_forever()
        except (SystemExit, KeyboardInterrupt): 
            pass
        self.running = False
        stderr2log.restore()
        self.log.info("Websocket server terminated")

    def application(self, environ, start_response):
        """
        Main application when clients are connecting to server.

        Must be overridden by subclass.
        """
        pass


if __name__ == '__main__':
    server = WebsocketServer('0.0.0.0', 8000)
    server.start()



