#!/bin/bash

# Plivo Installation script for CentOS 5 and 6
# and Debian based distros (Debian 5.0 , Ubuntu 10.04 and above)
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


PLIVO_GIT_REPO=git://github.com/plivo/plivoframework.git
PLIVO_SETUP_SCRIPT=https://raw.github.com/plivo/plivoframework/master/scripts/ez_setup.py


BRANCH=$2
if [ ! $BRANCH ]; then
    BRANCH=master
fi

#####################################################
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin
PLIVO_ENV=$1

LAST_PYTHON_VERSION=2.7.2

# Check if Install Directory Present
if [ ! $1 ] || [ -z "$1" ] ; then
    echo ""
    echo "Usage: $(basename $0) <Install Directory Path>"
    echo ""
    exit 1
fi

# Set full path
echo "$PLIVO_ENV" |grep '^/' -q && REAL_PATH=$PLIVO_ENV || REAL_PATH=$PWD/$PLIVO_ENV

# Identify Linux Distribution type
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
if [ -d $PLIVO_ENV ] ; then
    echo ""
    echo "$PLIVO_ENV already exists!"
    echo "Press any key to continue to update the existing environment or CTRL-C to exit"
    echo ""
    ACTION='UPDATE'
else
    echo ""
    echo "Plivo Framework will be installed at \"$REAL_PATH\""
    echo "Press any key to continue or CTRL-C to exit"
    echo ""
    ACTION='INSTALL'
fi
read INPUT


declare -i PY_MAJOR_VERSION
declare -i PY_MINOR_VERSION
PY_MAJOR_VERSION=$(python -V 2>&1 |sed -e 's/Python[[:space:]]\+\([0-9]\)\..*/\1/')
PY_MINOR_VERSION=$(python -V 2>&1 |sed -e 's/Python[[:space:]]\+[0-9]\+\.\([0-9]\+\).*/\1/')

if [ $PY_MAJOR_VERSION -ne 2 ] || [ $PY_MINOR_VERSION -lt 4 ]; then
    echo ""
    echo "Need Python version >= 2.4.X to install Plivo"
    echo "Please install a compatible version of python."
    echo ""
    exit 1
fi

echo "Setting up Prerequisites and Dependencies"
case $DIST in
    'DEBIAN')
        DEBIAN_VERSION=$(cat /etc/debian_version |cut -d'.' -f1)
        apt-get -y update
        apt-get -y install autoconf automake autotools-dev binutils bison build-essential cpp curl flex g++ gcc git-core libaudiofile-dev libc6-dev libdb-dev libexpat1 libgdbm-dev libgnutls-dev libmcrypt-dev libncurses5-dev libnewt-dev libpcre3 libpopt-dev libsctp-dev libsqlite3-dev libtiff4 libtiff4-dev libtool libx11-dev libxml2 libxml2-dev lksctp-tools lynx m4 make mcrypt ncftp nmap openssl sox sqlite3 ssl-cert ssl-cert unixodbc-dev unzip zip zlib1g-dev zlib1g-dev libevent-dev
        if [ "$DEBIAN_VERSION" = "5" ]; then
            apt-get -y update
            apt-get -y install git-core python-setuptools python-dev build-essential libreadline5-dev
        else
            apt-get -y update
            apt-get -y install git-core python-setuptools python-dev build-essential
        fi
        if [ $PY_MAJOR_VERSION -eq 2 ] && [ $PY_MINOR_VERSION -lt 6 ]; then
            # Setup Env
            mkdir -p $REAL_PATH/deploy
            DEPLOY=$REAL_PATH/deploy
            cd $DEPLOY
            cd $REAL_PATH/deploy

            # Install Isolated copy of python
		    if [ ! -f $REAL_PATH/bin/python ]; then
			    mkdir source
			    cd source
			    wget http://www.python.org/ftp/python/$LAST_PYTHON_VERSION/Python-$LAST_PYTHON_VERSION.tgz
			    tar -xvf Python-$LAST_PYTHON_VERSION.tgz
			    cd Python-$LAST_PYTHON_VERSION
			    ./configure --prefix=$DEPLOY
			    make && make install
		    fi
            # This is what does all the magic by setting upgraded python
            export PATH=$DEPLOY/bin:$PATH

            # Install easy_install
            cd $DEPLOY/source
            wget --no-check-certificate $PLIVO_SETUP_SCRIPT
            $DEPLOY/bin/python ez_setup.py

            EASY_INSTALL=$(which easy_install)
            $DEPLOY/bin/python $EASY_INSTALL --prefix $DEPLOY virtualenv
            $DEPLOY/bin/python $EASY_INSTALL --prefix $DEPLOY pip
	    else
		    easy_install virtualenv
		    easy_install pip
	    fi
    ;;
    'CENTOS')
        yum -y update
        yum -y install autoconf automake bzip2 cpio curl curl-devel curl-devel expat-devel fileutils gcc-c++ gettext-devel gnutls-devel libjpeg-devel libogg-devel libtiff-devel libtool libvorbis-devel make ncurses-devel nmap openssl openssl-devel openssl-devel perl patch unixODBC unixODBC-devel unzip wget zip zlib zlib-devel python-setuptools python-tools gcc python-devel readline-devel which sox bison libevent-devel
        if [ $PY_MAJOR_VERSION -eq 2 ] && [ $PY_MINOR_VERSION -lt 6 ]; then
            which git &>/dev/null
            if [ $? -ne 0 ]; then
                #install the RPMFORGE Repository
                if [ ! -f /etc/yum.repos.d/rpmforge.repo ];
                then
                    # Install RPMFORGE Repo
                    rpm --import http://apt.sw.be/RPM-GPG-KEY.dag.txt
                    echo '
