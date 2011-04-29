# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.
from gevent import monkey; monkey.patch_all()
from gevent.wsgi import WSGIServer

from plivo.utils.logger import StdoutLogger
from plivo.core.errors import ConnectError

from inbound_socket import RESTInboundSocket
from rest_api import rest_server, set_instances
import settings


def start_server(http_address, fs_address, fs_esl_password, log = StdoutLogger()):
    fs_host, fs_port = fs_address.split(':')
    fs_port = int(fs_port)
    inbound_listener = RESTInboundSocket(fs_host, fs_port, fs_esl_password, log=log)
    log.info("Connecting to FreeSWITCH at: '%s'" % (fs_address))
    try:
        inbound_listener.connect()
        set_instances(inbound_listener, log)
        fs_out_address = getattr(settings, 'FS_OUTBOUND_ADDRESS', '127.0.0.1:8084')
        inbound_listener.fs_out_address = fs_out_address
        log.info("Connected to FreeSWITCH")
    except ConnectError, e:
        log.error("Connect failed: %s" % str(e))
        raise SystemExit('exit')

    http_host, http_port = http_address.split(':')
    http_port = int(http_port)
    http_server = WSGIServer((http_host, http_port), rest_server)
    log.info("REST Server started at: 'http://%s'\n" % (http_address))
    http_server.serve_forever()

if __name__ == '__main__':
    http_address = getattr(settings, 'HTTP_ADDRESS', '127.0.0.1:8088')
    fs_in_address = getattr(settings, 'FS_INBOUND_ADDRESS', '127.0.0.1:8021')
    fs_esl_password = getattr(settings, 'FS_ESL_PASSWORD', 'ClueCon')

    start_server(http_address, fs_in_address, fs_esl_password, )
