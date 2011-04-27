# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import re
import urlparse


def get_http_header(file_url):
    return ""


def is_valid_url(value):
    regex = re.compile(
      r'^(?:http|ftp)s?://' # http:// or https://
      r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
      r'localhost|' #localhost...
      r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
      r'(?::\d+)?' # optional port
      r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    # If no domain starters we assume its http and add it
    if not value.startswith('http://') or not value.startswith('https://') \
        or not value.startswith('ftp://'):
        value = "http://%s" %value

    if regex.search(value):
        return True
    # Trivial case failed. Try for possible IDN domain
    if value:
        scheme, netloc, path, query, fragment = urlparse.urlsplit(value)
        try:
            netloc = netloc.encode('idna') # IDN -> ACE
        except UnicodeError: # invalid domain part
            return False
        url = urlparse.urlunsplit((scheme, netloc, path, query, fragment))
        if regex.search(url):
            return True

    return False
