# -*- coding: utf-8 -*-
"""
Event Socket class
"""

import types
import gevent
import gevent.queue as queue
import gevent.pool
from telephonie.core.commands import Commands
from telephonie.core.eventtypes import Event
from telephonie.core.eventtypes import (CommandResponse, ApiResponse, BgapiResponse)
from telephonie.core.errors import (LimitExceededError, ConnectError)


EOL = "\n"
MAXLINES_PER_EVENT = 2000



class BaseEventSocket(object):
    '''BaseEventSocket class'''
    def __init__(self, poolSize=1000, eventCallback=None):
        # callbacks for response events
        self._responseCallbacks = {'api/response':self._apiResponse,
                                   'command/reply':self._commandReplyResponse,
                                   'text/disconnect-notice':self._disconnectResponse
                                  }
        # queue for response events
        self.queue = queue.Queue()
        # set connected to False
        self.connected = False
        # create pool for spawning
        self.pool = gevent.pool.Pool(poolSize)
        # event callback class
        self._eventCallbackClass = eventCallback
        # current jobs from bgapi command
        self._bgapiJobs = {}
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
            ev = self.getEvent()
            # Dispatch this event
            if ev:
                self.pool.spawn(self.dispatchEvent, ev)
            gevent.sleep(0.005)

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
        _getResponse = self._responseCallbacks.get(ev.getContentType(), self._defaultResponse)
        # If callback response found, start this method to get final event
        if _getResponse:
            ev = _getResponse(ev)
        return ev

    def _catchBgapiJob(self ,ev):
        # FIXME NOT OPTIMIZED, NEED MORE WORK ... wen can probably use gevent.event.AsyncResult :) 
        # If Job-UUID header value present in self._bgapiJobs
        # add this event to bgapi response
        # and remove bgapi response from self._bgapiJobs
        jobuuid = ev.getHeader("Job-UUID")
        eventname = ev.getHeader("Event-Name")
        if jobuuid and (eventname == "BACKGROUND_JOB"):
            bgapiResponse = self._bgapiJobs.get(jobuuid, None)
            if bgapiResponse:
                bgapiResponse.setBackgroundJob(ev)
                del self._bgapiJobs[jobuuid]

    def _commandReplyResponse(self, ev):
        '''
        Callback response for Event type command/reply.
        '''
        # Get raw data for this event
        raw = self.readRaw(ev)
        if raw:
            # If raw was found drop current event 
            # and replace with Event created from raw
            ev = Event(raw)
            # Get raw response from Event Content-Length header 
            # and raw buffer
            rawresponse = self.readRawResponse(ev, raw)
            # If rawresponse was found, this is our Event body
            if rawresponse:
                ev.setBody(rawresponse)
        # Push Event to response events queue and return Event
        self.queue.put(ev)
        return ev

    def _apiResponse(self, ev):
        '''
        Callback response for Event type api/response.
        '''
        # Get raw data for this event
        raw = self.readRaw(ev)
        # If raw was found, this is our Event body
        if raw:
            ev.setBody(raw)
        # Push Event to response events queue and return Event
        self.queue.put(ev)
        return ev

    def _defaultResponse(self, ev):
        '''
        Default callback response for Event.
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

    def _disconnectResponse(self, ev):
        '''
        Callback response for Event type text/disconnect-notice.
        '''
        # Stop all and return Event
        self.stop()
        return ev

    def dispatchEvent(self, ev):
        '''
        Start Event callback for one Event.
        '''
        # try to catch background job from event
        self._catchBgapiJob(ev)
        # now start event callback
        if self._eventCallbackClass:
            self._eventCallbackClass(ev)
        
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
        # cast to appropriate event type
        # for _protocolSend, default is CommandResponse
        # If event is api, cast to ApiResponse
        if command == 'api':
            ev = ApiResponse.cast(ev)
        # If event is bgapi :
        # - cast to BgapiResponse
        # - add response to current jobs in background.
        # When Job-UUID will return from event, response will be updated with this event.
        elif command == "bgapi":
            ev = BgapiResponse.cast(ev)
            jobuuid = ev.getJobUUID()
            if jobuuid:
                self._bgapiJobs[jobuuid] = ev
        else:
            ev = CommandResponse.cast(ev)
        return ev
    
    def _protocolSendmsg(self, name, args=None, uuid="", lock=False):
        self._sendmsg(name, args, uuid, lock)
        ev = self.queue.get()
        return ev

    def disconnect(self):
        '''
        Disconnect from eventsocket and stop handling events.
        '''
        self.bgapiJobs = {}
        self.transport.close()
        self.stopEventHandler()
        self.connected = False

    def connect(self):
        '''
        Connect to eventsocket.

        Must be implemented by subclass.
        '''
        pass



class EventSocket(BaseEventSocket, Commands):
    '''
    EventSocket class
    '''
    def __init__(self, filter="ALL", poolSize=1000, eventCallback=None):
        BaseEventSocket.__init__(self, poolSize, eventCallback)
        self._filter = filter
