# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.core.errors import ConnectError
from plivo.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        inbound_event_listener = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL")
        try:
            inbound_event_listener.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        api_response = inbound_event_listener.api("FALSECOMMAND")
        log.info(str(api_response))
        if not api_response.is_success():
            log.error("api failed with response %s" % api_response.get_response())
            raise SystemExit('exit')

        log.info("api success with response %s" % api_response.get_response())

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")
