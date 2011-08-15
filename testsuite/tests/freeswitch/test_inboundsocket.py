# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from unittest import TestCase

import gevent
from gevent import socket
from gevent import Timeout
from gevent.server import StreamServer

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.freeswitch.eventtypes import Event
from plivo.core.errors import ConnectError


class TestClient(object):
    '''
    Client class on test inbound server side.
    '''
    def __init__(self, sock):
        self.socket = sock
        self.fd = self.socket.makefile()
        self.auth = False
        self.event_plain = False

    def send(self, msg):
        self.fd.write(msg)
        self.fd.flush()

    def recv(self):
        return self.fd.readline()

    def close(self):
        try:
            self.socket.close()
        except:
            pass


class TestEventSocketServer(object):
    '''
    Test inbound socket server.
    '''
    def __init__(self):
        self.server = StreamServer(('127.0.0.1', 18021), self.emulate)

    def start(self):
        self.server.serve_forever()

    def emulate(self, sock, address):
        client = TestClient(sock)
        client.send("Content-Type: auth/request\n\n")
        buff = ""
        # do auth (3 tries)
        for i in range(3):
            while True:
                line = client.recv()
                if not line:
                    break
                elif line == '\r\n' or line == '\n':
                    self.check_auth(client, buff)
                    buff = ""
                    break
                else:
                    buff += line
                    if buff.startswith('exit'):
                        self.disconnect(client)
                        return
            if client.auth is True:
                break
        if client.auth is False:
            self.disconnect(client)
            return

        # wait event plain ALL (3 tries)
        buff = ""
        for i in range(3):
            while True:
                line = client.recv()
                if not line:
                    break
                elif line == '\r\n' or line == '\n':
                    self.event_plain(client, buff)
                    buff = ""
                    break
                else:
                    buff += line
                    if buff.startswith('exit'):
                        self.disconnect(client)
                        return
            if client.event_plain is True:
                break
        if client.event_plain is False:
            self.disconnect(client)
            return

        # send fake heartbeat and re_schedule events to client 10 times
        for i in range(10):
            self.send_heartbeat(client)
            gevent.sleep(0.01)
            self.send_re_schedule(client)
            gevent.sleep(0.01)

        self.disconnect(client)
        return

    def disconnect(self, client):
        client.send("Content-Type: text/disconnect-notice\nContent-Length: 67\n\nDisconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n\n")
        client.close()

    def send_heartbeat(self, client):
        msg = \
"""Content-Length: 630
Content-Type: text/event-plain

Event-Name: HEARTBEAT
Core-UUID: 12640749-db62-421c-beac-4863eac76510
FreeSWITCH-Hostname: vocaldev
FreeSWITCH-IPv4: 10.0.0.108
FreeSWITCH-IPv6: %3A%3A1
Event-Date-Local: 2011-01-04%2010%3A19%3A56
Event-Date-GMT: Tue,%2004%20Jan%202011%2009%3A19%3A56%20GMT
Event-Date-Timestamp: 1294132796167745
Event-Calling-File: switch_core.c
Event-Calling-Function: send_heartbeat
Event-Calling-Line-Number: 65
Event-Info: System%20Ready
Up-Time: 0%20years,%203%20days,%2017%20hours,%2043%20minutes,%2039%20seconds,%20644%20milliseconds,%2091%20microseconds
Session-Count: 0
Session-Per-Sec: 30
Session-Since-Startup: 0
Idle-CPU: 100.000000

"""
        client.send(msg)

    def send_re_schedule(self, client):
        msg = \
"""Content-Length: 491
Content-Type: text/event-plain

Event-Name: RE_SCHEDULE
Core-UUID: 12640749-db62-421c-beac-4863eac76510
FreeSWITCH-Hostname: vocaldev
FreeSWITCH-IPv4: 10.0.0.108
FreeSWITCH-IPv6: %3A%3A1
Event-Date-Local: 2011-01-04%2010%3A19%3A56
Event-Date-GMT: Tue,%2004%20Jan%202011%2009%3A19%3A56%20GMT
Event-Date-Timestamp: 1294132796167745
Event-Calling-File: switch_scheduler.c
Event-Calling-Function: switch_scheduler_execute
Event-Calling-Line-Number: 65
Task-ID: 1
Task-Desc: heartbeat
Task-Group: core
Task-Runtime: 1294132816

"""
        client.send(msg)

    def check_auth(self, client, buff):
        # auth request
        if buff.startswith('auth '):
            try:
                password = buff.split(' ')[1].strip()
                if password == 'ClueCon':
                    client.auth = True
                    client.send("Content-Type: command/reply\nReply-Text: +OK accepted\n\n")
                    return True
                raise Exception("Invalid auth password")
            except:
                client.send("Content-Type: command/reply\nReply-Text: -ERR invalid\n\n")
                return False
        client.send("Content-Type: command/reply\nReply-Text: -ERR invalid\n\n")
        return False

    def event_plain(self, client, buff):
        if buff.startswith('event plain'):
            client.event_plain = True
            client.send("Content-Type: command/reply\nReply-Text: +OK event listener enabled plain\n\n")
            return True
        return False


class TestInboundEventSocket(InboundEventSocket):
    def __init__(self, host, port, password, filter='ALL', pool_size=500, connect_timeout=5):
        InboundEventSocket.__init__(self, host, port, password, filter, pool_size=pool_size,
                                        connect_timeout=connect_timeout, eventjson=False)
        self.heartbeat_events = []
        self.re_schedule_events = []

    def on_re_schedule(self, ev):
        self.re_schedule_events.append(ev)

    def on_heartbeat(self, ev):
        self.heartbeat_events.append(ev)

    def serve_for_test(self):
        timeout = Timeout(10)
        timeout.start()
        try:
            while self.is_connected():
                if len(self.re_schedule_events) == 10 and len(self.heartbeat_events) == 10:
                    break
                gevent.sleep(0.01)
        finally:
            timeout.cancel()


class TestInboundCase(TestCase):
    '''
    Test case for Inbound Event Socket.
    '''
    def setUp(self):
        s = TestEventSocketServer()
        self.server_proc = gevent.spawn(s.start)
        gevent.sleep(0.2)

    def tearDown(self):
        try:
            self.server_proc.kill()
        except:
            pass

    def test_login_failure(self):
        isock = InboundEventSocket('127.0.0.1', 23333, 'ClueCon')
        self.assertRaises(ConnectError, isock.connect)

    def test_login_success(self):
        isock = InboundEventSocket('127.0.0.1', 18021, 'ClueCon', eventjson=False)
        try:
            isock.connect()
        except socket.error, se:
            self.fail("socket error: %s" % str(se))
        except ConnectError, e:
            self.fail("connect error: %s" % str(e))

    def test_events(self):
        isock = TestInboundEventSocket('127.0.0.1', 18021, 'ClueCon')
        try:
            isock.connect()
        except socket.error, se:
            self.fail("socket error: %s" % str(se))
        except ConnectError, e:
            self.fail("connect error: %s" % str(e))
        try:
            isock.serve_for_test()
        except Timeout, t:
            self.fail("timeout error: cannot get all events")
        self.assertEquals(len(isock.heartbeat_events), 10)
        self.assertEquals(len(isock.re_schedule_events), 10)
        for ev in isock.heartbeat_events:
            self.assertEquals(ev.get_header('Event-Name'), 'HEARTBEAT')
        for ev in isock.re_schedule_events:
            self.assertEquals(ev.get_header('Event-Name'), 'RE_SCHEDULE')
