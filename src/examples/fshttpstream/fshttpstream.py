# -*- coding: utf-8 -*-
"""
Freeswitch http stream server class
"""
import os
import traceback
from telephonie.utils.logger import StdoutLogger
from gevent import (sleep, spawn, GreenletExit, socket)
import websocketserver
import queueinboundsocket
import client


class FSWebsocketServer(websocketserver.WebsocketServer):
    """
    Freeswitch websocket server.
    """
    def __init__(self, wshost, wsport, fshost, fsport, fspassword, fsfilter='ALL', log=None):
        websocketserver.WebsocketServer.__init__(self, wshost, wsport, log)
        self.fshost = fshost
        self.fsport = fsport
        self.fspassword = fspassword
        self.fsfilter = fsfilter
        self._inbound_process = None
        self._dispatch_process = None
        self.ws_clients = set()
        self.inbound_socket = queueinboundsocket.QueueInboundEventSocket(self.fshost, 
                                                                         self.fsport, 
                                                                         self.fspassword, 
                                                                         self.fsfilter, 
                                                                         log=log)

    def start(self):
        """
        Start inbound connection, dispatcher and listen for websocket clients.
        """
        self._inbound_process = spawn(self.inbound_socket.start)
        self._dispatch_process = spawn(self.dispatch_events)
        super(FSWebsocketServer, self).start()
        self._dispatch_process.kill()
        self._inbound_process.kill()

    def dispatch_events(self):
        """
        Dispatch events to websocket clients.
        """
        self.log.debug("dispatch_events started")
        while self.is_running():
            try:
                ev = self.inbound_socket.wait_for_event()
                self.log.debug(str(ev))
                for c in self.ws_clients:
                    c.push_event(ev)
                sleep(0.005)
            except GreenletExit:
                self.log.warn("dispatch_events stopped")
                return
            except Exception, e:
                self.log.error("In dispatch_events: %s" % str(e))
                [ self.log.error(line) for line in traceback.format_exc().splitlines() ]

    def application(self, environ, start_response):
        """
        Main application when clients are connecting to server.
        """
        if environ["PATH_INFO"] == '/websock':
            ws = None
            c = None
            try:
                ws = environ["wsgi.websocket"]
                client_config = ws.wait()
                c = client.Client(ws, client_config)
                self.ws_clients.add(c)
                self.log.info("New client %s from %s" % (str(id(ws)), environ["REMOTE_ADDR"]))
                self.log.debug("Set client %s from %s with %s" % (str(id(ws)), environ["REMOTE_ADDR"], str(c.get_client_filter())))
                self.log.debug(str(environ))
                while self.is_running():
                    c.consume_event()
                    sleep(0.005)
                return
            except socket.error, e:
                self.log.warn("Websocket %s from %s disconnected" % (str(id(ws)), environ["REMOTE_ADDR"]))
                self.log.debug(str(environ))
                self.ws_clients.discard(c)
                return
            except KeyError:
                self.log.error("Invalid request from %s" % str(environ["REMOTE_ADDR"]))
                self.log.debug(str(environ))
                self.ws_clients.discard(c)
                start_response('400 Bad Request', [('content-type', 'text/plain')])
                return ['Bad Request']
            except Exception, e:
                self.log.error("Error %s" % str(e))
                [ self.log.error(line) for line in traceback.format_exc().splitlines() ]
                self.log.debug(str(environ))
                self.ws_clients.discard(c)
                start_response('500 Internal Server Error', [('content-type', 'text/plain')])
                return ['Internal Server Error']
        elif environ["PATH_INFO"] == '/clients':
            status = ""
            for c in self.ws_clients:
                addr = c.get_peername()
                status += "Websocket %s since %d seconds\n" % (str(addr), c.get_duration())
            start_response('200 OK', [('content-type', 'text/plain')])
            return [status]
        elif environ["PATH_INFO"] == '/status':
            start_response('200 OK', [('content-type', 'text/plain')])
            return ['UP %d' % os.getpid()]
        start_response('404 Not Found', [('content-type', 'text/plain')])
        return ['Not Found']


if __name__ == '__main__':
    log = StdoutLogger()
    fs = FSWebsocketServer('0.0.0.0', 8000, '127.0.0.1', 8021, 'ClueCon', 'ALL', log)
    fs.start()

