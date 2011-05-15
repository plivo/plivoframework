# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from rest_api import PlivoRestApi

"""
We defined here the different Urls available by the Plivo WSGIServer

Each API needs to refer to a specific version number in order to provide
a versionning on each API method.

For instance /v0.1/Calls and /v0.2/Calls might not offer the same parameters
to initiate calls
"""

PLIVO_VERSION = 'v0.1';

URLS = {
        # API Index
        '/': (PlivoRestApi.index, ['GET']),
        # API to originate several calls simultaneously
        '/' + PLIVO_VERSION + '/BulkCalls/': (PlivoRestApi.bulk_calls, ['POST']),
        # API to originate a single call
        '/' + PLIVO_VERSION + '/Calls/': (PlivoRestApi.calls, ['POST']),
        # API to hangup a single call
        '/' + PLIVO_VERSION + '/HangupCall/': (PlivoRestApi.hangup_call, ['POST']),
        # API to transfer a single call
        '/' + PLIVO_VERSION + '/TransferCall/': (PlivoRestApi.hangup_call, ['POST']),
        # API to hangup all calls
        '/' + PLIVO_VERSION + '/HangupAll/': (PlivoRestApi.hangup_all_calls, ['POST']),
        # API to schedule hangup on a single call
        '/' + PLIVO_VERSION + '/SchedHangup/': (PlivoRestApi.sched_hangup, ['POST']),
        # API to cancel a scheduled hangup on a single call
        '/' + PLIVO_VERSION + '/SchedCancelHangup/': (PlivoRestApi.sched_cancel_hangup, ['POST']),
        # API to test the config
        '/TestConfig/': (PlivoRestApi.test_config, ['GET']),
        }
