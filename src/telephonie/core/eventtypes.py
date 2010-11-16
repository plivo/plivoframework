# -*- coding: utf-8 -*-
"""
Event Types classes
"""

from urllib import unquote
from urllib import quote


class Event(object):
    '''Event class'''
    def __init__(self, buffer=""):
        self._headers = {}
        self._body = ''
        if buffer:
            # set event headers from buffer
            for line in buffer.splitlines():
                try:
                    var, val = line.rstrip().split(': ', 1)
                    var = var.strip()
                    val = unquote(val.strip())
                    self.setHeader(var, val)
                except ValueError: 
                    pass

    def __getitem__(self, key):
        return self.getHeader(key)

    def __setitem__(self, key, value):
        self.setHeader(key, value)

    def getContentLength(self):
        '''
        Get Content-Length header as integer.

        If not found return 0 .
        '''
        length = self.getHeader('Content-Length')
        if length:
            try:
                return int(length)
            except:
                return 0
        return 0

    def getReplyText(self):
        '''
        Get Reply-Text header.

        Return string or None if header not found.
        '''
        return self.getHeader('Reply-Text') 

    def isReplyTextSuccess(self):
        '''
        Return True if ReplyText header is beginning with +OK else False.
        '''
        reply = self.getReplyText()
        return reply and reply[:3] == '+OK'

    def getContentType(self):
        '''
        Get Content-Type header.

        Return string or None if header not found.
        '''
        return self.getHeader('Content-Type')

    def getHeaders(self):
        '''
        Get all headers as dict.
        '''
        return self._headers

    def setHeaders(self, headers):
        '''
        Set all headers froms dict.
        '''
        self._headers = headers.copy()

    def getHeader(self, key, defaultvalue=None):
        '''
        Get one header.

        Return string or None if header not found.
        '''
        try:
            return self._headers[key]
        except KeyError:
            return defaultvalue

    def setHeader(self, key, value):
        '''
        Set one header.
        '''
        self._headers[key] = value

    def getBody(self):
        '''
        Get Event body.
        '''
        return self._body

    def setBody(self, data):
        '''
        Set Event body.
        '''
        self._body = data

    def getRawEvent(self):
        raw = ''
        raw += '\n'.join([ '%s: %s' % (k, quote(v)) for k, v in self.getHeaders().iteritems() ])
        raw += '\n'
        if self._body:
            raw += self._body
        return raw

    def __str__(self):
        return '<Event [headers=%s, response=%s]>' \
               % (str(self.getHeaders()), str(self.getBody()))



class ApiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, ev):
        '''
        Make ApiResponse instance from Event instance
        '''
        cls = ApiResponse()
        cls.setHeaders(ev.getHeaders())
        cls.setBody(ev.getBody())
        return cls

    def getResponse(self):
        '''
        Get response for api command.
        '''
        return self.getBody()

    def isSuccess(self):
        '''
        Return True if api command success else False.
        '''
        return self._body and self._body[:3] == '+OK'

    def __str__(self):
        return '<ApiResponse [headers=%s, response=%s]>' \
               % (str(self.getHeaders()), str(self.getResponse()))



class BgapiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)
        self._backgroundJob = None

    @classmethod
    def cast(self, ev):
        '''
        Make BgapiResponse instance from Event instance
        '''
        cls = BgapiResponse()
        cls.setHeaders(ev.getHeaders())
        cls.setBody(ev.getBody())
        return cls

    def getResponse(self):
        '''
        Get response for bgapi command.
        '''
        return self.getReplyText()

    def getJobUUID(self):
        '''
        Get Job-UUID from bgapi command.
        '''
        return self.getHeader('Job-UUID')

    def isSuccess(self):
        '''
        Return True if bgapi command success else False.
        '''
        return self.isReplyTextSuccess()

    def __str__(self):
        return '<BgapiResponse [headers=%s, response=%s, jobuuid=%s]>' \
               % (str(self.getHeaders()), str(self.getResponse()), self.getJobUUID())



class CommandResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, ev):
        '''
        Make CommandResponse instance from Event instance
        '''
        cls = CommandResponse()
        cls.setHeaders(ev.getHeaders())
        cls.setBody(ev.getBody())
        return cls

    def getResponse(self):
        '''
        Get response for command.
        '''
        return self.getReplyText()

    def isSuccess(self):
        '''
        Return True if command success else False.
        '''
        return self.isReplyTextSuccess()

    def __str__(self):
        return '<CommandResponse [headers=%s, response=%s]>' \
               % (str(self.getHeaders()), str(self.getResponse()))


