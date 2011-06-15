# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.errors import ConnectError
from plivo.utils.logger import StdoutLogger
import gevent.event



CONTACTS = (
            '{originate_timeout=20}sofia/internal/hansolo@star.war',
            '{originate_timeout=20}sofia/internal/luke@star.war',
            '{originate_timeout=20}sofia/internal/anakin@star.war',
            '{originate_timeout=20}sofia/internal/palpatine@star.war',
            '{originate_timeout=20}sofia/internal/c3po@star.war',
            '{originate_timeout=20}sofia/internal/r2d2@star.war',
            '{originate_timeout=20}sofia/internal/chewbacca@star.war',
            '{originate_timeout=20}sofia/internal/leia@star.war',
            '{originate_timeout=20}sofia/internal/padme@star.war',
            '{originate_timeout=20}sofia/internal/yoda@star.war',
            '{originate_timeout=20}sofia/internal/obiwan@star.war',
           )


class MyEventSocket(InboundEventSocket):
    def __init__(self, host, port, password, filter="ALL", log=None):
        self.log = log
        self.jobs = {}
        InboundEventSocket.__init__(self, host, port, password, filter)

    def track_job(self, job_uuid):
        self.jobs[job_uuid] = gevent.event.AsyncResult()

    def untrack_job(self, job_uuid):
        try:
            del self.jobs[job_uuid]
        except:
            pass

    def on_background_job(self, ev):
        '''
        Receives callbacks for BACKGROUND_JOB event.
        '''
        job_uuid = ev['Job-UUID']
        job_cmd = ev['Job-Command']
        job_arg = ev['Job-Command-Arg']
        self.log.debug("%s %s, args %s => %s" % (job_uuid, job_cmd, job_arg, ev.get_body()))
        try:
            async_result = self.jobs[job_uuid]
            async_result.set(ev)
        except KeyError:
            # job is not tracked
            return

    def wait_for_job(self, job_uuid):
        '''
        Waits until BACKGROUND_JOB event was caught and returns Event.
        '''
        try:
            async_result = self.jobs[job_uuid]
            return async_result.wait()
        except KeyError:
            # job is not tracked
            return None


def spawn_originate(inbound_event_listener, contact, log):
    fs_bg_api_string = \
        "originate %s &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)" \
        % contact
    bg_api_response = inbound_event_listener.bgapi(fs_bg_api_string)
    log.info(str(bg_api_response))
    job_uuid = bg_api_response.get_job_uuid()
    if not job_uuid:
        log.error("bgapi %s: job uuid not found" % fs_bg_api_string)
        return
    inbound_event_listener.track_job(job_uuid)
    log.info("bgapi %s => Job-UUID %s" % (fs_bg_api_string, job_uuid))
    log.info("waiting job %s ..." % job_uuid)
    ev = inbound_event_listener.wait_for_job(job_uuid)

    log.info("bgapi %s => %s" % (fs_bg_api_string, str(ev.get_body())))


if __name__ == '__main__':
    log = StdoutLogger()
    try:
        inbound_event_listener = MyEventSocket('127.0.0.1', 8021, 'ClueCon', filter="BACKGROUND_JOB", log=log)
        try:
            inbound_event_listener.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')
        if not CONTACTS:
            log.error("No CONTACTS !")
            raise SystemExit('exit')
        pool = gevent.pool.Pool(len(CONTACTS))
        for contact in CONTACTS:
            pool.spawn(spawn_originate, inbound_event_listener, contact, log)
        pool.join()
        log.debug("all originate commands done")
    except (SystemExit, KeyboardInterrupt):
        pass
    log.info("exit")
