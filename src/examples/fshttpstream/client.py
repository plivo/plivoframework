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


PING_EVENT = '{"Ping": null}'

END_FILTERS = 'EOF'

MAX_FILTERS = 100


class Client(object):
    """
    Websocket client.
    """
    def __init__(self, ws, inactivity_timeout=20):
        self.started = datetime.datetime.now()
        self.uuid = str(uuid.uuid4())
        self.inactivity_timeout = inactivity_timeout
        self.client_filters = set()
        self.ws = ws
        self.queue = gevent.queue.Queue()
        self.last_event = datetime.datetime.now()
        for x in range(MAX_FILTERS):
            f = ws.wait()
            if f == END_FILTERS:
                break
            self.add_filter(f)

    def add_filter(self, refilter):
        if not refilter:
            return
        f = ClientFilter(refilter)
        if not f.get_regexp() is None:
            self.client_filters.add(f)

    def get_id(self):
        return self.uuid

    def get_config(self):
        return self.config

    def get_filters(self):
        return self.client_filters

    def list_filters(self):
        return [ str(f) for f in self.client_filters ]

    def get_peername(self):
        return self.ws.socket.getpeername()

    def get_duration(self):
        return (datetime.datetime.now()-self.started).seconds

    def push_event(self, event):
        self.queue.put(event)

    def ping(self):
        now = datetime.datetime.now()
        if (now - self.last_event).seconds >= self.inactivity_timeout:
            self.ws.send(PING_EVENT)
            self.last_event = now
            gevent.sleep(0.02)
            return True
        return False

    def consume_event(self):
        try:
            event = self.queue.get(timeout=1)
            json_event = json.dumps(event.get_headers())
            if not self.client_filters:
                self.ws.send(json_event)
                self.last_event = datetime.datetime.now()
                return
            for f in self.client_filters:
                if f.event_match(event.get_unquoted_raw_event()):
                    self.ws.send(json_event)
                    self.last_event = datetime.datetime.now()
                    return
            return 
        except gevent.queue.Empty:
            gevent.sleep(0.02)
            return


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

