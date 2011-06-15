# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Outbound server example in sync mode full .
"""

from plivo.core.freeswitch.outboundsocket import OutboundEventSocket, OutboundServer
from plivo.utils.logger import StdoutLogger
import gevent.queue


class SyncOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, filter=None):
        self.log = log
        self._action_queue = gevent.queue.Queue()
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocol_send(self, command, args=""):
        self.log.info("[%s] args='%s'" % (command, args))
        response = super(SyncOutboundEventSocket, self)._protocol_send(command, args)
        self.log.info(str(response))
        return response

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1):
        self.log.info("[%s] args=%s, uuid='%s', lock=%s, loops=%d" \
                      % (name, str(args), uuid, str(lock), loops))
        response = super(SyncOutboundEventSocket, self)._protocol_sendmsg(name, args, uuid, lock, loops)
        self.log.info(str(response))
        return response

    def on_channel_execute_complete(self, event):
        if event.get_header('Application') == 'playback':
            self.log.info("Playback done (%s)" % str(event.get_header('Application-Response')))

    def on_channel_answer(self, event):
        self._action_queue.put(event)

    def run(self):
        self.connect()
        self.log.info("Channel Unique ID => %s" % self.get_channel_unique_id())
        # only catch events for this channel
        self.myevents()
        # answer channel
        self.answer()
        self.log.info("Wait answer")
        event = self._action_queue.get()
        gevent.sleep(1) # sleep 1 sec: sometimes sound is truncated after answer
        self.log.info("Channel answered")

        # play file
        self.playback("/usr/local/freeswitch/sounds/en/us/callie/ivr/8000/ivr-hello.wav", terminators="*")
        # finally hangup
        self.hangup()


class SyncOutboundServer(OutboundServer):
    def __init__(self, address, handle_class, filter=None):
        self.log = StdoutLogger()
        self.log.info("Start server %s ..." % str(address))
        OutboundServer.__init__(self, address, handle_class, filter)

    def handle_request(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._requestClass(socket, address, self.log, filter=self._filter)
        self.log.info("End request from %s" % str(address))



if __name__ == '__main__':
    outboundserver = SyncOutboundServer(('127.0.0.1', 8084), SyncOutboundEventSocket)
    outboundserver.serve_forever()
