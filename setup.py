from setuptools import find_packages
import sys

requires = ['gevent', 'flask==0.7.2', 'ujson==1.9', 'redis==2.4.9']

if sys.prefix == '/usr':
    etc_prefix = '/etc'
else:
    etc_prefix = sys.prefix + '/etc'


author = "Plivo Team"
author_email = "hello@plivo.org"
maintainer = "Plivo Team"
maintainer_email = "hello@plivo.org"
license = "MPL 1.1"

setup_args = {
      'name':'plivo',
      'version':'0.1.0',
      'description':'Plivo - Rapid Communication Application Development Framework',
      'url':'http://github.com/plivo/plivo',
      'author':author,
      'author_email':author_email,
      'maintainer':maintainer,
      'maintainer_email':maintainer_email,
      'platforms':['linux'],
      'long_description':'Framework to create communication applications rapidly in any language',
      'package_dir':{'': 'src'},
      'packages':find_packages('src'),
      'include_package_data':True,
      'scripts':['src/bin/plivo-rest',
                 'src/bin/plivo-outbound',
                 'src/bin/plivo-cache',
                 'src/bin/plivo-postinstall',
                 'src/bin/wavdump.py',
                 'src/bin/wavstream.sh',
                 'src/bin/cacheserver',
                 'src/bin/plivo'],
      'data_files':[(etc_prefix+'/plivo/', ['src/config/default.conf', 'src/config/cache.conf', 
                    'src/initscripts/centos/plivo', 'src/initscripts/centos/plivocache']),
                   ],
      'keywords':"telecom voip telephony freeswitch ivr rest",
      'license':license,
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
        "Development Status :: 1 - Beta"]
}


try:
    from setuptools import setup
    setup_args['install_requires'] = requires
except ImportError:
    from distutils.core import setup
    setup_args['requires'] = requires

# setup
setup(**setup_args)
