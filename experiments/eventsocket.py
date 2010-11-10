# -*- coding: utf-8 -*-

"""
FreeSWITCH Event Socket Class
"""

import types
import string
import re, urllib
from cStringIO import StringIO
import gevent
import gevent.queue as queue
import gevent.pool
from telephonie.core.commands import Commands


FSEOL = "\n\n"
EOL = "\n"


class EventError(Exception):
    pass


class AuthError(Exception):
    pass


class _O(dict):
    """Translates dictionary keys to instance attributes"""
    def __setattr__(self, k, v):
        dict.__setitem__(self, k, v)

    def __delattr__(self, k):
        dict.__delitem__(self, k)

    def __getattribute__(self, k):
        try:
            return dict.__getitem__(self, k)
        except KeyError:
            return dict.__getattribute__(self, k)


class EventSocket(object):
    def __init__(self, poolSize=10000):
        self.pool = gevent.pool.Pool(poolSize)
        
        self.__ctx = None
        self.__rawlen = None
        self.__io = StringIO()
        self.__crlf = re.compile(r"[\r\n]+")
        self.__rawresponse = [
            "api/response",
            "text/disconnect-notice",
        ]

    def processLine(self, ev, line):
        try:
            k, v = self.__crlf.sub("", line).split(":", 1)
            k = k.replace("-", "_").strip()
            v = urllib.unquote(v.strip())
            ev[k] = v
        except:
            pass

    def parseEvent(self, isctx=False):
        ev = _O()
        self.__io.reset()

        for line in self.__io:
            if line == "\n":
                break
            self.processLine(ev, line)

        if not isctx:
            rawlength = ev.get("Content_Length")
            if rawlength:
                ev.rawresponse = self.__io.read(int(rawlength))

        self.__io.reset()
        self.__io.truncate()
        return ev
    
    def readRawResponse(self):
        self.__io.reset()
        chunk = self.__io.read(int(self.__ctx.Content_Length))
        self.__io.reset()
        self.__io.truncate()
        return _O(rawresponse=chunk)

    def handleEvents(self):
        while True:
            self.receiveEvent()

    def receiveEvent(self):
        rawlength = None
        while True:
            line = self.transport.readline()
            # Create an event once we fully receive the current buffer
            if line == EOL:
                self.__io.write(EOL)
                ctx = self.parseEvent(True)
                rawlength = ctx.get("Content_Length")
                break
            else:
                self.__io.write(line + EOL)
        if rawlength:
            self.__ctx = ctx
            self.__rawlen = int(rawlength)
            receiveRawDataEvent(self)
        else:
            self.dispatchEvent(ctx, _O())
                
    def receiveRawDataEvent(self):
        data = self.transport.read(self.__rawlen)
        self.__rawlen -= len(data)
        self.__io.write(data)
        if self.__rawlen == 0:
            if self.__ctx.get("Content_Type") in self.__rawresponse:
                self.dispatchEvent(self.__ctx, self.readRawResponse())
            else:
                self.dispatchEvent(self.__ctx, self.parseEvent())

    def dispatchEvent(self, ctx, event):
        ctx.data = _O(event.copy())
        self.pool.spawn(self.eventReceived, _O(ctx.copy()))
        self.__ctx = self.__rawlen = None
    
    def eventReceived(self, ctx):
        pass
        
    def _send(self, cmd):
        if isinstance(cmd, types.UnicodeType):
            cmd = cmd.encode("utf-8")
        self.transport.write(cmd + FSEOL)
        
    def sendmsg(self, name, arg=None, uuid="", lock=False):
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

        self.transport.write(FSEOL)


class EventProtocol(EventSocket, Commands):
    def __init__(self, password, filter="ALL", poolSize=10000):
        EventSocket.__init__(self, poolSize)
        self.password = password
        self.filter = filter
        
        # our internal event queue
        self.__EventQueue = queue.Queue()
        
        # callbacks by event's content-type
        self.__EventCallbacks = {
            "auth/request": self.authRequest,
            "api/response": self._apiResponse,
            "command/reply": self._commandReply,
            "text/event-plain": self._plainEvent,
            "text/disconnect-notice": self.onDisconnect,
        }

    def isConnected(self):
        return self.connected

    def connect(self):
        self.eventThread = gevent.spawn(self.handleEvents)
        self.connected = True
        self.auth(self.password)
        self.eventplain(self.filter)
        
    def _protocolSend(self, name, args=""):
        self._send("%s %s" % (name, args))
        ev = self.__EventQueue.get()
        return ev
    
    def _protocolSendmsg(self, name, args=None, uuid="", lock=False):
        self._sendmsg(name, args, uuid, lock)
        ev = self.__EventQueue.get()
        return ev
    
    def eventReceived(self, ctx):
        #log.msg("GOT EVENT: %s\n" % repr(ctx), logLevel=logging.DEBUG)
        content_type = ctx.get("Content_Type", None)
        if content_type:
            method = self.__EventCallbacks.get(content_type, None)
            if callable(method):
                return method(ctx)
            else:
                return self.unknownContentType(content_type, ctx)
    
    def authRequest(self, ctx):
        pass

    def onDisconnect(self, ctx):
        pass

    def _apiResponse(self, ctx):
        self.__EventQueue.put(ctx)
        
    def _commandReply(self, ctx):
        if ctx.Reply_Text.startswith("+OK"):
            self.__EventQueue.put(ctx)
        else:
            self.__EventQueue.put(EventError(ctx))

    def _plainEvent(self, ctx):
        name = ctx.data.get("Event_Name")
        if name:
            evname = "on" + string.capwords(name, "_").replace("_", "")

        method = getattr(self, evname, None)
        if callable(method):
            return method(ctx.data)
        else:
            return self.unboundEvent(ctx.data, evname)

    def unknownContentType(self, content_type, ctx):
        #log.err("[eventsocket] unknown Content-Type: %s" % content_type, logLevel=log.logging.DEBUG)
        pass

    def unboundEvent(self, ctx, evname):
        #log.err("[eventsocket] unbound Event: %s" % evname, logLevel=log.logging.DEBUG)
        pass