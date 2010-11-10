# -*- coding: utf-8 -*-
import gevent
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

        responses = []
        jobresponses = []
        for x in xrange(200):
            responses.append(iev.bgapi("originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)"))

        bgapicount = len(responses)

        while True:
            for res in responses[:]:
                if res.getBackgroundJob():
                    jobresponses.append(res)
                    responses.remove(res)
                gevent.sleep(0.02)
            if len(responses) == 0:
                break
        for response in jobresponses:
            log.debug(str(response))
            log.debug(str(response.getBackgroundJob()))

        log.info("number of bgapi commands: %d" % bgapicount)
        log.info("number of background_job event: %d" % len(jobresponses))

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

