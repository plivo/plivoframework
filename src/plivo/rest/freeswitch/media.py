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
              }


def auth_protect(decorated_func):
    def wrapper(obj):
        if obj._validate_ip_auth():
            return decorated_func(obj)
    wrapper.__name__ = decorated_func.__name__
    wrapper.__doc__ = decorated_func.__doc__
    return wrapper


class CacheErrorHandler(urllib2.HTTPDefaultErrorHandler):
    def http_error_default(self, req, fp, code, msg, headers):
        result = urllib2.HTTPError(req.get_full_url(), code, msg, headers, fp)
        result.status = code
        return result


class UnsupportedResourceFormat(Exception):
    pass


class ResourceCache(object):
    """Uses redis cache as a backend for storing info on cached files.
    """
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.host = redis_host
        self.port = redis_port
        self.db = redis_db
        self.opener = urllib2.build_opener(CacheErrorHandler())
        self._connect()

    def _connect(self):
        self._cx = redis.Redis(host=self.host, port=self.port, db=self.db)
        return True

    def get_resource_params(self, url):
        resource_key = self.get_resource_key(url)
        try:
            if self._cx.sismember("resource_key", resource_key):
                resource_type = self._cx.hget("resource_key:%s" % resource_key, "resource_type")
                etag = self._cx.hget("resource_key:%s" % resource_key, "etag")
                last_modified = self._cx.hget("resource_key:%s" % resource_key, "last_modified")
                return resource_key, resource_type, etag, last_modified
            else:
                return None, None, None, None
        except redis.exceptions.ConnectionError, e:
            if not self._connect():
                raise e

    def update_resource_params(self, resource_key, resource_type, etag, last_modified, buffer):
        if etag is None:
            etag = ""
        if last_modified is None:
            last_modified = ""
        try:
            if not self._cx.sismember("resource_key", resource_key):
                self._cx.sadd("resource_key", resource_key)
            self._cx.hset("resource_key:%s" % resource_key, "resource_type", resource_type)
            self._cx.hset("resource_key:%s" % resource_key, "etag", etag)
            self._cx.hset("resource_key:%s" % resource_key, "last_modified", last_modified)
            self._cx.hset("resource_key:%s" % resource_key, "file", buffer)
        except redis.exceptions.ConnectionError, e:
            if not self._connect():
                raise e

    def delete_resource(self, resource_key):
        try:
            if self._cx.sismember("resource_key", resource_key):
                self._cx.srem("resource_key", resource_key)
                self._cx.delete("resource_key:%s" % resource_key)
        except redis.exceptions.ConnectionError, e:
            if not self._connect():
                raise e

    def cache_resource(self, url):
        request = urllib2.Request(url)
        user_agent = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/14.0.835.35 Safari/535.1'
        request.add_header('User-Agent', user_agent)
        first_time = self.opener.open(request)
        try:
            resource_type = MIME_TYPES[first_time.headers.get('Content-Type')]
        except KeyError:
            raise UnsupportedResourceFormat("Resource format not supported")
        etag = first_time.headers.get('ETag')
        last_modified = first_time.headers.get('Last-Modified')
        response = urllib2.urlopen(request)
        resource_key = self.get_resource_key(url)
        stream = response.read()
        self.update_resource_params(resource_key, resource_type, etag, last_modified, stream)
        return stream, resource_type

    def get_stream(self, resource_key):
        try:
            stream = self._cx.hget("resource_key:%s" % resource_key, "file")
            resource_type = self._cx.hget("resource_key:%s" % resource_key, "resource_type")
            return stream, resource_type
        except redis.exceptions.ConnectionError, e:
            if not self._connect():
                raise e

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
        
        #second_try = self.opener.open(request)
        try:
            second_try = urllib2.urlopen(request)
        except urllib2.HTTPError, e:
            #if second_try.status == 304:
            if e.code == 304:
                return no_change
        return True, etag, last_modified


