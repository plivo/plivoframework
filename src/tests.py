# -*- coding: utf-8 -*-
import unittest

__all__ = ['test_events', 'test_inboundsocket']

def make_test():
    return unittest.TextTestRunner()

def make_suite():
    return unittest.TestLoader().loadTestsFromNames([
        'tests.test_events',
        'tests.test_inboundsocket',
    ])

def run_test():
    return make_suite()

def run():
    runner = make_test()
    suite = make_suite()
    runner.run(suite)


if __name__ == '__main__':
    import os
    import sys
    #sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, '.')
    run()
