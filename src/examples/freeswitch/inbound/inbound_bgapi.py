# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.errors import ConnectError
from plivo.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        inbound_event_listener = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="BACKGROUND_JOB")
        try:
            inbound_event_listener.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        fs_bg_api_string = "originate user/1000 &playback(/usr/local/freeswitch/sounds/en/us/callie/base256/8000/liberty.wav)"
        bg_api_response = inbound_event_listener.bgapi(fs_bg_api_string)
        log.info(str(bg_api_response))
        log.info(bg_api_response.get_response())
        if not bg_api_response.is_success():
            log.error("bgapi failed !")
            raise SystemExit('exit')

        job_uuid = bg_api_response.get_job_uuid()
        if not job_uuid:
            log.error("bgapi jobuuid not found !")
            raise SystemExit('exit')

        log.info("bgapi success with Job-UUID " + job_uuid)

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")
