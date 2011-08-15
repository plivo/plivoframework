# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from unittest import TestCase

from plivo.core.freeswitch.eventtypes import Event


class TestEvent(TestCase):
    EVENT_COMMAND_REPLY = "Content-Type: command/reply\nReply-Text: +OK accepted\n\n"
    EVENT_AUTH_REQUEST = "Content-Type: auth/request\n\n"
    EVENT_CONTENT_LENGTH = "Content-Length: 491\nContent-Type: text/event-plain\n\n"
    EVENT_PLAIN = """Event-Name: RE_SCHEDULE
Core-UUID: 12640749-db62-421c-beac-4863eac76510
FreeSWITCH-Hostname: vocaldev
FreeSWITCH-IPv4: 10.0.0.108
FreeSWITCH-IPv6: %3A%3A1
Event-Date-Local: 2011-01-03%2018%3A33%3A56
Event-Date-GMT: Mon,%2003%20Jan%202011%2017%3A33%3A56%20GMT
Event-Date-Timestamp: 1294076036427219
Event-Calling-File: switch_scheduler.c
Event-Calling-Function: switch_scheduler_execute
Event-Calling-Line-Number: 65
Task-ID: 1
Task-Desc: heartbeat
Task-Group: core
Task-Runtime: 1294076056

"""


    def test_command_reply(self):
        ev = Event(self.EVENT_COMMAND_REPLY)
        self.assertEquals(ev.get_content_type(), "command/reply")
        self.assertEquals(ev.get_reply_text(), "+OK accepted")
        self.assertTrue(ev.is_reply_text_success())

    def test_auth_request(self):
        ev = Event(self.EVENT_AUTH_REQUEST)
        self.assertEquals(ev.get_content_type(), "auth/request")

    def test_event_plain(self):
        ev1 = Event(self.EVENT_CONTENT_LENGTH)
        self.assertEquals(ev1.get_content_length(), 491)
        self.assertEquals(ev1.get_content_type(), "text/event-plain")
        ev2 = Event(self.EVENT_PLAIN)
        self.assertEquals(ev2.get_header("Event-Name"), "RE_SCHEDULE")
        self.assertEquals(len(self.EVENT_PLAIN), ev1.get_content_length())
