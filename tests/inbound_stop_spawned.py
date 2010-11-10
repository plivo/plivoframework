# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger
import gevent

def stop(iev, log):
    log.info("stopping now !")
    iev.disconnect()
    log.info("stopped !")

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        iev = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL")
        try:
            iev.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        log.info("stopping in 5 seconds !")
        gevent.spawn_later(5, stop, iev, log)

        iev.serve_forever()

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")

