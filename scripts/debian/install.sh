#!/bin/sh

# Plivo Installation script for Debian based distros (Debian 5.0 , Ubuntu 10.04 and above)
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


PLIVO_CONF_PATH=https://github.com/miglu/plivo/blob/master/src/config/default.conf

#####################################################
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin
PLIVO_ENV=$1


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
if [ -f /etc/debian_version ] ; then
        DIST='DEBIAN'
else
    echo ""
    echo "This Installer should be run on a Debian based system"
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

            if [ $(echo "$PY_MAJOR_VERSION < 5" | bc) -eq 1  ] ; then

                echo ""
                echo "Python version below 2.5. Please Upgrade your python."
                echo ""
                exit 1

            fi

            apt-get -y install python-setuptools python-dev build-essential

easy_install virtualenv
easy_install pip

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
