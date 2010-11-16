# -*- coding: utf-8 -*-
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()
    try:
        iev = InboundEventSocket('127.0.0.1', 8021, 'ClueCon', filter="ALL")
        try:
            iev.connect()
        except ConnectError, e:
            log.error("connect failed: %s" % str(e))
            raise SystemExit('exit')

        filterResponse = iev.filter("Event-Name CHANNEL_ANSWER")
        log.info(str(filterResponse))
        if not filterResponse.isSuccess():
            log.error("filter failed with response %s" % filterResponse.getResponse())
            raise SystemExit('exit')

        log.info("filter success with response %s" % filterResponse.getResponse())

    except (SystemExit, KeyboardInterrupt): pass

    log.info("exit")
            
        

