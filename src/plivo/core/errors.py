# -*- coding: utf-8 -*-
"""
Exceptions classes
"""

class LimitExceededError(Exception): 
    '''Exception class when MAXLINES_PER_EVENT is reached'''
    pass


class ConnectError(Exception): 
    '''Exception class for connection'''
    pass

