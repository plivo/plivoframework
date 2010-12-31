# -*- coding: utf-8 -*-
'''
Simple hack to redirect stderr output to a logger instance.
'''
import sys

_stderr = sys.stderr


class _StderrRedirect(object):
    def __init__(self, log):
        self.log = log

    def write(self, msg):
        for line in msg.splitlines():
            line = line.strip()
            if line:
                self.log.error(line)

    def flush(self):
        return


def patch(log):
    '''
    Patch stderr to be redirected to a logger instance.
    '''
    sys.stderr = _StderrRedirect(log)


def restore():
    '''
    Restore stderr.
    '''
    sys.stderr = _stderr
    

