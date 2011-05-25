# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from plivo.rest.freeswitch.api import PlivoRestApi

"""
We are defining here the different Urls available on our Plivo WSGIServer

Each API refers to a specific version number which needs to be added
before each API method.

For instance /v0.1/Call and /v0.2/Call refer to be different version of the API and
so what provide different options to initiate calls.
Refer to the API documentation in order to see the changes made
"""

PLIVO_VERSION = 'v0.1';

URLS = {
        # API Index
        '/': (PlivoRestApi.index, ['GET']),
        # API to originate several calls simultaneously
        '/' + PLIVO_VERSION + '/BulkCall/': (PlivoRestApi.bulk_call, ['POST']),
        # API to originate a single call
        '/' + PLIVO_VERSION + '/Call/': (PlivoRestApi.call, ['POST']),
        # API to hangup a single call
        '/' + PLIVO_VERSION + '/HangupCall/': (PlivoRestApi.hangup_call, ['POST']),
        # API to transfer a single call
        '/' + PLIVO_VERSION + '/TransferCall/': (PlivoRestApi.transfer_call, ['POST']),
        # API to hangup all calls
        '/' + PLIVO_VERSION + '/HangupAllCalls/': (PlivoRestApi.hangup_all_calls, ['POST']),
        # API to schedule hangup on a single call
        '/' + PLIVO_VERSION + '/ScheduleHangup/': (PlivoRestApi.schedule_hangup, ['POST']),
        # API to cancel a scheduled hangup on a single call
        '/' + PLIVO_VERSION + '/CancelScheduledHangup/': (PlivoRestApi.cancel_scheduled_hangup, ['POST']),
       }
