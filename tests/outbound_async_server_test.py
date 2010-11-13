# -*- coding: utf-8 -*-
"""
Outbound server example in async mode full .
"""

from telephonie.core.outboundsocket import (OutboundEventSocket, OutboundServer)
from telephonie.utils.logger import StdoutLogger
import gevent.queue
import gevent


class AsyncOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, filter=None, poolSize=50, connectTimeout=5):
        self.log = log
        self._action_queue = gevent.queue.Queue()
        OutboundEventSocket.__init__(self, socket, address, filter, poolSize, connectTimeout)

    def _protocolSend(self, command, args=""):
        self.log.info("[%s] args='%s'" % (command, args))
        res = super(AsyncOutboundEventSocket, self)._protocolSend(command, args)
        self.log.info(str(res))
        return res

    def _protocolSendmsg(self, name, args=None, uuid="", lock=False):
        self.log.info("[%s] args=%s uuid='%s' lock=%s" % (name, str(args), uuid, str(lock)))
        res = super(AsyncOutboundEventSocket, self)._protocolSendmsg(name, args, uuid, lock)
        self.log.info(str(res))
        return res

    def onChannelExecuteComplete(self, ev):
        if ev.getHeader('Application') == 'playback':
            self._action_queue.put(ev)

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
        # wait until playback is done
        self.log.info("Waiting end of playback ...")
        ev = self._action_queue.get()
        # log playback execute response
        self.log.info("Playback done (%s)" % str(ev.getHeader('Application-Response')))
        # finally hangup
        self.hangup()


class AsyncOutboundServer(OutboundServer):
    def __init__(self, address, handleClass, filter=None):
        self.log = StdoutLogger()
        self.log.info("Start server %s ..." % str(address))
        OutboundServer.__init__(self, address, handleClass, filter)

    def doHandle(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._handleClass(socket, address, self.log, filter=self._filter)
        self.log.info("End request from %s" % str(address))



if __name__ == '__main__':
    outboundserver = AsyncOutboundServer(('127.0.0.1', 8084), AsyncOutboundEventSocket)
    outboundserver.serve_forever()

