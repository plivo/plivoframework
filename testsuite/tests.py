# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import os
import sys
import unittest


def make_test():
    return unittest.TextTestRunner()

def make_suite():
    return unittest.TestLoader().loadTestsFromNames([
        'tests.freeswitch.test_events',
        'tests.freeswitch.test_inboundsocket',
    ])

def run_test():
    return make_suite()

def run():
    runner = make_test()
    suite = make_suite()
    runner.run(suite)


if __name__ == '__main__':
    #sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, '.')
    run()