[rpmforge]
name = Red Hat Enterprise $releasever - RPMforge.net - dag
mirrorlist = http://apt.sw.be/redhat/el5/en/mirrors-rpmforge
enabled = 0
protect = 0
gpgkey = file:///etc/pki/rpm-gpg/RPM-GPG-KEY-rpmforge-dag
gpgcheck = 1
' > /etc/yum.repos.d/rpmforge.repo
                fi
                yum -y --enablerepo=rpmforge install git-core
            fi

            # Setup Env
            mkdir -p $REAL_PATH/deploy
            DEPLOY=$REAL_PATH/deploy
            cd $DEPLOY
            cd $REAL_PATH/deploy

            # Install Isolated copy of python
	    if [ ! -f $REAL_PATH/bin/python ]; then
		    mkdir source
		    cd source
		    wget http://www.python.org/ftp/python/$LAST_PYTHON_VERSION/Python-$LAST_PYTHON_VERSION.tgz
		    tar -xvf Python-$LAST_PYTHON_VERSION.tgz
		    cd Python-$LAST_PYTHON_VERSION
		    ./configure --prefix=$DEPLOY
		    make && make install
	    fi
            # This is what does all the magic by setting upgraded python
            export PATH=$DEPLOY/bin:$PATH

            # Install easy_install
            cd $DEPLOY/source
            wget --no-check-certificate https://github.com/plivo/plivoframework/raw/master/scripts/ez_setup.py
            $DEPLOY/bin/python ez_setup.py

            EASY_INSTALL=$(which easy_install)
            $DEPLOY/bin/python $EASY_INSTALL --prefix $DEPLOY virtualenv
            $DEPLOY/bin/python $EASY_INSTALL --prefix $DEPLOY pip
        else
            yum -y install git-core
            easy_install virtualenv
            easy_install pip
        fi
    ;;
esac


# Setup virtualenv
virtualenv --no-site-packages $REAL_PATH
source $REAL_PATH/bin/activate

# force installation of gevent 1.03a
pip uninstall gevent
pip install -Iv http://gevent.googlecode.com/files/gevent-1.0a3.tar.gz
pip install -e git+${PLIVO_GIT_REPO}@${BRANCH}#egg=plivo



# Check install
if [ ! -f $REAL_PATH/bin/plivo ]; then
    echo
    echo
    echo
    echo "Installation failed !"
    echo
    echo
    echo
    exit 1
fi

clear

# Install configs
CONFIG_OVERWRITE=no
case $ACTION in
    "UPDATE")
        while [ 1 ]; do
            clear
	    echo "Do you want to overwrite the following config files"
	    echo " - $REAL_PATH/etc/plivo/default.conf"
	    echo " - $REAL_PATH/etc/plivo/cache/cache.conf"
	    echo "yes/no ?"
	    read INPUT
	    if [ "$INPUT" = "yes" ]; then
	        CONFIG_OVERWRITE=yes
                break
            elif [ "$INPUT" = "no" ]; then
	        CONFIG_OVERWRITE=no
                break
            fi
        done
    ;;
    "INSTALL")
        CONFIG_OVERWRITE=yes
    ;;
esac

if [ "$CONFIG_OVERWRITE" = "yes" ]; then
    mkdir -p $REAL_PATH/etc/plivo &>/dev/null
    mkdir -p $REAL_PATH/etc/plivo/cache &>/dev/null
    cd $REAL_PATH/src/plivo
    git checkout $BRANCH 
    cp -f $REAL_PATH/src/plivo/src/config/default.conf $REAL_PATH/etc/plivo/default.conf
    cp -f $REAL_PATH/src/plivo/src/config/cache.conf $REAL_PATH/etc/plivo/cache/cache.conf
fi

# Create tmp and plivocache directories
mkdir -p $REAL_PATH/tmp &>/dev/null
mkdir -p $REAL_PATH/tmp/plivocache &>/dev/null

# Post install script
$REAL_PATH/bin/plivo-postinstall &>/dev/null

# Install init scripts
case $DIST in
    "DEBIAN")
        cp -f $REAL_PATH/bin/plivo /etc/init.d/plivo
        cp -f $REAL_PATH/bin/cacheserver /etc/init.d/plivocache
        sed -i "s#/usr/local/plivo#$REAL_PATH#g" /etc/init.d/plivo
        sed -i "s#/usr/local/plivo#$REAL_PATH#g" /etc/init.d/plivocache
        cd /etc/rc2.d
        ln -s /etc/init.d/plivocache S99plivocache
        ln -s /etc/init.d/plivo S99plivo
    ;;
    "CENTOS")
        cp -f $REAL_PATH/src/plivo/src/initscripts/centos/plivo /etc/init.d/plivo
        cp -f $REAL_PATH/src/plivo/src/initscripts/centos/plivocache /etc/init.d/plivocache
        sed -i "s#/usr/local/plivo#$REAL_PATH#g" /etc/init.d/plivo
        sed -i "s#/usr/local/plivo#$REAL_PATH#g" /etc/init.d/plivocache
        chkconfig --add plivo
        chkconfig --add plivocache
    ;;
esac



clear
# Install Complete
echo ""
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
echo "    /etc/init.d/plivo start"
echo
echo "* Configure plivo cache:"
echo "    The config is $REAL_PATH/etc/plivo/cache/cache.conf"
echo "    IMPORTANT: you need to install a redis server for plivo cache server!"
echo "               Check with your sysadmin !"
echo
echo "* To Start Plivo cache server:"
echo "    /etc/init.d/plivocache start"
echo
echo "**************************************************************"
echo ""
echo ""
echo "Visit http://www.plivo.org for documentation and examples"
exit 0
