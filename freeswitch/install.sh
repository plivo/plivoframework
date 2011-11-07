#!/bin/bash

# FreeSWITCH Installation script for CentOS 5.5/5.6
# and Debian based distros (Debian 5.0 , Ubuntu 10.04 and above)
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


FS_CONF_PATH=https://github.com/plivo/plivo/raw/master/freeswitch
FS_GIT_REPO=git://git.freeswitch.org/freeswitch.git
FS_INSTALLED_PATH=/usr/local/freeswitch

#####################################################
FS_BASE_PATH=/usr/src/
#####################################################

CURRENT_PATH=$PWD

# Identify Linux Distribution
if [ -f /etc/debian_version ] ; then
    DIST="DEBIAN"
elif [ -f /etc/redhat-release ] ; then
    DIST="CENTOS"
else
    echo ""
    echo "This Installer should be run on a CentOS or a Debian based system"
    echo ""
    exit 1
fi


clear
echo ""
echo "FreeSWITCH will be installed in $FS_INSTALLED_PATH"
echo "Press any key to continue or CTRL-C to exit"
echo ""
read INPUT


echo "Setting up Prerequisites and Dependencies for FreeSWITCH"
case $DIST in
    'DEBIAN')
        apt-get -y update
        apt-get -y install autoconf automake autotools-dev binutils bison build-essential cpp curl flex g++ gcc git-core libaudiofile-dev libc6-dev libdb-dev libexpat1 libgdbm-dev libgnutls-dev libmcrypt-dev libncurses5-dev libnewt-dev libpcre3 libpopt-dev libsctp-dev libsqlite3-dev libtiff4 libtiff4-dev libtool libx11-dev libxml2 libxml2-dev lksctp-tools lynx m4 make mcrypt ncftp nmap openssl sox sqlite3 ssl-cert ssl-cert unixodbc-dev unzip zip zlib1g-dev zlib1g-dev libjpeg-dev libssl-dev sox
        ;;
    'CENTOS')
        yum -y update

        VERS=$(cat /etc/redhat-release |cut -d' ' -f4 |cut -d'.' -f1)

        COMMON_PKGS=" autoconf automake bzip2 cpio curl curl-devel curl-devel expat-devel fileutils gcc-c++ gettext-devel gnutls-devel libjpeg-devel libogg-devel libtiff-devel libtool libvorbis-devel make ncurses-devel nmap openssl openssl-devel openssl-devel perl patch unixODBC unixODBC-devel unzip wget zip zlib zlib-devel bison sox"
        if [ "$VERS" = "6" ]
        then
            yum -y install $COMMON_PKGS git

        else
            yum -y install $COMMON_PKGS
            #install the RPMFORGE Repository
            if [ ! -f /etc/yum.repos.d/rpmforge.repo ]
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
        ;;
esac

# Install FreeSWITCH
cd $FS_BASE_PATH
git clone $FS_GIT_REPO
cd $FS_BASE_PATH/freeswitch
sh bootstrap.sh && ./configure
[ -f modules.conf ] && cp modules.conf modules.conf.bak
sed -i \
-e "s/#applications\/mod_curl/applications\/mod_curl/g" \
-e "s/#asr_tts\/mod_flite/asr_tts\/mod_flite/g" \
-e "s/#asr_tts\/mod_pocketsphinx/asr_tts\/mod_pocketsphinx/g" \
-e "s/#asr_tts\/mod_tts_commandline/asr_tts\/mod_tts_commandline/g" \
-e "s/#formats\/mod_shout/formats\/mod_shout/g" \
-e "s/#endpoints\/mod_dingaling/endpoints\/mod_dingaling/g" \
-e "s/#formats\/mod_shell_stream/formats\/mod_shell_stream/g" \
-e "s/#applications\/mod_soundtouch/applications\/mod_soundtouch/g" \
-e "s/#say\/mod_say_de/say\/mod_say_de/g" \
-e "s/#say\/mod_say_es/say\/mod_say_es/g" \
-e "s/#say\/mod_say_fr/say\/mod_say_fr/g" \
-e "s/#say\/mod_say_it/say\/mod_say_it/g" \
-e "s/#say\/mod_say_nl/say\/mod_say_nl/g" \
-e "s/#say\/mod_say_ru/say\/mod_say_ru/g" \
-e "s/#say\/mod_say_zh/say\/mod_say_zh/g" \
-e "s/#say\/mod_say_hu/say\/mod_say_hu/g" \
-e "s/#say\/mod_say_th/say\/mod_say_th/g" \
modules.conf
make && make install && make sounds-install && make moh-install

# Enable FreeSWITCH modules
cd $FS_INSTALLED_PATH/conf/autoload_configs/
[ -f modules.conf.xml ] && cp modules.conf.xml modules.conf.xml.bak
sed -i -r \
-e "s/<\!--\s?<load module=\"mod_xml_curl\"\/>\s?-->/<load module=\"mod_xml_curl\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_xml_cdr\"\/>\s?-->/<load module=\"mod_xml_cdr\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_dingaling\"\/>\s?-->/<load module=\"mod_dingaling\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_shout\"\/>\s?-->/<load module=\"mod_shout\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_tts_commandline\"\/>\s?-->/<load module=\"mod_tts_commandline\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_flite\"\/>\s?-->/<load module=\"mod_flite\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_pocketsphinx\"\/>\s?-->/<load module=\"mod_pocketsphinx\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_soundtouch\"\/>\s?-->/<load module=\"mod_soundtouch\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_say_ru\"\/>\s?-->/<load module=\"mod_say_ru\"\/>/g" \
-e "s/<\!--\s?<load module=\"mod_say_zh\"\/>\s?-->/<load module=\"mod_say_zh\"\/>/g" \
-e 's/mod_say_zh.*$/&\n    <load module="mod_say_de"\/>\n    <load module="mod_say_es"\/>\n    <load module="mod_say_fr"\/>\n    <load module="mod_say_it"\/>\n    <load module="mod_say_nl"\/>\n    <load module="mod_say_hu"\/>\n    <load module="mod_say_th"\/>/' \
modules.conf.xml


#Configure Dialplan
cd $FS_INSTALLED_PATH/conf/dialplan/

# Place Plivo Default Dialplan in FreeSWITCH
[ -f default.xml ] && mv default.xml default.xml.bak
wget --no-check-certificate $FS_CONF_PATH/conf/default.xml -O default.xml

# Place Plivo Public Dialplan in FreeSWITCH
[ -f public.xml ] && mv public.xml public.xml.bak
wget --no-check-certificate $FS_CONF_PATH/conf/public.xml -O public.xml

#Configure Conference @plivo profile
cd $FS_INSTALLED_PATH/conf/autoload_configs/
[ -f conference.conf.xml ] && mv conference.conf.xml conference.conf.xml.bak
wget --no-check-certificate $FS_CONF_PATH/conf/conference.conf.xml -O conference.conf.xml

cd $CURRENT_PATH

# Install Complete
#clear
echo ""
echo ""
echo ""
echo "**************************************************************"
echo "Congratulations, FreeSWITCH is now installed at '$FS_INSTALLED_PATH'"
echo "**************************************************************"
echo
echo "* To Start FreeSWITCH in foreground :"
echo "    '$FS_INSTALLED_PATH/bin/freeswitch'"
echo
echo "* To Start FreeSWITCH in background :"
echo "    '$FS_INSTALLED_PATH/bin/freeswitch -nc'"
echo
echo "**************************************************************"
echo ""
echo ""
exit 0
