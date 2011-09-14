# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from plivo.rest.freeswitch.cacheapi import PlivoCacheApi


URLS = {
        # API Index
        '/': (PlivoCacheApi.index, ['GET']),
        # API to get cache url content
        '/Cache/': (PlivoCacheApi.do_cache, ['GET']),
        # API to get cache url type
        '/CacheType/': (PlivoCacheApi.do_cache_type, ['GET']),
        # API to reload cache server config
        '/ReloadConfig/': (PlivoCacheApi.do_reload_config, ['GET', 'POST']),
       }
