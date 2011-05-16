# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import base64
import ConfigParser
import httplib
import os.path
import re
import urllib
import urllib2
import urlparse

from werkzeug.datastructures import MultiDict


def url_exists(url):
    p = urlparse.urlparse(url)
    try:
        connection = httplib.HTTPConnection(p[1])
        connection.request('HEAD', p[2])
        response = connection.getresponse()
        connection.close()
        return response.status == httplib.OK
    except Exception:
        return False


def file_exists(filepath):
    return os.path.isfile(filepath)


def get_config(filename):
    config = ConfigParser.SafeConfigParser()
    config.read(filename)
    return config


def get_post_param(request, str):
    try:
        return request.form[str]
    except MultiDict.KeyError:
        return ""


def get_conf_value(config, section, key):
    try:
        value = config.get(section, key)
        return str(value)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
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
    def __init__(self, auth_id ='', auth_token =''):
        """initialize a object

        id: Plivo SID/ID
        token: Plivo token

        returns a HTTPRequest object
        """
        self.auth_id = auth_id
        self.auth_token = auth_token
        self.opener = None

    def _build_get_uri(self, uri, params):
        if params and len(params) > 0:
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

        authstring = base64.encodestring('%s:%s' % (self.auth_id,
                                                            self.auth_token))
        authstring = authstring.replace('\n', '')
        request.add_header("Authorization", "Basic %s" % authstring)

        return request

    def fetch_response(self, uri, params, method='POST'):
        if method and method not in ['GET', 'POST']:
            raise NotImplementedError('HTTP %s method not implemented'
                                                                    % method)

        request = self._prepare_http_request(uri, params, method)
        try:
            response = urllib2.urlopen(request).read()
        except Exception, e:
            response = ""

        return response
