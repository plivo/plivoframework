# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


from gevent import monkey
monkey.patch_all()

import grp
import os
import pwd
import signal
import sys
import optparse

import gevent

from plivo.core.freeswitch import outboundsocket
from plivo.rest.freeswitch.outboundsocket import PlivoOutboundEventSocket
from plivo.rest.freeswitch import helpers
import plivo.utils.daemonize
from plivo.utils.logger import StdoutLogger, FileLogger, SysLogger, DummyLogger, HTTPLogger

"""
PlivoOutboundServer is our event_socket server listening for connection
with Freeswitch.

This server by default is listens on 127.0.0.1:8084
"""


class PlivoOutboundServer(outboundsocket.OutboundServer):
    def __init__(self, configfile, daemon=False,
                    pidfile='/tmp/plivo_outbound.pid'):
        self._request_id = 0
        self._daemon = daemon
        self._run = False
        self._pidfile = pidfile
        self.configfile = configfile
        # load config
        self._config = None
        self.cache = {}
        self.load_config()

        # This is where we define the connection with the
        # Plivo XML element Processor
        outboundsocket.OutboundServer.__init__(self, (self.fs_host, self.fs_port),
                                PlivoOutboundEventSocket, filter=None)

    def load_config(self, reload=False):
        # backup config
        backup_config = self._config
        # create config
        config = helpers.PlivoConfig(self.configfile)
        try:
            # read config
            config.read()

            # set trace flag
            self._trace = config.get('outbound_server', 'TRACE', default='false') == 'true'

            if not reload:
                # create first logger if starting
                self.create_logger(config=config)
                self.log.info("Starting ...")
                self.log.warn("Logger %s" % str(self.log))

            # create outbound server
            if not reload:
                self.fs_outbound_address = config.get('outbound_server', 'FS_OUTBOUND_ADDRESS')
                self.fs_host, fs_port = self.fs_outbound_address.split(':', 1)
                self.fs_port = int(fs_port)

            self.default_answer_url = config.get('common', 'DEFAULT_ANSWER_URL')

            self.default_hangup_url = config.get('common', 'DEFAULT_HANGUP_URL', default='')

            self.default_http_method = config.get('common', 'DEFAULT_HTTP_METHOD', default='')
            if not self.default_http_method in ('GET', 'POST'):
                self.default_http_method = 'POST'

            self.key = config.get('common', 'AUTH_ID', default='')
            self.secret = config.get('common', 'AUTH_TOKEN', default='')

            self.extra_fs_vars = config.get('common', 'EXTRA_FS_VARS', default='')
            self.proxy_url = config.get('common', 'PROXY_URL', default=None)

            # load cache params
            self.cache['url'] = config.get('common', 'CACHE_URL', default='')
            self.cache['script'] = config.get('common', 'CACHE_SCRIPT', default='')
            if not self.cache['url'] or not self.cache['script']:
                self.cache = {}

            # create new logger if reloading
            if reload:
                self.create_logger(config=config)
                self.log.warn("New logger %s" % str(self.log))

            # set new config
            self._config = config
            self.log.info("Config : %s" % str(self._config.dumps()))

        except Exception, e:
            if backup_config:
                self._config = backup_config
                self.log.warn("Error reloading config: %s" % str(e))
                self.log.warn("Rollback to the last config")
                self.log.info("Config : %s" % str(self._config.dumps()))
            else:
                sys.stderr.write("Error loading config: %s" % str(e))
                sys.stderr.flush()
                raise e

    def reload(self):
        self.log.warn("Reload ...")
        self.load_config(reload=True)
        self.log.warn("Reload done")

    def _get_request_id(self):
        try:
            self._request_id += 1
        except OverflowError:
            self._request_id = 1
        return self._request_id

    def handle_request(self, socket, address):
        request_id = self._get_request_id()
        self.log.info("(%d) New request from %s" % (request_id, str(address)))
        self._requestClass(socket, address, self.log, self.cache,
                           default_answer_url=self.default_answer_url,
                           default_hangup_url=self.default_hangup_url,
                           default_http_method=self.default_http_method,
                           extra_fs_vars=self.extra_fs_vars,
                           auth_id=self.key,
                           auth_token=self.secret,
                           request_id=request_id,
                           trace=self._trace,
                           proxy_url=self.proxy_url
                           )
        self.log.info("(%d) End request from %s" % (request_id, str(address)))

    def create_logger(self, config):
        """This will create a logger using helpers.PlivoConfig instance

        Based on the settings in the configuration file,
        LOG_TYPE will determine if we will log in file, syslog, stdout, http or dummy (no log)
        """

        if self._daemon is False:
            logtype = config.get('outbound_server', 'LOG_TYPE')
            if logtype == 'dummy':
                self.log = DummyLogger()
            else:
                self.log = StdoutLogger()
            self.log.set_debug()
        else:
            logtype = config.get('outbound_server', 'LOG_TYPE')
            if logtype == 'file':
                logfile = config.get('outbound_server', 'LOG_FILE')
                self.log = FileLogger(logfile)
            elif logtype == 'syslog':
                syslogaddress = config.get('outbound_server', 'SYSLOG_ADDRESS')
                syslogfacility = config.get('outbound_server', 'SYSLOG_FACILITY')
                self.log = SysLogger(syslogaddress, syslogfacility)
            elif logtype == 'dummy':
                self.log = DummyLogger()
            elif logtype == 'http':
                url = config.get('outbound_server', 'HTTP_LOG_URL')
                method = config.get('outbound_server', 'HTTP_LOG_METHOD')
                fallback_file = config.get('outbound_server', 'HTTP_LOG_FILE_FAILURE')
                self.log = HTTPLogger(url=url, method=method, fallback_file=fallback_file)
            else:
                self.log = StdoutLogger()
            log_level = config.get('outbound_server', 'LOG_LEVEL', default='INFO')
            if log_level == 'DEBUG' or self._trace is True:
                self.log.set_debug()
            elif log_level == 'INFO':
                self.log.set_info()
            elif log_level == 'ERROR':
                self.log.set_error()
            elif log_level in ('WARN', 'WARNING'):
                self.log.set_warn()

    def do_daemon(self):
        """This will daemonize the current application

        Two settings from our configuration files are also used to run the
        daemon under a determine user & group.

        USER : determine the user running the daemon
        GROUP : determine the group running the daemon
        """
        # get user/group from config
        user = self._config.get('outbound_server', 'USER', default='')
        group = self._config.get('outbound_server', 'GROUP', default='')
        if not user or not group:
            uid = os.getuid()
            user = pwd.getpwuid(uid)[0]
            gid = os.getgid()
            group = grp.getgrgid(gid)[0]
        # daemonize now
        plivo.utils.daemonize.daemon(user, group, path='/',
                                     pidfile=self._pidfile,
                                     other_groups=())

    def sig_term(self, *args):
        self.stop()
        self.log.warn("Shutdown ...")
        sys.exit(0)

    def sig_hup(self, *args):
        self.reload()

    def start(self):
        self.log.info("Starting OutboundServer ...")
        # catch SIG_TERM
        gevent.signal(signal.SIGTERM, self.sig_term)
        gevent.signal(signal.SIGHUP, self.sig_hup)
        # run
        self._run = True
        if self._daemon:
            self.do_daemon()
        super(PlivoOutboundServer, self).start()
        self.log.info("OutboundServer started at '%s'" \
                                    % str(self.fs_outbound_address))
        self.serve_forever()
        self.log.info("OutboundServer Exited")


def main():
    parser = optparse.OptionParser()
    parser.add_option("-c", "--configfile", action="store", type="string",
                      dest="configfile",
                      help="use plivo config file (argument is mandatory)",
                      metavar="CONFIGFILE")
    parser.add_option("-p", "--pidfile", action="store", type="string",
                      dest="pidfile",
                      help="write pid to PIDFILE (argument is mandatory)",
                      metavar="PIDFILE")
    (options, args) = parser.parse_args()

    configfile = options.configfile
    pidfile = options.pidfile

    if not configfile:
        configfile = './etc/plivo/default.conf'
        if not os.path.isfile(configfile):
            raise SystemExit("Error : Default config file mising at '%s'. Please specify -c <configfilepath>" %configfile)
    if not pidfile:
        pidfile='/tmp/plivo_outbound.pid'

    outboundserver = PlivoOutboundServer(configfile=configfile,
                                    pidfile=pidfile, daemon=False)
    outboundserver.start()


if __name__ == '__main__':
    main()
