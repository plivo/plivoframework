# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from gevent import monkey; monkey.patch_all()
import gevent
import os

from gevent.wsgi import WSGIServer
from flask import Flask

from plivo.utils.logger import StdoutLogger
from plivo.core.errors import ConnectError

from rest_api import PlivoRestApi
from inbound_socket import RESTInboundSocket
import urls
import helpers

class PlivoRestServer(PlivoRestApi):
    name = "PlivoRestServer"

    def __init__(self, configfile, log = StdoutLogger()):
        # load config
        self._config = helpers.get_config(configfile)
        # create flask app
        self.app = Flask(self.name)
        self.app.secret_key = helpers.get_conf_value(self._config, 'rest_server', 'SECRET_KEY')
        if helpers.get_conf_value(self._config, 'rest_server', 'DEBUG') == 'true':
            self.app.debug = True
        self.log = log
        # create rest server
        self.fs_inbound_address = helpers.get_conf_value(self._config, 'freeswitch', 'FS_INBOUND_ADDRESS')
        fs_host, fs_port = self.fs_inbound_address.split(':', 1)
        fs_port = int(fs_port)
        fs_password = helpers.get_conf_value(self._config, 'freeswitch', 'FS_PASSWORD')
        self._rest_inbound_socket = RESTInboundSocket(fs_host, fs_port, fs_password, filter='ALL', log=self.log)
        fs_out_address = helpers.get_conf_value(self._config, 'freeswitch', 'FS_OUTBOUND_ADDRESS')
        self._rest_inbound_socket.fs_outbound_address = fs_out_address
        # expose api functions to flask app
        for path, func_desc in urls.URLS.iteritems():
            func, methods = func_desc
            fn = getattr(self, func.__name__)
            self.app.add_url_rule(path, func.__name__, fn, methods=methods)
        # create wsgi server
        self.http_address = helpers.get_conf_value(self._config, 'rest_server', 'HTTP_ADDRESS')
        http_host, http_port = self.http_address.split(':', 1)
        http_port = int(http_port)
        self.http_server = WSGIServer((http_host, http_port), self.app)

    def start(self):
        retry_seconds = 10.0
        while True:
            try:
                self.log.info("Trying to connect to FreeSWITCH at: %s" %self.fs_inbound_address)
                self._rest_inbound_socket.connect()
                self.log.info("Connected to FreeSWITCH")
                self.log.info("REST Server started at: 'http://%s'\n" % (self.http_address))
                self.http_server.serve_forever()
            except ConnectError, e:
                self.log.error("Connect failed: %s" % str(e))
            except (SystemExit, KeyboardInterrupt):
                break
            self.log.error("Reconnecting in %s seconds" %retry_seconds)
            gevent.sleep(retry_seconds)
            retry_seconds += 20.0
        self.log.info("REST Server Exited")


if __name__ == '__main__':
    server = PlivoRestServer(configfile='./plivo_rest.conf')
    server.start()
