try:
    from setuptools import find_packages
except:
    from distutils.core import find_packages

author = "Plivo Team"
author_email = "contact@plivo.org"
maintainer = "Plivo Team"
maintainer_email = "contact@plivo.org"
licence = "MPL 1.1"

setup_args = {
      'name':'plivo',
      'version':'0.1.0',
      'description':'Plivo - Rapid Communication Application Development Framework',
      'url':'http://github.com/miglu/Plivo',
      'author':author,
      'author_email':author_email,
      'maintainer':maintainer,
      'maintainer_email':maintainer_email,
      'platforms':['linux'],
      'long_description':'Framework to create communication applications rapidly in any language',
      'package_dir':{'': 'src'},
      'packages':find_packages('src'),
      'include_package_data':True,
      'scripts':['src/scripts/plivo_rest_server',
                 'src/scripts/plivo_outbound_server',
                 'src/scripts/plivo'],
      'keywords':"telecom voip telephony freeswitch ivr rest",
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
        "Development Status :: 1 - Beta"]
}



def post_install():
    import sys
    import os
    import shutil
    prefix = sys.prefix
    # set plivo script
    f = open(prefix + '/bin/plivo', 'r')
    buff = f.read()
    f.close()
    new_buff = buff.replace('__PREFIX__', prefix)
    f = open(prefix + '/bin/plivo', 'w')
    f.write(new_buff)
    f.close()
    # create config directory
    try:
        os.mkdir(prefix + '/config')
    except:
        pass
    # copy default config file to config directory
    shutil.copy2('src/config/plivo_rest.conf', prefix + '/config/')


try:
    from setuptools import setup
    setup_args['install_requires'] = ['gevent', 'flask']
except ImportError:
    from distutils.core import setup
    setup_args['requires'] = ['gevent', 'flask']

setup(**setup_args)
post_install()

