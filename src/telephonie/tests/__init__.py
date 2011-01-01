# -*- coding: utf-8 -*-
import unittest

__all__ = ['test_events']

def make_test():
    return unittest.TextTestRunner()

def make_suite():
    return unittest.TestLoader().loadTestsFromNames([
        'telephonie.tests.test_events',
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
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    run()