def get_resource(socket, url):
    full_file_name = url
    stream = ''
    resource_type = None

    if socket.cache is not None:
        # don't do cache if not a remote file
        if not full_file_name[:7].lower() == "http://" \
            and not full_file_name[:8].lower() == "https://":
            return (full_file_name, stream, resource_type)

        rk = socket.cache.get_resource_key(url)
        socket.log.debug("Resource key %s" % rk)
        #~socket.cache.delete_resource(rk)
        try:
            resource_key, resource_type, etag, last_modified = socket.cache.get_resource_params(url)
            if resource_key is None:
                socket.log.info("Resource not found in cache. Download and Cache")
                try:
                    stream, resource_type = socket.cache.cache_resource(url)
                except UnsupportedResourceFormat:
                    socket.log.error("Ignoring Unsupported Audio File at - %s" % url)
            else:
                socket.log.debug("Resource found in Cache. Check if source is newer")
                updated, new_etag, new_last_modified = socket.cache.is_resource_updated(url, etag, last_modified)
                if not updated:
                    socket.log.debug("Source file same. Use Cached Version")
                    #file_name = "%s.%s" % (resource_key, resource_type)
                    stream, resource_type = socket.cache.get_stream(resource_key)
                else:
                    socket.log.debug("Source file updated. Download and Cache")
                    try:
                        stream, resource_type = socket.cache.cache_resource(url)
                    except UnsupportedResourceFormat:
                        socket.log.error("Ignoring Unsupported Audio File at - %s" % url)
        except Exception, e:
            socket.log.error("Cache Error !")
            [ socket.log.debug('Cache Error: %s' % line) for line in \
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



class PlivoMediaApi(object):
    _config = None
    log = None

    def _validate_ip_auth(self):
        """Verify request is from allowed ips
        """
        allowed_ips = self._config.get('media_server', 'ALLOWED_IPS', default='')
        if not allowed_ips:
            return True
        for ip in allowed_ips.split(','):
            if ip.strip() == request.remote_addr.strip():
                return True
        raise Unauthorized("IP Auth Failed")

    @auth_protect
    def index(self):
        message = """
        Welcome to Plivo - http://www.plivo.org/<br>
        <br>
        Plivo is a Communication Framework to rapidly build Voice based apps,
        to make and receive calls, using your existing web development skills
        and infrastructure.<br>
        <br>
        <br>
        For further information please visit our website :
        http://www.plivo.org/ <br>
        <br>
        <br>
        """
        return message

    @auth_protect
    def do_media(self):
        url = get_http_param(request, "url")
        if not url:
            self.log.debug("No Url")
            return "NO URL", 404
        self.log.debug("Url is %s" % str(url))
        file_path, stream, resource_type = get_resource(self, url)
        if not stream:
            self.log.debug("Url %s: no stream" % str(url))
            return "NO STREAM", 404
        if resource_type == 'mp3':
            _type = 'audio/mp3'
        elif resource_type == 'wav':
            _type = 'audio/wav'
        else:
            self.log.debug("Url %s: not supported format" % str(url))
            return "NOT SUPPORTED FORMAT", 404
        self.log.debug("Url %s: stream found" % str(url))
        return flask.Response(response=stream, status=200, 
                              headers=None, mimetype=_type, 
                              content_type=_type, 
                              direct_passthrough=False)

    @auth_protect
    def do_media_type(self):
        url = get_http_param(request, "url")
        if not url:
            self.log.debug("No Url")
            return "NO URL", 404
        self.log.debug("Url is %s" % str(url))
        file_path, stream, resource_type = get_resource(self, url)
        if not resource_type:
            self.log.debug("Url %s: no type" % str(url))
            return "NO TYPE", 404
        self.log.debug("Url %s: type is %s" % (str(url), str(resource_type)))
        return flask.jsonify(MediaType=resource_type)

        
