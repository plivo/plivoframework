# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        iev = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL")
        try:
            iev.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        response = iev.api("originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)")
        log.info(str(response))
        if not response.getStatus():
            log.error("api failed with response %s" % response.getResponse())
            raise SystemExit('exit')

        log.info("api success with response %s" % response.getResponse())

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

