# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger

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
            
        

