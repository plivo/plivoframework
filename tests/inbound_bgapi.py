# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        iev = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="BACKGROUND_JOB")
        try:
            iev.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        bgAPIResponse = iev.bgapi("originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)")
        log.info(str(bgAPIResponse))
        log.info(bgAPIResponse.getResponse())
        if not bgAPIResponse.isSuccess():
            log.error("bgapi failed !")
            raise SystemExit('exit')

        jobuuid = bgAPIResponse.getJobUUID()
        if not jobuuid:
            log.error("bgapi jobuuid not found !")
            raise SystemExit('exit')

        log.info("bgapi success with Job-UUID " + jobuuid)

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

