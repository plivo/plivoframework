# -*- coding: utf-8 -*-
"""
Event Types classes
"""

from urllib import unquote
from urllib import quote
from UserDict import DictMixin


class OrderedDict(dict, DictMixin):
    '''
    ordered dict from http://code.activestate.com/recipes/576693/ (with __repr__ modified).
    '''
    def __init__(self, *args, **kwds):
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        try:
            self.__end
        except AttributeError:
            self.clear()
        self.update(*args, **kwds)

    def clear(self):
        self.__end = end = []
        end += [None, end, end]         # sentinel node for doubly linked list
        self.__map = {}                 # key --> [key, prev, next]
        dict.clear(self)

    def __setitem__(self, key, value):
        if key not in self:
            end = self.__end
            curr = end[1]
            curr[2] = end[1] = self.__map[key] = [key, curr, end]
        dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        key, prev, next = self.__map.pop(key)
        prev[2] = next
        next[1] = prev

    def __iter__(self):
        end = self.__end
        curr = end[2]
        while curr is not end:
            yield curr[0]
            curr = curr[2]

    def __reversed__(self):
        end = self.__end
        curr = end[1]
        while curr is not end:
            yield curr[0]
            curr = curr[1]

    def popitem(self, last=True):
        if not self:
            raise KeyError('dictionary is empty')
        if last:
            key = reversed(self).next()
        else:
            key = iter(self).next()
        value = self.pop(key)
        return key, value

    def __reduce__(self):
        items = [[k, self[k]] for k in self]
        tmp = self.__map, self.__end
        del self.__map, self.__end
        inst_dict = vars(self).copy()
        self.__map, self.__end = tmp
        if inst_dict:
            return (self.__class__, (items,), inst_dict)
        return self.__class__, (items,)

    def keys(self):
        return list(self)

    setdefault = DictMixin.setdefault
    update = DictMixin.update
    pop = DictMixin.pop
    values = DictMixin.values
    items = DictMixin.items
    iterkeys = DictMixin.iterkeys
    itervalues = DictMixin.itervalues
    iteritems = DictMixin.iteritems

    def __repr__(self):
        return '{' + ', '.join([ "%s: %s" % (str(k), str(v)) for k, v in self.items() ]) + '}'

    def copy(self):
        return self.__class__(self)

    @classmethod
    def fromkeys(cls, iterable, value=None):
        d = cls()
        for key in iterable:
            d[key] = value
        return d

    def __eq__(self, other):
        if isinstance(other, OrderedDict):
            return len(self)==len(other) and self.items() == other.items()
        return dict.__eq__(self, other)

    def __ne__(self, other):
        return not self == other


class Event(object):
    '''Event class'''
    def __init__(self, buffer=""):
        self._headers = OrderedDict()
        self._raw_body = ''
        self._raw_headers = ''
        self._u_raw_headers = ''
        if buffer:
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
        key = key.strip()
        value = value.strip()
        u_value = unquote(value)
        self._raw_headers += "%s: %s\n" % (key, value)
        self._u_raw_headers += "%s: %s\n" % (key, u_value)
        self._headers[key] = u_value

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

    def get_raw_headers(self):
        '''
        Gets raw headers (quoted).
        '''
        return self._raw_headers

    def get_unquoted_raw_headers(self):
        '''
        Gets raw headers (unquoted).
        '''
        return self._u_raw_headers

    def get_raw_event(self):
        '''
        Gets raw Event (quoted).
        '''
        return self._raw_headers + self._raw_body + '\n'

    def get_unquoted_raw_event(self):
        '''
        Gets raw Event (unquoted).
        '''
        return self._u_raw_headers + self._raw_body + '\n'

    def __str__(self):
        return '<%s headers=%s, body=%s>' \
               % (self.__class__.__name__, 
                  str(self.get_unquoted_raw_headers().replace('\n', '\\n')), 
                  str(self.get_body()).replace('\n', '\\n'))


class ApiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, event):
        '''
        Makes an ApiResponse instance from Event instance.
        '''
        cls = ApiResponse(event.get_raw_headers())
        cls.set_body(event.get_body())
        return cls

    def get_response(self):
        '''
        Gets response for api command.
        '''
        return self.get_body()

    def is_success(self):
        '''
        Returns True if api command is a success.
        
        Otherwise returns False.
        '''
        return self._raw_body and self._raw_body[:3] == '+OK'


class BgapiResponse(Event):
    def __init__(self, buffer=""):
        Event.__init__(self, buffer)

    @classmethod
    def cast(self, event):
        '''
        Makes a BgapiResponse instance from Event instance.
        '''
        cls = BgapiResponse(event.get_raw_headers())
        cls.set_body(event.get_body())
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
        cls = CommandResponse(event.get_raw_headers())
        cls.set_body(event.get_body())
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



