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
        # API to reload Plivo config
        '/' + PLIVO_VERSION + '/ReloadConfig/': (PlivoRestApi.reload_config, ['POST', 'GET']),
        # API to reload Plivo Cache config
        '/' + PLIVO_VERSION + '/ReloadCacheConfig/': (PlivoRestApi.reload_cache_config, ['POST', 'GET']),
        # API to originate several calls simultaneously
        '/' + PLIVO_VERSION + '/BulkCall/': (PlivoRestApi.bulk_call, ['POST']),
        # API to originate a single call
        '/' + PLIVO_VERSION + '/Call/': (PlivoRestApi.call, ['POST']),
        # API to originate a call group simultaneously
        '/' + PLIVO_VERSION + '/GroupCall/': (PlivoRestApi.group_call, ['POST']),
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
        # API to start recording a call
        '/' + PLIVO_VERSION + '/RecordStart/': (PlivoRestApi.record_start, ['POST']),
        # API to stop recording a call
        '/' + PLIVO_VERSION + '/RecordStop/': (PlivoRestApi.record_stop, ['POST']),
        # API to play something on a single call
        '/' + PLIVO_VERSION + '/Play/': (PlivoRestApi.play, ['POST']),
        # API to stop play something on a single call
        '/' + PLIVO_VERSION + '/PlayStop/': (PlivoRestApi.play_stop, ['POST']),
        # API to schedule playing something  on a single call
        '/' + PLIVO_VERSION + '/SchedulePlay/': (PlivoRestApi.schedule_play, ['POST']),
        # API to cancel a scheduled play on a single call
        '/' + PLIVO_VERSION + '/CancelScheduledPlay/': (PlivoRestApi.cancel_scheduled_play, ['POST']),
        # API to add soundtouch audio effects to a call
        '/' + PLIVO_VERSION + '/SoundTouch/': (PlivoRestApi.sound_touch, ['POST']),
        # API to remove soundtouch audio effects on a call
        '/' + PLIVO_VERSION + '/SoundTouchStop/': (PlivoRestApi.sound_touch_stop, ['POST']),
        # API to send digits to a call
        '/' + PLIVO_VERSION + '/SendDigits/': (PlivoRestApi.send_digits, ['POST']),
        # API to mute a member in a conference
        '/' + PLIVO_VERSION + '/ConferenceMute/': (PlivoRestApi.conference_mute, ['POST']),
        # API to unmute a member in a conference
        '/' + PLIVO_VERSION + '/ConferenceUnmute/': (PlivoRestApi.conference_unmute, ['POST']),
        # API to kick a member from a conference
        '/' + PLIVO_VERSION + '/ConferenceKick/': (PlivoRestApi.conference_kick, ['POST']),
        # API to hangup a conference member
        '/' + PLIVO_VERSION + '/ConferenceHangup/': (PlivoRestApi.conference_hangup, ['POST']),
        # API to deaf a member in a conference
        '/' + PLIVO_VERSION + '/ConferenceDeaf/': (PlivoRestApi.conference_deaf, ['POST']),
        # API to undeaf a member in a conference
        '/' + PLIVO_VERSION + '/ConferenceUndeaf/': (PlivoRestApi.conference_undeaf, ['POST']),
        # API to start recording a conference
        '/' + PLIVO_VERSION + '/ConferenceRecordStart/': (PlivoRestApi.conference_record_start, ['POST']),
        # API to stop recording a conference
        '/' + PLIVO_VERSION + '/ConferenceRecordStop/': (PlivoRestApi.conference_record_stop, ['POST']),
        # API to play a sound file into a conference
        '/' + PLIVO_VERSION + '/ConferencePlay/': (PlivoRestApi.conference_play, ['POST']),
        # API to say something into a conference
        '/' + PLIVO_VERSION + '/ConferenceSpeak/': (PlivoRestApi.conference_speak, ['POST']),
        # API to list a conference with members
        '/' + PLIVO_VERSION + '/ConferenceListMembers/': (PlivoRestApi.conference_list_members, ['POST']),
        # API to list all conferences with members
        '/' + PLIVO_VERSION + '/ConferenceList/': (PlivoRestApi.conference_list, ['POST']),
       }
