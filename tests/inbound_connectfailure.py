# -*- coding: utf-8 -*-
import traceback
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()

    log.info('#'*60)
    log.info("Connect with bad host")
    try:
        iev = InboundEventSocket('falsehost', 8021, 'ClueCon')
        iev.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('#'*60)
    log.info("Connect with bad port")
    try:
        iev = InboundEventSocket('127.0.0.1', 9999999, 'ClueCon')
        iev.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('#'*60)
    log.info("Connect with bad password")
    try:
        iev = InboundEventSocket('127.0.0.1', 8021, 'falsepassword')
        iev.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('exit')
        

