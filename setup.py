#!/usr/bin/env python
try:
    from setuptools import find_packages
except:
    from distutils.core import find_packages

version = open('VERSION.txt').read().strip()
author = "Telephonie Team"
author_email = "telephonie@miglu.com"
maintainer = "Telephonie Team"
maintainer_email = "telephonie@miglu.com"
licence = "MPL 1.1"

setup_args = {
      'name':'telephonie',
      'version':version,
      'description':'Telephonie framework',
      'url':'http://github.com/miglu/Telephonie',
      'author':author,
      'author_email':author_email,
      'maintainer':maintainer,
      'maintainer_email':maintainer_email,
      'platforms':['linux'],
      'long_description':'Framework to create telephony applications using FreeSWITCH',
      'packages':find_packages('src'),
      'package_dir':{'': 'src'},
      'scripts':['src/scripts/telephonied'],
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
