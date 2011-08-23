# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


class RESTFormatException(Exception):
    pass


class RESTSyntaxException(Exception):
    pass


class RESTAttributeException(Exception):
    pass


class RESTDownloadException(Exception):
    pass


class RESTNoExecuteException(Exception):
    pass


class RESTHangup(Exception):
    pass


class RESTRedirectException(Exception):
    def __init__(self, url=None, params={}, method=None):
        self.url = url
        self.method = method
        self.params = params

    def get_url(self):
        return self.url

    def get_method(self):
        return self.method

    def get_params(self):
        return self.params


class RESTSIPTransferException(Exception):
    def __init__(self, sip_url=None):
        self.sip_url = sip_url

    def get_sip_url(self):
        return self.sip_url


class UnrecognizedElementException(Exception):
    pass


class UnsupportedResourceFormat(Exception):
    pass
