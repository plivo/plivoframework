# -*- coding: utf-8 -*-
"""
Event Socket class
"""

import types
import string
import gevent
import gevent.socket as socket
import gevent.queue as queue
import gevent.pool
from telephonie.core.commands import Commands
from telephonie.core.eventtypes import Event
from telephonie.core.eventtypes import (CommandResponse, ApiResponse, BgapiResponse)
from telephonie.core.errors import (LimitExceededError, ConnectError)


EOL = "\n"
MAXLINES_PER_EVENT = 2000



class EventSocket(Commands):
    '''EventSocket class'''
    def __init__(self, filter="ALL", poolSize=1000):
        # callbacks for reading events and sending response
        self._responseCallbacks = {'api/response':self._apiResponse,
                                   'command/reply':self._commandReply,
                                   'text/event-plain':self._eventPlain,
                                   'auth/request':self._authRequest,
                                   'text/disconnect-notice':self._disconnectNotice
                                  }
        # default event filter
        self._filter = filter
        # queue for response events
        self.queue = queue.Queue()
        # set connected to False
        self.connected = False
        # create pool for spawning
        self.pool = gevent.pool.Pool(poolSize)
        # handler thread
        self._handlerThread = None

    def isConnected(self):
        '''
        Check if connected and authenticated to eventsocket.

        Return True or False
        '''
        return self.connected

    def startEventHandler(self):
        '''
        Start Event handler in background.
        '''
        self._handlerThread = gevent.spawn(self.handleEvents)

    def stopEventHandler(self):
        '''
        Stop Event handler.
        '''
        if self._handlerThread:
            self._handlerThread.kill()
        
    def handleEvents(self):
        '''
        Endless loop getting and dispatching event.
        '''
        while True:
            try:
                # get event and dispatch to handler
                ev = self.getEvent()
                if ev:
                    self.pool.spawn(self.dispatchEvent, ev)
                    gevent.sleep(0.005)
            except (LimitExceededError, socket.error):
                self.connected = False
                raise

    def readEvent(self):
        '''
        Read one Event from socket until EOL.

        Return Event instance.

        Note: raise LimitExceededError if MAXLINES_PER_EVENT is reached.
        '''
        buff = ''
        for x in range(MAXLINES_PER_EVENT):
            line = self.transport.readline()
            if line == EOL:
                # When match EOL, create Event and return it
                return Event(buff)
            else:
                # Else append line to current buffer
                buff += line
        raise LimitExceededError("MAXLINES_PER_EVENT (%d) reached" % MAXLINES_PER_EVENT)

    def readRaw(self, ev):
        '''
        Read raw data based on Event Content-Length.

        Return raw string or None if not found.
        '''
        length = ev.getContentLength()
        # Read length bytes if length > 0
        if length:
            return self.transport.read(int(length))
        return None

    def readRawResponse(self, ev, raw):
        '''
        Extract raw response from raw buffer and length based on Event Content-Length.

        Return raw string or None if not found.
        '''
        length = ev.getContentLength()
        if length:
            return raw[-length:]
        return None

    def getEvent(self):
        '''
        Get complete Event, and process response callback.
        '''
        ev = self.readEvent()
        # Get callback response for this event (default is self._defaultResponse)
        _getResponse = self._responseCallbacks.get(ev.getContentType(), self._unknownEvent)
        # If callback response found, start this method to get final event
        if _getResponse:
            ev = _getResponse(ev)
        return ev

    def _authRequest(self, ev):
        '''
        Callback for reading auth/request and sending response.
        '''
        # Just push Event to response events queue and return Event
        self.queue.put(ev)
        return ev

    def _apiResponse(self, ev):
        '''
        Callback for reading api/response and sending response.
        '''
        # Get raw data for this event
        raw = self.readRaw(ev)
        # If raw was found, this is our Event body
        if raw:
            ev.setBody(raw)
        # Push Event to response events queue and return Event
        self.queue.put(ev)
        return ev

    def _commandReply(self, ev):
        '''
        Callback for reading command/reply and sending response.
        '''
        # Just push Event to response events queue and return Event
        self.queue.put(ev)
        return ev

    def _eventPlain(self, ev):
        '''
        Callback for reading text/event-plain.
        '''
        # Get raw data for this event
        raw = self.readRaw(ev)
        # If raw was found drop current event 
        # and replace with Event created from raw
        if raw:
            ev = Event(raw)
            # Get raw response from Event Content-Length header 
            # and raw buffer
            rawresponse = self.readRawResponse(ev, raw)
            # If rawresponse was found, this is our Event body
            if rawresponse:
                ev.setBody(rawresponse)
        # Just return Event
        return ev

    def _disconnectNotice(self, ev):
        '''
        Callback for reading text/disconnect-notice.
        '''
        # Stop all and return Event
        self.stop()

    def _unknownEvent(self, ev):
        '''
        Callback for reading unknown event type.

        Can be implemented in subclass to process unknown event types.
        '''
        pass

    def dispatchEvent(self, ev):
        '''
        Dispatch one event with callback.
        '''
        callback = None
        eventname = ev.getHeader('Event-Name')
        # If 'Event-Name' header is found, try to get callback for this event
        if eventname:
            method = 'on' + string.capwords(eventname, '_').replace('_', '')
            callback = getattr(self, method, None)
        # If no callback found, if onFallback method exists, call it
        # else return
        if not callback:
            if hasattr(self, 'onFallback'):
                callback = self.onFallback
            else:
                return
        # Call callback.
        # On exception if onFailure method exists, call it 
        # else raise current exception
        try: 
            callback(ev)
        except: 
            if hasattr(self, 'onFailure'):
                self.onFailure(ev)
            else:
                raise

    def disconnect(self):
        '''
        Disconnect from eventsocket and stop handling events.
        '''
        self.transport.close()
        self.stopEventHandler()
        self.connected = False

    def connect(self):
        '''
        Connect to eventsocket.

        Must be implemented by subclass.
        '''
        pass

    def _send(self, cmd):
        if isinstance(cmd, types.UnicodeType):
            cmd = cmd.encode("utf-8")
        self.transport.write(cmd + EOL*2)
        
    def _sendmsg(self, name, arg=None, uuid="", lock=False):
        if isinstance(name, types.UnicodeType):
            name = name.encode("utf-8")
        if isinstance(arg, types.UnicodeType):
            arg = arg.encode("utf-8")
        self.transport.write("sendmsg %s\ncall-command: execute\n" % uuid)
        self.transport.write("execute-app-name: %s\n" % name)
        if arg:
            self.transport.write("execute-app-arg: %s\n" % arg)
        if lock is True:
            self.transport.write("event-lock: true\n")
        self.transport.write(EOL)
        
    def _protocolSend(self, command, args=""):
        if args:
            self._send("%s %s" % (command, args))
        else:
            self._send("%s" % command)
        ev = self.queue.get()
        # Cast Event to appropriate event type :
        # If event is api, cast to ApiResponse
        if command == 'api':
            ev = ApiResponse.cast(ev)
        # If event is bgapi, cast to BgapiResponse
        elif command == "bgapi":
            ev = BgapiResponse.cast(ev)
        # Default is cast to CommandResponse
        else:
            ev = CommandResponse.cast(ev)
        return ev
    
    def _protocolSendmsg(self, name, args=None, uuid="", lock=False):
        self._sendmsg(name, args, uuid, lock)
        ev = self.queue.get()
        # Always cast Event to appropriate CommandResponse
        return CommandResponse.cast(ev)

