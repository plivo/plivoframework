# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

import base64
import ConfigParser
from hashlib import sha1
import hmac
import httplib
import os
import os.path
import re
import redis
import urllib
import urllib2
import urlparse
import uuid
import ujson as json
from werkzeug.datastructures import MultiDict

# remove depracated warning in python2.6
try:
    from hashlib import md5 as _md5
except ImportError:
    import md5
    _md5 = md5.new


MIME_TYPES = {'audio/mpeg': 'mp3',
              'audio/x-wav': 'wav',
              }


def get_substring(start_char, end_char, data):
    if data is None or not data:
        return ""
    start_pos = data.find(start_char)
    if start_pos < 0:
        return ""
    end_pos = data.find(end_char)
    if end_pos < 0:
        return ""
    return data[start_pos+len(start_char):end_pos]


def url_exists(url):
    p = urlparse.urlparse(url)
    if p[4]:
        extra_string = "%s?%s" %(p[2], p[4])
    else:
        extra_string = p[2]
    try:
        connection = httplib.HTTPConnection(p[1])
        connection.request('HEAD', extra_string)
        response = connection.getresponse()
        connection.close()
        return response.status == httplib.OK
    except Exception:
        return False


def file_exists(filepath):
    return os.path.isfile(filepath)

def normalize_url_space(url):
    return url.strip().replace(' ', '+')

def get_post_param(request, key):
    try:
        return request.form[key]
    except MultiDict.KeyError:
        return ""


