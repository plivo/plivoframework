# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger
import gevent

def stop(inbound_event_listener, log):
    log.info("stopping now !")
    inbound_event_listener.disconnect()
    log.info("stopped !")

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        inbound_event_listener = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL")
        try:
            inbound_event_listener.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        log.info("stopping in 5 seconds !")
        gevent.spawn_later(5, stop, inbound_event_listener, log)

        inbound_event_listener.serve_forever()

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

