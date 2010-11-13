# -*- coding: utf-8 -*-
"""
Outbound Event Socket class
"""

from telephonie.core.outboundsocket import (OutboundEventSocket, OutboundServer)
from telephonie.utils.logger import StdoutLogger


class MyOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, filter="ALL", poolSize=50, connectTimeout=5):
        self.log = log
        self.log.info("New client " + str(address))
        OutboundEventSocket.__init__(self, socket, address, filter, poolSize, connectTimeout)

    def run(self):
        self.log.info("Channel UUID => %s" % str(self.client.getHeader('Core-UUID')))
        res = self.answer()
        self.log.info("Answer => " + str(res))
        res = self.playback("/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav", terminators="*")
        self.log.info("Playback => " + str(res))
        res = self.hangup()
        self.log.info("Hangup " + str(res))
        self.disconnect()


class MyOutboundServer(OutboundServer):
    def __init__(self, address, handle, filter="ALL"):
        self.log = StdoutLogger()
        self.log.info("Start server %s ..." % str(address))
        OutboundServer.__init__(self, address, handle)

    def doHandle(self, socket, address):
        self._handleClass(socket, address, self.log, filter=self._filter)



if __name__ == '__main__':
    outboundserver = MyOutboundServer(('127.0.0.1', 8084), MyOutboundEventSocket)
    outboundserver.serve_forever()

