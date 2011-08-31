# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

from plivo.rest.freeswitch.media import PlivoMediaApi


URLS = {
        # API Index
        '/': (PlivoMediaApi.index, ['GET']),
        # API to get cache url content
        '/Media/': (PlivoMediaApi.do_media, ['GET']),
        # API to get cache url type
        '/MediaType/': (PlivoMediaApi.do_media_type, ['GET']),
       }
