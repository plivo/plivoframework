# -*- coding: utf-8 -*-
"""
Client class
"""
import datetime
import uuid
import re
import gevent.queue
try: 
    import simplejson as json
except ImportError:
    import json


class Client(object):
    """
    Websocket client.
    """
    def __init__(self, ws, raw_config=''):
        self.started = datetime.datetime.now()
        self.uuid = str(uuid.uuid4())
        self.raw_config = raw_config
        self.config = json.loads(self.raw_config)
        try:
            self.client_filter = ClientFilter(self.config['filter'])
        except KeyError:
            self.client_filter = ClientFilter(None)
        self.ws = ws
        self.queue = gevent.queue.Queue()

    def get_id(self):
        return self.uuid

    def get_config(self):
        return self.config

    def get_client_filter(self):
        return self.client_filter

    def get_peername(self):
        return self.ws.socket.getpeername()

    def get_duration(self):
        return (datetime.datetime.now()-self.started).seconds

    def push_event(self, event):
        self.queue.put(event)

    def consume_event(self):
        event = self.queue.get()
        json_event = json.dumps(event.get_headers())
        if self.client_filter.event_match(event.get_raw_event()):
            self.ws.send(json_event)


class ClientFilter(object):
    """
    Event filter based on regexp for websocket client.
    """
    def __init__(self, reg=None):
        if not reg:
            self.__reg = None
        else:
            try:
                self.__reg = re.compile(reg, re.DOTALL|re.MULTILINE)
            except re.error:
                self.__reg = None

    def __str__(self):
        if not self.__reg:
            return "<ClientFilter no filter>"
        return "<ClientFilter %s>" % str(self.__reg.pattern)

    def get_regexp(self):
        if self.__reg:
            return self.__reg.pattern
        else:
            return None

    def event_match(self, raw_event):
        # if not filter just return True
        if not self.__reg:
            return True
        # try to match from regexp filter
        if self.__reg.search(raw_event):
            return True
        return False

