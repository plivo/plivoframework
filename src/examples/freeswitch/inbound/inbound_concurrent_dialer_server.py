# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.errors import ConnectError
from plivo.utils.logger import StdoutLogger

import gevent
from gevent import wsgi


CONTACTS = (
            '{originate_timeout=20}user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)',
            '{originate_timeout=20}user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)',
            '{originate_timeout=20}user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)',
           )


class MyEventSocket(InboundEventSocket):
    def __init__(self, host, port, password, filter="ALL", log=None):
        InboundEventSocket.__init__(self, host, port, password, filter)
        self.log = log


    def on_background_job(self, ev):
        '''
        Receives callbacks for BACKGROUND_JOB event.
        '''
        job_uuid = ev['Job-UUID']
        job_cmd = ev['Job-Command']
        job_arg = ev['Job-Command-Arg']
        self.log.debug("BackGround JOB Recieved" )
        self.log.debug("%s %s, args %s \n\n" % (job_uuid, job_cmd, job_arg))


    def on_channel_hangup(self, ev):
        '''
        Receives callbacks for BACKGROUND_JOB event.
        '''
        job_uuid = ev['Job-UUID']
        job_cmd = ev['Job-Command']
        job_arg = ev['Job-Command-Arg']
        self.log.debug("Channel Hangup" )
        self.log.debug("%s %s, args %s \n\n " % (job_uuid, job_cmd, job_arg))


def spawn_originate(inbound_event_listener, contact, log):
    log.info("Originate command")
    fs_bg_api_string = \
        "originate %s &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)" \
        % contact
    bg_api_response = inbound_event_listener.bgapi(fs_bg_api_string)
    log.info(str(bg_api_response))
    job_uuid = bg_api_response.get_job_uuid()
    if not job_uuid:
        log.error("bgapi %s: job uuid not found \n\n" % fs_bg_api_string)
        return

    log.info("bgapi %s => Job-UUID %s \n\n" % (fs_bg_api_string, job_uuid))


def dispatch_requests(env, start_response):
    if env['PATH_INFO'] == '/':
        if CONTACTS:
            start_response('200 OK', [('Content-Type', 'text/html')])

            #Put logic to handle the request each time
            pool = gevent.pool.Pool(len(CONTACTS))
            jobs = [pool.spawn(spawn_originate, inbound_event_listener, contact, log) for contact in CONTACTS]
            gevent.joinall(jobs)
            log.debug("All originate commands done")

            return ["<b>Executed Request</b>"]

    start_response('404 Not Found', [('Content-Type', 'text/html')])
    return ['<h1>Wrong Usage - Command Not found</h1>']


if __name__ == '__main__':
    log = StdoutLogger()
    #Connect to freeswitch ESL in inbound mode
    inbound_event_listener = MyEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL", log=log)
    try:
        inbound_event_listener.connect()
    except ConnectError, e:
        log.error("connect failed: %s" % str(e))
        raise SystemExit('exit')

    #Connect to freeswitch ESL in inbound mode
    wsgi.WSGIServer(('', 8088), dispatch_requests).serve_forever()
