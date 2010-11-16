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

        apiResponse = iev.api("originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)")
        log.info(str(apiResponse))
        if not apiResponse.isSuccess():
            log.error("api failed with response %s" % apiResponse.getResponse())
            raise SystemExit('exit')

        log.info("api success with response %s" % apiResponse.getResponse())

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

