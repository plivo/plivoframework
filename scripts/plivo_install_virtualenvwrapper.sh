#!/bin/bash

# Plivo Installation script for CentOS 5.5/5.6
# and Debian based distros (Debian 5.0 , Ubuntu 10.04 and above)
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

PLIVO_CONF_PATH=https://github.com/plivo/plivo/blob/master/src/config/default.conf
VIRTUALENV_PATH=~/.virtualenvs

#####################################################
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin
PLIVO_ENV=plivo
REAL_PATH=$VIRTUALENV_PATH/$PLIVO_ENV

# Check if the Virtual Env Directory Exist
if [ $1 ] && [ ! -d "$1" ] ; then
    echo ""
    echo "Usage: $(basename $0) [Existing Virtual Env Path]"
    echo ""
    exit 1
elif [ $1 ] ; then
    VIRTUALENV_PATH=$1
    PLIVO_ENV='plivo'
    REAL_PATH=$VIRTUALENV_PATH'plivo'
fi

echo "VIRTUALENV_PATH=$VIRTUALENV_PATH"
echo "PLIVO_ENV=$PLIVO_ENV"
echo "REAL_PATH=$REAL_PATH"


[ -d $PLIVO_ENV ] && echo "Abort. $PLIVO_ENV already exists !" && exit 1

# Identify Linix Distribution type
if [ -f /etc/debian_version ] ; then
        DIST='DEBIAN'
elif [ -f /etc/redhat-release ] ; then
        DIST='CENTOS'
else
    echo ""
    echo "This Installer should be run on a CentOS or a Debian based system"
    echo ""
    exit 1
fi


clear
echo ""
echo "Plivo Framework will be installed at \"$REAL_PATH\""
echo "Press any key to continue or CTRL-C to exit"
echo ""
read INPUT

declare -i PY_MAJOR_VERSION
declare -i PY_MINOR_VERSION
PY_MAJOR_VERSION=$(python -V 2>&1 |sed -e 's/Python[[:space:]]\+\([0-9]\)\..*/\1/')
PY_MINOR_VERSION=$(python -V 2>&1 |sed -e 's/Python[[:space:]]\+[0-9]\+\.\([0-9]\+\).*/\1/')

if [ $PY_MAJOR_VERSION -ne 2 ] || [ $PY_MINOR_VERSION -lt 4 ]; then
    echo ""
    echo "Python version supported between 2.4.X - 2.7.X"
    echo "Please install a compatible version of python."
    echo ""
    exit 1
fi

echo "Setting up Prerequisites and Dependencies"
case $DIST in
        'DEBIAN')
            sudo apt-get -y install python-setuptools python-dev build-essential libevent-dev
        ;;
        'CENTOS')
            sudo yum -y install python-setuptools python-tools python-devel libevent
        ;;
esac

sudo easy_install virtualenv
sudo easy_install virtualenvwrapper
sudo easy_install pip

# Enable virtualenvwrapper
chk=`grep "virtualenvwrapper" ~/.bashrc|wc -l`
if [ $chk -lt 1 ] ; then
    echo "Set Virtualenvwrapper into bash"
    echo "export WORKON_HOME=\$HOME/.virtualenvs" >> ~/.bashrc
    echo "source /usr/local/bin/virtualenvwrapper.sh" >> ~/.bashrc
fi


# Setup virtualenv
export WORKON_HOME=$HOME/.virtualenvs
source /usr/local/bin/virtualenvwrapper.sh

mkvirtualenv --no-site-packages $PLIVO_ENV
workon $PLIVO_ENV

pip install plivo

mkdir -p $REAL_PATH/etc/plivo &>/dev/null
wget --no-check-certificate $PLIVO_CONF_PATH -O $REAL_PATH/etc/plivo/default.conf
$REAL_PATH/bin/plivo-postinstall &>/dev/null


# Install Complete
clear
echo ""
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
exit 0
