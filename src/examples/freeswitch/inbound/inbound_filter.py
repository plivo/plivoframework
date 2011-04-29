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

        filter_response = inbound_event_listener.filter("Event-Name CHANNEL_ANSWER")
        log.info(str(filter_response))
        if not filter_response.is_success():
            log.error("filter failed with response %s" % filter_response.get_response())
            raise SystemExit('exit')

        log.info("filter success with response %s" % filter_response.get_response())

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")
