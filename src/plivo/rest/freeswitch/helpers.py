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
import urllib
import urllib2
import urlparse
import uuid
import traceback

import redis
import redis.exceptions
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

def get_http_param(request, key):
    try:
        return request.args[key]
    except MultiDict.KeyError:
        return ""

def is_valid_url(value):
    if not value:
        return False
    return value[:7] == 'http://' or value[:8] == 'https://'

def is_sip_url(value):
    if not value:
        return False
    return value[:4] == 'sip:'


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


def get_resource(socket, url):
    try:
        if socket.cache:
            # don't do cache if not a remote file
            if not url[:7].lower() == "http://" \
                and not url[:8].lower() == "https://":
                return url

            cache_url = socket.cache['url'].strip('/')
            data = {}
            data['url'] = url
            url_values = urllib.urlencode(data)
            full_url = '%s/CacheType/?%s' % (cache_url, url_values)
            req = urllib2.Request(full_url)
            handler = urllib2.urlopen(req)
            response = handler.read()
            result = json.loads(response)
            cache_type = result['CacheType']
            if cache_type == 'wav':
                wav_stream = 'shell_stream://%s %s/Cache/?%s' % (socket.cache['script'], cache_url, url_values)
                return wav_stream
            elif cache_type == 'mp3':
                _url = socket.cache['url'][7:].strip('/')
                mp3_stream = "shout://%s/Cache/?%s" % (_url, url_values)
                return mp3_stream
            else:
                socket.log.warn("Unsupported format %s" % str(cache_type))

    except Exception, e:
        socket.log.error("Cache Error !")
        socket.log.error("Cache Error: %s" % str(e))

    if url[:7].lower() == "http://":
        audio_path = url[7:]
        url = "shout://%s" % audio_path
    elif url[:8].lower() == "https://":
        audio_path = url[8:]
        url = "shout://%s" % audio_path

    return url



 

