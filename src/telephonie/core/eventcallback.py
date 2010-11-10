# -*- coding: utf-8 -*-
"""
Event callback base class to handle FreeSWITCH's events .

Please refer to http://wiki.freeswitch.org/wiki/Event_list

To implement Event callback class, inherit from BaseEventCallback and add methods for events.

For example to add method for CHANNEL_HANGUP event, 
create method : onChannelHangup(self, ev)

Special methods :
- onFallback(self, ev) : if an event don't have a callback matching, it will be processed throw this callback .

- onFailure(self, ev) : if callback raise an error, this callback is called. 

If you don't want special methods, don't create them in your class !


"""

import string


class BaseEventCallback(object):
    def __init__(self, ev):
        self._doCall(ev)

    def _doCall(self, ev):
        callback = None
        eventname = ev.getHeader('Event-Name')
        # If 'Event-Name' header is found, try to get callback for this event
        if eventname:
            method = string.capwords(eventname, '_').replace('_', '')
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

        
class PrintEventCallback(BaseEventCallback):
    '''Event callback class example which output is stdout.'''
    def __init__(self, ev):
        import telephonie.utils.logger as logger
        self.__logger = logger.StdoutLogger()
        BaseEventCallback.__init__(self, ev)

    def log_info(self, *args):
        self.__logger.info('PrintEventCallback '+' '.join([ str(arg) for arg in args ]))

    def log_warn(self, *args):
        self.__logger.warn('PrintEventCallback '+' '.join([ str(arg) for arg in args ]))

    def log_error(self, *args):
        self.__logger.error('PrintEventCallback '+' '.join([ str(arg) for arg in args ]))

    def log_debug(self, *args):
        self.__logger.debug('PrintEventCallback '+' '.join([ str(arg) for arg in args ]))

    def onFallback(self, ev):
        '''If no callback found, always print event'''
        self.log_warn(ev)

    def onFailure(self, ev):
        '''If callback raise exception, always print event'''
        self.log_error(ev)

