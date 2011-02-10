#!/usr/bin/env python

from telephonie import (__version__, __author__, __author_email__, __maintainer__, __maintainer_email__, __licence__)

setup_args = {
      'name':'telephonie',
      'version':__version__,
      'description':'Telephonie framework',
      'url':'http://github.com/miglu/Telephonie',
      'author':__author__,
      'author_email':__author_email__,
      'maintainer':__maintainer__,
      'maintainer_email':__maintainer_email__,
      'platforms':['linux'],
      'long_description':'Framework to create telephony applications using FreeSWITCH',
      'packages':['telephonie', 'telephonie.core', 'telephonie.utils'],
      'scripts':['scripts/telephonied'],
      'keywords':"telecom voip telephony freeswitch ivr",
      'license':__licence__,
      'zip_safe':False,
      'classifiers':[
        "Programming Language :: Python",
        "Operating System :: POSIX",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications",
        "Topic :: Multimedia",
        "Environment :: Console",
        "Environment :: Web Environment",
        "Programming Language :: Python",
        "Intended Audience :: Developers",
        "Intended Audience :: Telecommunications Industry",
        "License :: OSI Approved :: Mozilla Public License 1.1 (MPL 1.1)",
        "Development Status :: 4 - Beta"]
}


try:
    from setuptools import setup
    setup_args['install_requires'] = ['gevent']
except ImportError:
    from distutils.core import setup
    setup_args['requires'] = ['gevent']
  
setup(**setup_args)
