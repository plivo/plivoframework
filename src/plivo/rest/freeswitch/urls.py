# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from rest_api import PlivoRestApi


URLS = {
        '/': (PlivoRestApi.index, ['GET']),
        '/v0.1/BulkCalls/': (PlivoRestApi.bulk_calls, ['POST']),
        '/v0.1/Calls/': (PlivoRestApi.calls, ['POST']),
        '/TestConfig/': (PlivoRestApi.test_config, ['GET']),
        }
