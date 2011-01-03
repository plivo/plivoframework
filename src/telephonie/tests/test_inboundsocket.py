# -*- coding: utf-8 -*-
from unittest import TestCase

from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.eventtypes import Event
from telephonie.core.errors import ConnectError
import gevent
from gevent import socket
from gevent.server import StreamServer


class TestClient(object):
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
    def __init__(self):
        self.server = StreamServer(('127.0.0.1', 18021), self.emulator)

    def start(self):
        self.server.serve_forever()

    def emulator(self, sock, address):
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
            if client.auth is False:
                break
        if client.auth is False:
            self.disconnect(client)
            raise ConnectError("auth failure")

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
            if client.event_plain is False:
                break
        if client.event_plain is False:
            self.disconnect(client)
            raise ConnectError("event plain failure")

        # send fake heartbeat and re_schedule events to client 10 times
        for i in range(10):
            self.send_heartbeat(client)
            self.send_re_schedule(client)
            gevent.sleep(1.0)

        self.disconnect(client)
        return

    def disconnect(self, client):
        client.send("Content-Type: text/disconnect-notice\nContent-Length: 67\n\nDisconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n\n")
        client.close()

    def send_heartbeat(self, client):
        msg = \
"""Content-Length: 628
Content-Type: text/event-plain

Event-Name: HEARTBEAT
Core-UUID: 12640749-db62-421c-beac-4863eac76510
FreeSWITCH-Hostname: vocaldev
FreeSWITCH-IPv4: 10.0.0.108
FreeSWITCH-IPv6: ::1
Event-Date-Local: 2011-01-03 17:55:36
Event-Date-GMT: Mon,03 Jan 2011 16:55:36 GMT
Event-Date-Timestamp: 1294073736359087
Event-Calling-File: switch_core.c
Event-Calling-Function: send_heartbeat
Event-Calling-Line-Number: 65
Event-Info: System Ready
Up-Time: 0 years, 3 days, 1 hour, 19 minutes, 19 seconds, 835 milliseconds, 430 microseconds
Session-Count: 0
Session-Per-Sec: 30
Session-Since-Startup: 0
Idle-CPU: 99.000000

"""
        client.send(msg)

    def send_re_schedule(self, client):
        msg = \
"""Event-Name: RE_SCHEDULE
Core-UUID: 12640749-db62-421c-beac-4863eac76510
FreeSWITCH-Hostname: vocaldev
FreeSWITCH-IPv4: 10.0.0.108
FreeSWITCH-IPv6: ::1
Event-Date-Local: 2011-01-03 17;58:16
Event-Date-GMT: Mon, 03 Jan 2011 16:58:16 GMT
Event-Date-Timestamp: 1294073896363806
Event-Calling-File: switch_scheduler.c
Event-Calling-Function: switch_scheduler_execute
Event-Calling-Line-Number: 65
Task-ID: 1
Task-Desc: heartbeat
Task-Group: core
Task-Runtime: 1294073916

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
        return False

    def event_plain(self, client, buff):
        if buff.startswith("event plain"):
            client.event_plain = True
            client.send("Content-Type: command/reply\nReply-Text: +OK event listener enabled plain\n\n")
            return True
        return False



class TestInboundEventSocket(InboundEventSocket):
    def __init__(self, host, port, password, filter='ALL', pool_size=500, connect_timeout=5):
        InboundEventSocket.__init__(self, host, port, password, filter, pool_size, connect_timeout)
        self.heartbeat_event_count = 0
        self.re_schedule_event_count = 0

    def unbound_event(self, ev):
        print str(ev)

    def on_re_schedule(self, ev):
        self.heartbeat_event_count += 1

    def on_heartbeat(self, ev):
        self.re_schedule_event_count += 1
        


class TestInboundCase(TestCase):
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
        isock = InboundEventSocket('127.0.0.1', 18021, 'ClueCon')
        try:
            self.assertTrue(isock.connect())
        except ConnectError, e:
            self.fail("connect error: %s" % str(e))
        except socket.error, se:
            self.fail("socket error: %s" % str(se))
        #self.assertTrue(isock.connect)
"""
    def test_event_plain(self):
        isock = TestInboundEventSocket('127.0.0.1', 18021, 'ClueCon')
        try:
            self.assertTrue(isock.connect)
        except socket.error, se:
            self.fail("socket error: %s" % str(se))
        except ConnectError, e:
            self.fail("connect error: %s" % str(e))
        self.assertEquals(isock.heartbeat_event_count, 10)
        self.assertEquals(isock.re_schedule_event_count, 10)
"""



