import re
import httplib
from urlparse import urlsplit, urlunsplit

import webob

_re_include = re.compile(r'''<esi:include'''
                         r'''(?:\s+(?:''' # whitespace at start of tag
                             r'''src=["']?(?P<src>[^"'\s]*)["']?''' # find src=
                             r'''|alt=["']?(?P<alt>[^"'\s]*)["']?''' # or find alt=
                             r'''|onerror=["']?(?P<onerror>[^"'\s]*)["']?''' # or find onerror=
                             r'''|(?P<other>[^\s]+)?''' # or find something eles
                         r'''))+\s*/>''') # match whitespace at the end and the end tag

def get_url(url, chase_redirect=False, force_ssl=False):
    if chase_redirect or force_ssl:
        raise NotImplementedError
    url = urlsplit(url)
    if url.scheme != 'http':
        raise NotImplementedError
    path = urlunsplit(('', '', url[2], url[3], url[4]))
    conn = httplib.HTTPConnection(url.hostname, url.port)
    conn.request("GET", path)
    resp = conn.getresponse()
    if resp != '200':
        raise Exception(resp.status)
    return resp.read()

class InvalidESIMarkup(Exception):
    pass

def process_include(body):
    index = 0
    new = []
    matches = _re_include.finditer(body)
    for match in matches:
        # add section before current match to new body
        new.append(body[index:match.start()])
        if match.group('other') or not match.group('src'):
            raise InvalidESIMarkup("Invalid ESI markup: %s" % body[match.start():match.end()])
        # get content to insert
        new_content = get_url(match.group('src'))
        new.append(new_content)
        # update index
        index = match.end()
    if not index:
        return None
    new.append(body[index:])
    return ''.join(new)


class MiddleWare(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        req = webob.Request(environ)
        resp = req.get_response(self.app)
        if resp.content_type == 'text/html' and resp.status_int == 200:
            new_body = process_include(resp.body)
            if new_body is not None:
                resp.body = new_body
        return resp(environ, start_response)
