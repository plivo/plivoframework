# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import traceback
from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.utils.logger import StdoutLogger

if __name__ == '__main__':
    log = StdoutLogger()

    log.info('#'*60)
    log.info("Connect with bad host")
    try:
        inbound_event_listener = InboundEventSocket('falsehost', 8021, 'ClueCon')
        inbound_event_listener.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('#'*60)
    log.info("Connect with bad port")
    try:
        inbound_event_listener = InboundEventSocket('127.0.0.1', 9999999, 'ClueCon')
        inbound_event_listener.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('#'*60)
    log.info("Connect with bad password")
    try:
        inbound_event_listener = InboundEventSocket('127.0.0.1', 8021, 'falsepassword')
        inbound_event_listener.connect()
    except:
        [ log.info(line) for line in traceback.format_exc().splitlines() ]
    log.info('#'*60 + '\n')

    log.info('exit')
