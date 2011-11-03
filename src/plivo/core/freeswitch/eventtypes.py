# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Event Types classes
"""

from urllib import unquote
import ujson as json


class Event(object):
    '''Event class'''
    __slots__ = ('__weakref__',
                 '_headers',
                 '_raw_body',
                )

    def __init__(self, buffer=""):
        self._headers = {}
        self._raw_body = ''
        if buffer:
            buffer = buffer.decode('utf-8', 'ignore')
            buffer = buffer.encode('utf-8')
            # Sets event headers from buffer.
            for line in buffer.splitlines():
                try:
                    var, val = line.rstrip().split(': ', 1)
                    self.set_header(var, val)
                except ValueError:
                    pass

    def __getitem__(self, key):
        return self.get_header(key)

    def __setitem__(self, key, value):
        self.set_header(key, value)

    def get_content_length(self):
        '''
        Gets Content-Length header as integer.

        Returns 0 If length not found.
        '''
        length = self.get_header('Content-Length')
        if length:
            try:
                return int(length)
            except:
                return 0
        return 0

    def get_reply_text(self):
        '''
        Gets Reply-Text header as string.

        Returns None if header not found.
        '''
        return self.get_header('Reply-Text')

    def is_reply_text_success(self):
        '''
        Returns True if ReplyText header begins with +OK.

        Returns False otherwise.
        '''
        reply = self.get_reply_text()
        return reply and reply[:3] == '+OK'

    def get_content_type(self):
        '''
        Gets Content-Type header as string.

        Returns None if header not found.
        '''
        return self.get_header('Content-Type')

    def get_headers(self):
        '''
        Gets all headers as a python dict.
        '''
        return self._headers

    def set_headers(self, headers):
        '''
        Sets all headers from dict.
        '''
        self._headers = headers.copy()

    def get_header(self, key, defaultvalue=None):
        '''
        Gets a specific header as string.

        Returns None if header not found.
        '''
        try:
            return self._headers[key]
        except KeyError:
            return defaultvalue

    def set_header(self, key, value):
        '''
        Sets a specific header.
        '''
        self._headers[key.strip()] = unquote(value.strip())

    def get_body(self):
        '''
        Gets raw Event body.
        '''
        return self._raw_body

    def set_body(self, data):
        '''
        Sets raw Event body.
        '''
        self._raw_body = data

    def is_empty(self):
        '''Return True if no headers and no body.'''
        return not self._raw_body and not self._headers

    def get_response(self):
        '''
        Gets response (body).
        '''
        return self.get_body().strip()

    def is_success(self):
        '''
        Returns True if body begins with +OK.

        Otherwise returns False.
        '''
        return self._raw_body and self._raw_body[:3] == '+OK'

    def __str__(self):
        return '<%s headers=%s, body=%s>' \
               % (self.__class__.__name__,
                  str(self._headers),
                  str(self._raw_body))


class ApiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, event):
        '''
        Makes an ApiResponse instance from Event instance.
        '''
        cls = ApiResponse()
        cls._headers = event._headers
        cls._raw_body = event._raw_body
        return cls


class BgapiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, event):
        '''
        Makes a BgapiResponse instance from Event instance.
        '''
        cls = BgapiResponse()
        cls._headers = event._headers
        cls._raw_body = event._raw_body
        return cls

    def get_response(self):
        '''
        Gets response for bgapi command.
        '''
        return self.get_reply_text()

    def get_job_uuid(self):
        '''
        Gets Job-UUID from bgapi command.
        '''
        return self.get_header('Job-UUID')

    def is_success(self):
        '''
        Returns True if bgapi command is a success.

        Otherwise returns False.
        '''
        return self.is_reply_text_success()


class CommandResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, event):
        '''
        Makes a CommandResponse instance from Event instance.
        '''
        cls = CommandResponse()
        cls._headers = event._headers
        cls._raw_body = event._raw_body
        return cls

    def get_response(self):
        '''
        Gets response for a command.
        '''
        return self.get_reply_text()

    def is_success(self):
        '''
        Returns True if command is a success.

        Otherwise returns False.
        '''
        return self.is_reply_text_success()


class JsonEvent(Event):
    '''Json Event class'''
    def __init__(self, buffer=""):
        self._headers = {}
        self._raw_body = ''
        if buffer:
            buffer = buffer.decode('utf-8', 'ignore')
            buffer = buffer.encode('utf-8')
            self._headers = json.loads(buffer)
            try:
                self._raw_body = self._headers['_body']
            except KeyError:
                pass