def is_valid_url(value):
    regex = re.compile(
      r'^(?:http|ftp)s?://'  # http:// or https://
      r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
      r'localhost|'  # localhost
      r'http://127.0.0.1|'  # 127.0.0.1
      r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or ip
      r'(?::\d+)?'  # optional port
      r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    # If no domain starters we assume its http and add it
    if not value.startswith('http://') and not value.startswith('https://') \
        and not value.startswith('ftp://'):
        value = ''.join(['http://', value])

    if regex.search(value):
        return True
    # Trivial case failed. Try for possible IDN domain
    if value:
        scheme, netloc, path, query, fragment = urlparse.urlsplit(value)
        try:
            netloc = netloc.encode('idna')  # IDN -> ACE
        except UnicodeError:  # invalid domain part
            return False
        url = urlparse.urlunsplit((scheme, netloc, path, query, fragment))
        if regex.search(url):
            return True

    return False


class HTTPErrorProcessor(urllib2.HTTPErrorProcessor):
    def https_response(self, request, response):
        code, msg, hdrs = response.code, response.msg, response.info()
        if code >= 300:
            response = self.parent.error(
                'http', request, response, code, msg, hdrs)
        return response


class HTTPUrlRequest(urllib2.Request):
    def get_method(self):
        if getattr(self, 'http_method', None):
            return self.http_method
        return urllib2.Request.get_method(self)


class HTTPRequest:
    """Helper class for preparing HTTP requests.
    """
    USER_AGENT = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/14.0.835.35 Safari/535.1'

    def __init__(self, auth_id='', auth_token=''):
        """initialize a object

        auth_id: Plivo SID/ID
        auth_token: Plivo token

        returns a HTTPRequest object
        """
        self.auth_id = auth_id
        self.auth_token = auth_token
        self.opener = None

    def _build_get_uri(self, uri, params):
        if params:
            if uri.find('?') > 0:
                if uri[-1] != '&':
                    uri += '&'
                uri = uri + urllib.urlencode(params)
            else:
                uri = uri + '?' + urllib.urlencode(params)
        return uri

    def _prepare_http_request(self, uri, params, method='POST'):
        # install error processor to handle HTTP 201 response correctly
        if self.opener == None:
            self.opener = urllib2.build_opener(HTTPErrorProcessor)
            urllib2.install_opener(self.opener)

        if method and method == 'GET':
            uri = self._build_get_uri(uri, params)
            request = HTTPUrlRequest(uri)
        else:
            request = HTTPUrlRequest(uri, urllib.urlencode(params))
            if method and (method == 'DELETE' or method == 'PUT'):
                request.http_method = method

        request.add_header('User-Agent', self.USER_AGENT)

        # append the POST variables sorted by key to the uri
        # and transform None to '' and unicode to string
        s = uri
        for k, v in sorted(params.items()):
            if k:
                if v is None:
                    x = ''
                else:
                    x = str(v)
                params[k] = x
                s += k + x

        # compute signature and compare signatures
        signature =  base64.encodestring(hmac.new(self.auth_token, s, sha1).\
                                                            digest()).strip()
        request.add_header("X-PLIVO-SIGNATURE", "%s" % signature)

        # be sure 100 continue is disabled
        request.add_header("Expect", "")
        return request

    def fetch_response(self, uri, params={}, method='POST'):
        if not method in ('GET', 'POST'):
            raise NotImplementedError('HTTP %s method not implemented' \
                                                            % method)
        # Read all params in the query string and include them in params
        query = urlparse.urlsplit(uri)[3]
        args = query.split('&')
        for arg in args:
            try:
                k, v = arg.split('=')
                params[k] = v
            except ValueError:
                pass

        request = self._prepare_http_request(uri, params, method)
        response = urllib2.urlopen(request).read()
        return response


def get_config(filename):
    config = ConfigParser.SafeConfigParser()
    config.read(filename)
    return config


def get_json_config(url):
    config = HTTPJsonConfig()
    config.read(url)
    return config


def get_conf_value(config, section, key):
    try:
        value = config.get(section, key)
        return str(value)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        return ""


class HTTPJsonConfig(object):
    """
    Json Config Format is :
    {'section1':{'key':'value', ..., 'keyN':'valueN'},
     'section2 :{'key':'value', ..., 'keyN':'valueN'},
     ...
     'sectionN :{'key':'value', ..., 'keyN':'valueN'},
    }
    """
    def __init__(self):
        self.jdata = None

    def read(self, url):
        req = HTTPRequest()
        data = req.fetch_response(url, params={}, method='POST')
        self.jdata = json.loads(data)

    def get(self, section, key):
        try:
            val = self.jdata[section][key]
            if val is None:
                return ""
            return str(val)
        except KeyError:
            return ""

    def dumps(self):
        return self.jdata


class PlivoConfig(object):
    def __init__(self, source):
        self._cfg = ConfigParser.SafeConfigParser()
        self._cfg.optionxform = str # make case sensitive
        self._source = source
        self._json_cfg = None
        self._json_source = None
        self._cache = {}

    def _set_cache(self):
        if self._json_cfg:
            self._cache = dict(self._json_cfg.dumps())
        else:
            self._cache = {}
            for section in self._cfg.sections():
                self._cache[section] = {}
                for var, val in self._cfg.items(section):
                    self._cache[section][var] = val

    def read(self):
        self._cfg.read(self._source)
        try:
            self._json_source = self._cfg.get('common', 'JSON_CONFIG_URL')
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            self._json_source = None
        if self._json_source:
            self._json_cfg = HTTPJsonConfig()
            self._json_cfg.read(self._json_source)
        else:
            self._json_source = None
            self._json_cfg = None
        self._set_cache()

    def dumps(self):
        return self._cache

    def __getitem__(self, section):
        return self._cache[section]

    def get(self, section, key, **kwargs):
        try:
            return self._cache[section][key]
        except KeyError, e:
            try:
                d = kwargs['default']
                return d
            except KeyError:
                raise e

    def reload(self):
        self.read()


class CacheErrorHandler(urllib2.HTTPDefaultErrorHandler):
    def http_error_default(self, req, fp, code, msg, headers):
        result = urllib2.HTTPError(req.get_full_url(), code, msg, headers, fp)
        result.status = code
        return result


class ResourceCache(object):
    """Uses redis cache as a backend for storing info on cached files.
    """
    def __init__(self, cache_path="plivocache/", redis_host='localhost', redis_port=6379, redis_db=0):
        self.cache = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        root_path = os.path.abspath(os.path.dirname(__file__))
        self.cache_path = os.path.join(root_path, cache_path)
        if not os.path.exists(cache_path):
            os.makedirs(self.cache_path)
        self.opener = urllib2.build_opener(CacheErrorHandler())

    def get_resource_params(self, url):
        resource_key = self.get_resource_key(url)
        if self.cache.sismember("resource_key", resource_key):
            resource_type = self.cache.hget("resource_key:%s" % resource_key, "resource_type")
            etag = self.cache.hget("resource_key:%s" % resource_key, "etag")
            last_modified = self.cache.hget("resource_key:%s" % resource_key, "last_modified")
            return resource_key, resource_type, etag, last_modified
        else:
            return None, None, None, None

    def update_resource_params(self, resource_key, resource_type, etag, last_modified):
        if etag is None:
            etag = ""
        if last_modified is None:
            last_modified = ""
        self.cache.sadd("resource_key", resource_key)
        self.cache.hset("resource_key:%s" % resource_key, "resource_type", resource_type)
        self.cache.hset("resource_key:%s" % resource_key, "etag", etag)
        self.cache.hset("resource_key:%s" % resource_key, "last_modified", last_modified)

    def delete_resource(self, resource_key):
        if self.cache.sismembers("resource_key", resource_key):
            self.cache.srem("resource_key", resource_key)
            self.cache.delete("resource_key:%s" % resource_key)

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
        local_name = "%s.%s" % (resource_key, resource_type)
        cache_full_path = os.path.join(self.cache_path, local_name)
        f = open(cache_full_path, 'wb')
        f.write(response.read())
        f.close()
        self.update_resource_params(resource_key, resource_type, etag, last_modified)
        return cache_full_path

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

        second_try = self.opener.open(request)
        if second_try.status == 304:
            return no_change

        return True, etag, last_modified


def get_resource(socket, url):
    full_file_name = url
    if socket.cache is not None:
        rk = socket.cache.get_resource_key(url)
        socket.log.debug("Resource key %s" %rk)
        #~socket.cache.delete_resource(rk)
        resource_key, resource_type, etag, last_modified = socket.cache.get_resource_params(url)
        if resource_key is None:
            socket.log.info("Resource not found in cache. Download and Cache")
            try:
                full_file_name = socket.cache.cache_resource(url)
            except UnsupportedResourceFormat:
                socket.log.error("Ignoring Unsupported Audio File at - %s" % url)
        else:
            socket.log.debug("Resource found in Cache. Check if source is newer")
            updated, new_etag, new_last_modified = socket.cache.is_resource_updated(url, etag, last_modified)
            if not updated:
                socket.log.debug("Source file same. Use Cached Version")
                file_name = "%s.%s" % (resource_key, resource_type)
                full_file_name = os.path.join(socket.cache.cache_path, file_name)
            else:
                socket.log.debug("Source file updated. Download and Cache")
                try:
                    full_file_name = socket.cache.cache_resource(url)
                except UnsupportedResourceFormat:
                    socket.log.error("Ignoring Unsupported Audio File at - %s" % url)
    else:
        if full_file_name[:7].lower() == "http://":
            audio_path = full_file_name[7:]
        elif full_file_name[:8].lower() == "https://":
            audio_path = full_file_name[8:]
        elif full_file_name[:6].lower() == "ftp://":
            audio_path = full_file_name[6:]

        full_file_name = "shout://%s" % audio_path

    return full_file_name
