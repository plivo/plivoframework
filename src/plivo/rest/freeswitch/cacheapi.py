# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

import base64
import re
import uuid
import os
import os.path
from datetime import datetime
import urllib
import urllib2
import urlparse
import traceback

import redis
import redis.exceptions
import flask
from flask import request
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import Unauthorized

# remove depracated warning in python2.6
try:
    from hashlib import md5 as _md5
except ImportError:
    import md5
    _md5 = md5.new

from plivo.rest.freeswitch.helpers import is_valid_url, get_conf_value, \
                                            get_post_param, get_http_param

MIME_TYPES = {'audio/mpeg': 'mp3',
              'audio/x-wav': 'wav',
              'application/srgs+xml': 'grxml',
              'application/x-jsgf': 'jsgf',
             }



def ip_protect(decorated_func):
    def wrapper(obj):
        if obj._validate_ip_auth():
            return decorated_func(obj)
    wrapper.__name__ = decorated_func.__name__
    wrapper.__doc__ = decorated_func.__doc__
    return wrapper



class UnsupportedResourceFormat(Exception):
    pass


class ResourceCache(object):
    """Uses redis cache as a backend for storing cached files infos and datas.
    """
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0, redis_pw=None, proxy_url=None):
        self.host = redis_host
        self.port = redis_port
        self.db = redis_db
        self.pw = redis_pw
        self.proxy_url = proxy_url

    def get_cx(self):
        return redis.Redis(host=self.host, port=self.port, db=self.db,
                            socket_timeout=5.0, password=self.pw)

    def get_resource_params(self, url):
        resource_key = self.get_resource_key(url)
        cx = self.get_cx()
        if cx.sismember("resource_key", resource_key):
            resource_type = cx.hget("resource_key:%s" % resource_key, "resource_type")
            etag = cx.hget("resource_key:%s" % resource_key, "etag")
            last_modified = cx.hget("resource_key:%s" % resource_key, "last_modified")
            return resource_key, resource_type, etag, last_modified
        else:
            return None, None, None, None

    def update_resource_params(self, resource_key, resource_type, etag, last_modified, buffer):
        if etag is None:
            etag = ""
        if last_modified is None:
            last_modified = ""
        cx = self.get_cx()
        if not cx.sismember("resource_key", resource_key):
            cx.sadd("resource_key", resource_key)
        cx.hset("resource_key:%s" % resource_key, "resource_type", resource_type)
        cx.hset("resource_key:%s" % resource_key, "etag", etag)
        cx.hset("resource_key:%s" % resource_key, "last_modified", last_modified)
        cx.hset("resource_key:%s" % resource_key, "file", buffer)
        cx.hset("resource_key:%s" % resource_key, "last_update_time", str(datetime.now().strftime('%s')))

    def delete_resource(self, resource_key):
        cx = self.get_cx()
        if cx.sismember("resource_key", resource_key):
            cx.srem("resource_key", resource_key)
            cx.delete("resource_key:%s" % resource_key)

    def cache_resource(self, url):
        if self.proxy_url is not None:
            proxy = urllib2.ProxyHandler({'http': self.proxy_url})
            opener = urllib2.build_opener(proxy)
            urllib2.install_opener(opener)
        request = urllib2.Request(url)
        user_agent = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/14.0.835.35 Safari/535.1'
        request.add_header('User-Agent', user_agent)
        handler = urllib2.urlopen(request)
        try:
            resource_type = MIME_TYPES[handler.headers.get('Content-Type')]
            if not resource_type:
                raise UnsupportedResourceFormat("Resource format not found")
        except KeyError:
            raise UnsupportedResourceFormat("Resource format not supported")
        etag = handler.headers.get('ETag')
        last_modified = handler.headers.get('Last-Modified')
        resource_key = self.get_resource_key(url)
        stream = handler.read()
        self.update_resource_params(resource_key, resource_type, etag, last_modified, stream)
        return stream, resource_type

    def get_stream(self, resource_key):
        stream = self.get_cx().hget("resource_key:%s" % resource_key, "file")
        resource_type = self.get_cx().hget("resource_key:%s" % resource_key, "resource_type")
        return stream, resource_type

    def get_resource_key(self, url):
        return base64.urlsafe_b64encode(_md5(url).digest())

    def is_resource_updated(self, url, etag, last_modified):
        no_change = (False, None, None)
        # if no ETag, then check for 'Last-Modified' header
        if etag is not None and etag != "":
            request = urllib2.Request(url)
            request.add_header('If-None-Match', etag)
        elif last_modified is not None and last_modified != "":
            request = urllib2.Request(url)
            request.add_header('If-Modified-Since', last_modified)
        else:
            return no_change
        try:
            second_try = urllib2.urlopen(request)
        except urllib2.HTTPError, e:
            # if http code is 304, no change
            if e.code == 304:
                return no_change
        return True, etag, last_modified


def get_resource_type(server, url):
    resource_type = None
    resource_key, resource_type, etag, last_modified = server.cache.get_resource_params(url)
    if resource_type:
        return resource_type
    full_file_name, stream, resource_type = get_resource(server, url)
    return resource_type

