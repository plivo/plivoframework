# -*- coding: utf-8 -*-
"""
Telephonie  - Application Framework for the FreeSWITCH's Event Socket 

Primary Authors - Michael Ricordeau (tamiel) and Venky (bevenky)

Telephonie is inspired by and uses code from - https://github.com/fiorix/eventsocket
"""

__version__ = "0.0.1"

__name__ = "telephonie"

__author__ = "Telephonie Team"

__author_email__ = "telephonie@miglu.com"

__maintainer__ = "Telephonie Team"

__maintainer_email__ = "telephonie@miglu.com"

__licence__ = "unknown"

__all__ = ['core', 'utils']

import gevent.monkey
gevent.monkey.patch_all()


