# Copyright (c) 2011 Plivo Team. See LICENSE for details.

#!/usr/bin/env python
# -*- coding: utf-8 -*-

class RESTFormatException(Exception):
    pass


class RESTSyntaxException(Exception):
    pass


class UnrecognizedVerbException(Exception):
    pass


class RESTAttributeException(Exception):
    pass


class RESTDownloadException(Exception):
    pass
