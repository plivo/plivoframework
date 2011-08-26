# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import sys


def safe_str(o):
    try:
        return str(o)
    except:
        if isinstance(o, unicode):
            encoding = sys.getdefaultencoding()
            return o.encode(encoding, 'backslashreplace')
        return o
