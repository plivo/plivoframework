#!/usr/bin/env python
try:
    from setuptools import find_packages
except:
    from distutils.core import find_packages

version = open('VERSION.txt').read().strip()
author = "Plivo Team"
author_email = "contact@plivo.org"
maintainer = "Plivo Team"
maintainer_email = "contact@plivo.org"
licence = "MPL 1.1"

setup_args = {
      'name':'plivo',
      'version':version,
      'description':'Plivo framework',
      'url':'http://github.com/miglu/Plivo',
      'author':author,
      'author_email':author_email,
      'maintainer':maintainer,
      'maintainer_email':maintainer_email,
      'platforms':['linux'],
      'long_description':'Framework to create telephony applications',
      'packages':find_packages('src'),
      'package_dir':{'': 'src'},
      'include_package_data':True,
      'scripts':['src/scripts/plivod'],
      'keywords':"telecom voip telephony freeswitch ivr",
      'license':licence,
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