def get_resource(server, url):
    if not url:
        return url
    full_file_name = url
    stream = ''
    resource_type = None

    if server.cache is not None:
        # don't do cache if not a remote file
        if not full_file_name[:7].lower() == "http://" \
            and not full_file_name[:8].lower() == "https://":
            return (full_file_name, stream, resource_type)

        rk = server.cache.get_resource_key(url)
        server.log.debug("Cache -- Resource key %s for %s" % (rk, url))
        try:
            resource_key, resource_type, etag, last_modified = server.cache.get_resource_params(url)
            if resource_key is None:
                server.log.info("Cache -- %s not found. Downloading" % url)
                try:
                    stream, resource_type = server.cache.cache_resource(url)
                except UnsupportedResourceFormat:
                    server.log.error("Cache -- Ignoring Unsupported File at - %s" % url)
            else:
                server.log.debug("Cache -- Checking if %s source is newer" % url)
                updated, new_etag, new_last_modified = server.cache.is_resource_updated(url, etag, last_modified)
                if not updated:
                    server.log.debug("Cache -- Using Cached %s" % url)
                    stream, resource_type = server.cache.get_stream(resource_key)
                else:
                    server.log.debug("Cache -- Updating Cached %s" % url)
                    try:
                        stream, resource_type = server.cache.cache_resource(url)
                    except UnsupportedResourceFormat:
                        server.log.error("Cache -- Ignoring Unsupported File at - %s" % url)
        except Exception, e:
            server.log.error("Cache -- Failure !")
            [ server.log.debug('Cache -- Error: %s' % line) for line in \
                            traceback.format_exc().splitlines() ]

    if stream:
        return (full_file_name, stream, resource_type)

    if full_file_name[:7].lower() == "http://":
        audio_path = full_file_name[7:]
        full_file_name = "shout://%s" % audio_path
    elif full_file_name[:8].lower() == "https://":
        audio_path = full_file_name[8:]
        full_file_name = "shout://%s" % audio_path

    return (full_file_name, stream, resource_type)



class PlivoCacheApi(object):
    _config = None
    log = None
    allowed_ips = []

    def _validate_ip_auth(self):
        """Verify request is from allowed ips
        """
        if not self.allowed_ips:
            return True
        remote_ip = request.remote_addr.strip()
        if remote_ip in self.allowed_ips:
            return True
        self.log.debug("IP Auth Failed: remote ip %s not in %s" % (remote_ip, str(self.allowed_ips)))
        raise Unauthorized("IP Auth Failed")

    @ip_protect
    def index(self):
        return "OK"

    @ip_protect
    def do_cache(self):
        url = get_http_param(request, "url")
        if not url:
            self.log.debug("No Url")
            return "NO URL", 404
        self.log.debug("Url is %s" % str(url))
        try:
            file_path, stream, resource_type = get_resource(self, url)
            if not stream:
                self.log.debug("Url %s: no stream" % str(url))
                return "NO STREAM", 404
            if resource_type == 'mp3':
                _type = 'audio/mp3'
            elif resource_type == 'wav':
                _type = 'audio/wav'
            elif resource_type == 'grxml':
                _type = 'application/srgs+xml'
            elif resource_type == 'jsgf':
                _type = 'application/x-jsgf'
            else:
                self.log.debug("Url %s: not supported format" % str(url))
                return "NOT SUPPORTED FORMAT", 404
            self.log.debug("Url %s: stream found" % str(url))
            return flask.Response(response=stream, status=200,
                                  headers=None, mimetype=_type,
                                  content_type=_type,
                                  direct_passthrough=False)
        except Exception, e:
            self.log.error("/Cache/ Error: %s" % str(e))
            [ self.log.error('/Cache/ Error: %s' % line) for line in \
                            traceback.format_exc().splitlines() ]
            raise e

    @ip_protect
    def do_cache_type(self):
        url = get_http_param(request, "url")
        if not url:
            self.log.debug("No Url")
            return "NO URL", 404
        self.log.debug("Url is %s" % str(url))
        try:
            resource_type = get_resource_type(self, url)
            if not resource_type:
                self.log.debug("Url %s: no type" % str(url))
                return "NO TYPE", 404
            self.log.debug("Url %s: type is %s" % (str(url), str(resource_type)))
            return flask.jsonify(CacheType=resource_type)
        except Exception, e:
            self.log.error("/CacheType/ Error: %s" % str(e))
            [ self.log.error('/CacheType/ Error: %s' % line) for line in \
                            traceback.format_exc().splitlines() ]
            raise e

    @ip_protect
    def do_reload_config(self):
        try:
            self.reload()
            return flask.jsonify(Success=True, Message="ReloadConfig done")
        except Exception, e:
            self.log.error("/ReloadConfig/ Error: %s" % str(e))
            [ self.log.error('/ReloadConfig/ Error: %s' % line) for line in \
                            traceback.format_exc().splitlines() ]
            raise e

