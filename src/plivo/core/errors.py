# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Exceptions classes
"""

class LimitExceededError(Exception):
    '''Exception class when MAXLINES_PER_EVENT is reached'''
    pass


class ConnectError(Exception):
    '''Exception class for connection'''
    pass
