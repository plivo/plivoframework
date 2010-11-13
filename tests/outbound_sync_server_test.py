# -*- coding: utf-8 -*-
"""
Outbound server example in sync mode full .
"""

from telephonie.core.outboundsocket import (OutboundEventSocket, OutboundServer)
from telephonie.utils.logger import StdoutLogger
import gevent.queue


class SyncOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, filter=None):
        self.log = log
        self._action_queue = gevent.queue.Queue()
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocolSend(self, command, args=""):
        self.log.info("[%s] args='%s'" % (command, args))
        res = super(SyncOutboundEventSocket, self)._protocolSend(command, args)
        self.log.info(str(res))
        return res

    def _protocolSendmsg(self, name, args=None, uuid="", lock=False):
        self.log.info("[%s] args=%s uuid='%s' lock=%s" % (name, str(args), uuid, str(lock)))
        res = super(SyncOutboundEventSocket, self)._protocolSendmsg(name, args, uuid, lock)
        self.log.info(str(res))
        return res

    def onChannelExecuteComplete(self, ev):
        if ev.getHeader('Application') == 'playback':
            self.log.info("Playback done (%s)" % str(ev.getHeader('Application-Response')))

    def onChannelAnswer(self, ev):
        gevent.sleep(1) # sleep 1 sec: sometimes sound is truncated after answer
        self._action_queue.put(ev)

    def run(self):
        self.log.info("Channel Unique ID => %s" % self.getChannelUniqueID())

        # only catch events for this channel
        self.myevents()
        # answer channel
        self.answer()
        self.log.info("Wait answer")
        ev = self._action_queue.get(timeout=20)
        self.log.info("Channel answered")

        # play file
        self.playback("/usr/local/freeswitch/sounds/en/us/callie/ivr/8000/ivr-hello.wav", terminators="*")
        # finally hangup
        self.hangup()


class SyncOutboundServer(OutboundServer):
    def __init__(self, address, handleClass, filter=None):
        self.log = StdoutLogger()
        self.log.info("Start server %s ..." % str(address))
        OutboundServer.__init__(self, address, handleClass, filter)

    def doHandle(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._handleClass(socket, address, self.log, filter=self._filter)
        self.log.info("End request from %s" % str(address))



if __name__ == '__main__':
    outboundserver = SyncOutboundServer(('127.0.0.1', 8084), SyncOutboundEventSocket)
    outboundserver.serve_forever()

