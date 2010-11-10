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

        response = iev.bgapi("originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)")
        log.info(str(response))
        log.info(response.getResponse())
        if not response.getStatus():
            log.error("bgapi failed !")
            raise SystemExit('exit')

        jobuuid = response.getJobUUID()
        if not jobuuid:
            log.error("bgapi jobuuid not found :")
            raise SystemExit('exit')

        log.info("bgapi success with Job-UUID" + jobuuid)
        while True:
            job = response.getBackgroundJob()
            if job:
                log.info(str(job))
                if not job.getStatus():
                    log.error("backgroundjob failed with response %s" % job.getResponse())
                    raise SystemExit('exit')

                log.info("backgroundjob done with response %s" % job.getResponse())
                break
            gevent.sleep(0.05)

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

