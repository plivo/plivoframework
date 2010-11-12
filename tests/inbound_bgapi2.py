# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger
import gevent.queue


class MyEventSocket(InboundEventSocket):
    def __init__(self, host, port, password, filter, log=None):
        InboundEventSocket.__init__(self, host, port, password, filter)
        self.log = log
        self.jobqueue = gevent.queue.Queue()

    def onBackgroundJob(self, ev):
        '''
        Event callback for BACKGROUND_JOB .
        '''
        self.jobqueue.put(ev)

    def waitBackgroundJob(self):
        '''
        Wait until BACKGROUND_JOB event was catched and return Event.
        '''
        return self.jobqueue.get()



if __name__ == '__main__':
    log = StdoutLogger()
    try:
        iev = MyEventSocket('127.0.0.1', 8021, 'ClueCon', filter="BACKGROUND_JOB", log=log)
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
        log.info("bgapi success with Job-UUID " + jobuuid)
        log.info("waiting background job ...")
        ev = iev.waitBackgroundJob()
        log.info("background job: %s" % str(ev))


    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

