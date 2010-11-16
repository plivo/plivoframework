#!/usr/bin/env python

from setuptools import find_packages, setup
from telephonie import (__version__, __author__, __author_email__, __maintainer__, __maintainer_email__, __licence__)

setup(name='telephonie',
      version=__version__,
      description='Telephonie framework',
      url='http://bitbucket.org/miglu/telephonie',
      author=__author__,
      author_email=__author_email__,
      maintainer=__maintainer__,
      maintainer_email=__maintainer_email__,
      platforms=['linux'],
      long_description='Framework to create telephony applications using FreeSWITCH',
      packages=['telephonie', 'telephonie.core', 'telephonie.utils'],
      license=__licence__,
      install_requires=['gevent'],
      zip_safe=False,
      classifiers=[
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
        "Development Status :: 2 - Pre-Alpha"]
     )

