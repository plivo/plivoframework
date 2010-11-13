# -*- coding: utf-8 -*-
"""
Outbound server example in sync mode full .
"""

from telephonie.core.outboundsocket import (OutboundEventSocket, OutboundServer)
from telephonie.utils.logger import StdoutLogger


class SyncOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, filter="ALL", poolSize=50, connectTimeout=5):
        self.log = log
        OutboundEventSocket.__init__(self, socket, address, filter, poolSize, connectTimeout)

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

    def run(self):
        self.uuid = str(self.client.getHeader('Channel-Unique-ID'))
        self.log.info("Channel Unique ID => %s" % self.uuid)
        self.answer()
        self.playback("/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav", terminators="*")
        self.hangup()
        self.disconnect()


class SyncOutboundServer(OutboundServer):
    def __init__(self, address, handleClass, filter="ALL"):
        self.log = StdoutLogger()
        self.log.info("Start server %s ..." % str(address))
        OutboundServer.__init__(self, address, handleClass)

    def doHandle(self, socket, address):
        self.log.info("New request from %s" % str(address))
        self._handleClass(socket, address, self.log, filter=self._filter)
        self.log.info("End request from %s" % str(address))



if __name__ == '__main__':
    outboundserver = SyncOutboundServer(('127.0.0.1', 8084), SyncOutboundEventSocket)
    outboundserver.serve_forever()

