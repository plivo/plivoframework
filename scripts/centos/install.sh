#!/bin/sh

# Plivo Installation script for CentOS 5.5/5.6
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


PLIVO_CONF_PATH=https://github.com/miglu/plivo/blob/master/src/config/default.conf
PLIVO_EZSETUP_PATH=https://github.com/miglu/plivo/blob/master/scripts/centos/ez_setup.py

#####################################################
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin
PLIVO_ENV=$1

CURRENT=$PWD

# Check if Install Directory Present
if [ ! $1 ] || [ -z "$1" ] ; then
    echo ""
    echo "Usage: $(basename $0) <Install Directory Path>"
    echo ""
    exit 1
fi
[ -d $PLIVO_ENV ] && echo "Abort. $PLIVO_ENV already exists !" && exit 1


# Set full path
echo "$PLIVO_ENV" |grep '^/' -q && REAL_PATH=$PLIVO_ENV || REAL_PATH=$PWD/$PLIVO_ENV


# Identify Linix Distribution type
if [ -f /etc/redhat-release ] ; then
        DIST='CENTOS'
else
    echo ""
    echo "This Installer should be run on a CentOS system"
    echo ""
    exit 1
fi

clear
echo ""
echo "Plivo Framework will be installed at \"$REAL_PATH\""
echo "Press any key to continue or CTRL-C to exit"
echo ""
read INPUT


PY_MINOR_VERSION=$(python --version 2>&1 | sed 's/Python[[:space:]]\+[0-9]\+\.\([0-9]\+\).*/\1/')


echo "Setting up Prerequisites and Dependencies"

if [ $(echo "$PY_MINOR_VERSION < 5" | bc) -eq 1  ] ; then

    yum -y install autoconf automake libtool gcc-c++ ncurses-devel make wget curl-devel curl fileutils expat-devel libxml2 libxml2-devel gettext-devel libevent

    # Install Python 2.6
    mkdir $REAL_PATH
    mkdir $REAL_PATH/python
    export DEPLOY=$REAL_PATH/python
    mkdir $REAL_PATH/source
    cd $REAL_PATH/source
    wget http://www.python.org/ftp/python/2.6.6/Python-2.6.6.tgz
    tar -xvf Python-2.6.6.tgz
    cd Python-2.6.6
    ./configure —prefix=$DEPLOY
    make
    make install

cd $REAL_PATH/source
wget $PLIVO_EZSETUP_PATH
python ez_setup.py

easy_install --prefix $DEPLOY virtualenv
easy_install --prefix $DEPLOY pip
fi

# Setup virtualenv
virtualenv --no-site-packages $REAL_PATH
source $REAL_PATH/bin/activate

pip install gevent
pip install yolk
pip install plivo

mkdir -p $REAL_PATH/etc/plivo &>/dev/null
wget $PLIVO_CONF_PATH
mv default.conf $REAL_PATH/etc/plivo/
$REAL_PATH/bin/plivo-postinstall &>/dev/null

cd $CURRENT

# Install Complete
clear
echo ""
echo ""
echo "**************************************************************"
echo "Congratulations, Plivo Framework is now installed in $REAL_PATH"
echo "**************************************************************"
echo
echo "* Configure plivo :"
echo "    The default config is $REAL_PATH/etc/plivo/default.conf"
echo "    Here you can add/remove/modify config files to run mutiple plivo instances"
echo
echo "* To Start Plivo :"
echo "    $REAL_PATH/bin/plivo start"
echo
echo "**************************************************************"
echo ""
echo ""
echo "Visit http://www.plivo.org for documentation and examples"
echo ""
exit 0
