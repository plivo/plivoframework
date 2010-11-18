# -*- coding: utf-8 -*-
"""
Core for Telephonie Application Framework
"""

import gevent.monkey
gevent.monkey.patch_all()


__all__ = ['transport', 
           'eventsocket', 
           'commands', 
           'eventtypes', 
           'errors', 
           'inboundsocket',
           'outboundsocket']
