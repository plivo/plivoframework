#!/bin/bash

# FreeSWITCH Installation script for CentOS 5.5/5.6
# and Debian based distros (Debian 5.0 , Ubuntu 10.04 and above)
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


FS_CONF_PATH=https://github.com/plivo/plivo/raw/master/freeswitch/conf
FS_GIT_REPO=git://git.freeswitch.org/freeswitch.git
FS_INSTALLED_PATH=/usr/local/freeswitch

#####################################################
FS_BASE_PATH = /usr/src/
#####################################################

PWD = `pwd`


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
echo "FreeSWITCH will be installed at "$FS_BASE_PATH""
echo "Press any key to continue or CTRL-C to exit"
echo ""
read INPUT


echo "Setting up Prerequisites and Dependencies for FreeSWITCH"
case $DIST in
        'DEBIAN')
            apt-get -y update
            apt-get -y upgrade
            apt-get -y install autoconf automake autotools-dev binutils bison build-essential cpp curl flex g++ gcc git-core libaudiofile-dev libc6-dev libdb-dev libexpat1 libgdbm-dev libgnutls-dev libmcrypt-dev libncurses5-dev libnewt-dev libpcre3 libpopt-dev libsctp-dev libsqlite3-dev libtiff4 libtiff4-dev libtool libx11-dev libxml2 libxml2-dev lksctp-tools lynx m4 make mcrypt ncftp nmap openssl sox sqlite3 ssl-cert ssl-cert unixodbc-dev unzip zip zlib1g-dev zlib1g-dev

        ;;
        'CENTOS')
            sudo yum -y update
            yum -y install autoconf automake bzip2 cpio curl curl-devel curl-devel expat-devel fileutils gcc-c++ gettext-devel git-core gnutls-devel libjpeg-devel libogg-devel libtiff-devel libtool libvorbis-devel make ncurses-devel nmap openssl openssl-devel openssl-devel perl unixODBC unixODBC-devel unzip wget zip zlib zlib-devel

        ;;
esac

# Install FreeSWITCH
cd $FS_BASE_PATH/freeswitch
./bootstrap && ./configure
mv modules.conf modules.conf.bk
wget --no-check-certificate $FS_CONF_PATH/modules.conf
make && make install && make sounds-install && cd-moh-install

# Enable FreeSWITCH for loading
cd $FS_INSTALLED_PATH/conf/autoload_configs/
wget --no-check-certificate $FS_CONF_PATH/modules.conf.xml

cd $FS_INSTALLED_PATH/conf/dialplan/

# Place Plivo Default Dialplan in FreeSWITCH
mv default.xml default.xml.bk
wget --no-check-certificate $FS_CONF_PATH/default.xml

# Place Plivo Public Dialplan in FreeSWITCH
mv public.xml public.xml.bk
wget --no-check-certificate $FS_CONF_PATH/public.xml

cd $PWD

# Install Complete
clear
echo ""
echo ""
echo ""
echo "**************************************************************"
echo "Congratulations, FreeSWITCH is now installed at '$FS_INSTALLED_PATH'"
echo "**************************************************************"
echo
echo "* To Start FreeSWITCH in foreground :"
echo "    '.$FS_INSTALLED_PATH/bin/freeswitch'"
echo
echo "* To Start FreeSWITCH in background :"
echo "    '.$FS_INSTALLED_PATH/bin/freeswitch -nc'"
echo
echo "**************************************************************"
echo ""
echo ""
exit 0
