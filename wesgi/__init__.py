import re
import sys
import threading
import collections
from httplib2 import Http
try:
    from urllib.parse import urlsplit, urljoin
except ImportError:
    # Python 2
    from urlparse import urlsplit, urljoin

import webob

__all__ = ['Policy', 'AkamaiPolicy', 'MiddleWare', 'InvalidESIMarkup', 'RecursionError']

try:
    from sys import getsizeof
except ImportError:
    # Python 2.5
    def getsizeof(obj):
        if isinstance(obj, basestring):
            # approximation for strings, which is what httplib stores
            return len(obj)
        return 0

try:
    basestring
except NameError:
    basestring = str

#
# Policies that can make the middleware work like different ESI processors
#

class Policy(object):
    max_nested_includes = None
    chase_redirect = False
    cache = None

    def http(self):
        http = Http(cache=self.cache, timeout=5, disable_ssl_certificate_validation=True)
        http.follow_redirects = self.chase_redirect
        return http

class AkamaiPolicy(Policy):
    """Configure the middleware to behave like akamai"""
    max_nested_includes = 5



#: Client headers to forward in subrequests to all servers
forward_headers_all_servers = set(['accept-language', 'cache-control'])

#: Client headers to forward only in subrequests to the same server
forward_headers_same_origin = forward_headers_all_servers | \
        set(['cookie', 'authorization', 'referer'])

#
# Cache
#

_marker = object()

class _Counter(dict):

    def __missing__(self, key):
        return 0

class LRUCache(object):

    def __init__(self, maxsize=1000, max_object_size=102400):
        # 1000 * 40kb/page ~ 40Mb
        maxqueue = maxsize * 10
        queuedrop = maxsize * 2
        # set instance variables so we can test
        self._cache = cache = {}
        self._refcount = refcount = _Counter()
        self._queue = queue = collections.deque()
        lock = threading.Lock()
        self.hits = 0
        self.misses = 0

        def compact_queue():
            # compact the queue when it gets too big
            # first: remove duplicates
            refcount.clear()
            queue.appendleft(_marker)
            for k in iter(queue.pop, _marker):
                if k in refcount:
                    continue
                queue.appendleft(k)
                refcount[k] = 1
            if len(queue) > maxqueue:
                # if we're still too big, and have no duplicates
                # there's probably something hammering the same thing remove
                # queuedrop items not in our cache
                count = 0
                queue.append(_marker)
                while count <= queuedrop:
                    key = queue.popleft()
                    assert key is not _marker
                    if key in self._cache:
                        queue.append(key)
                    else:
                        count += 1
                        del refcount[key]
                for k in iter(queue.popleft, _marker):
                    queue.append(k)

        def get(key):
            if lock.acquire(False):
                try:
                    queue.append(key)
                    refcount[key] = refcount.get(key, 0) + 1
                    if len(queue) > maxqueue:
                        compact_queue()
                finally:
                    lock.release()
            val = cache.get(key, _marker)
            if val is not _marker:
                self.hits += 1
                return val
            self.misses += 1
            return None

        def set(key, value):
            if max_object_size is not None and getsizeof(value) > max_object_size:
                # note, this doesn't take into account the size of objects referenced by value
                return
            orig_key = key
            if len(cache) >= maxsize:
                # remove least recently used
                key = queue.popleft()
                refcount[key] -= 1
                while refcount[key]:
                    key = queue.popleft()
                    refcount[key] -= 1
                del refcount[key]
                delete(key)
            queue.appendleft(orig_key)
            refcount[orig_key] += 1
            cache[orig_key] = value

        def locked_set(key, value):
            lock.acquire()
            try:
                set(key, value)
            finally:
                lock.release()

        def delete(key):
            cache.pop(key, None)

        self.get = get
        self.set = locked_set
        self.delete = delete

#
# The middleware
#

class MiddleWare(object):

    def __init__(self, app, policy='default', debug=True):
        self.debug = debug
        self.app = app
        if isinstance(policy, basestring):
            policy = _POLICIES[policy]
        self.policy = policy
        self.http = policy.http()

    def __call__(self, environ, start_response):
        req = webob.Request(environ)
        resp = req.get_response(self.app)
        if resp.content_type == 'text/html' and resp.status_int == 200:
            new_body = self._process(resp.body, req)
            if new_body is not None:
                resp.body = new_body
        return resp(environ, start_response)

    def _process(self, body, req):
        commented = self._commented(body)
        return self._process_include(body, req, comments=commented)

    def _commented(self, body):
        # identify parts of body which are comments
        comments = []
        c_idx = 0

        # Compatibility workaround: in python 2 this returns ``'>'``,
        # in python 3 it's ``62``.
        end_of_comment_marker = b'>'[0]
        while 1:
            match = _re_comment.search(body, c_idx)
            if match is None:
                break
            c_idx = match.start() + 1
            if len(body) < match.end() + 1:
                continue
            if body[match.end()] != end_of_comment_marker:
                # invalid comment, contains --, ignore it
                continue
            # we found a comment
            c_idx = match.end()
            comments.append((match.start(), match.end() + 1))
        return tuple(comments)

    def _process_include(self, body, req, level=0, comments=()):
        debug = self.debug
        policy = self.policy
        comments = list(comments)
        require_ssl = not (req.environ['wsgi.url_scheme'] == 'http')
        if debug and policy.max_nested_includes is not None and level > policy.max_nested_includes:
            raise RecursionError('Too many nested includes', level, body)
        c_start = c_end = None
        if comments:
            c_start, c_end = comments.pop(0)
        # process the includes
        index = 0
        new = []
        matches = _re_include.finditer(body)
        for match in matches:
            if c_end is not None:
                while c_end is not None and c_end < match.end():
                    # remove comments which we have passed
                    c_start = c_end = None
                    if comments:
                        c_start, c_end = comments.pop(0)
                if c_end is not None:
                    # ignore this match if we are in a comment
                    if c_start < match.start() and c_end > match.end():
                        continue
            # add section before current match to new body
            new.append(body[index:match.start()])
            if match.group('other') or not match.group('src'):
                if debug:
                    raise InvalidESIMarkup("Invalid ESI markup: %s" % body[match.start():match.end()])
                # silently ignore this match
                index = match.end()
                continue
            # get content to insert
            try:
                new_content = _include_url(match.group('src'), req, require_ssl, policy.chase_redirect, self.http)
            except:
                if match.group('alt'):
                    try:
                        new_content = _include_url(match.group('alt'), req, require_ssl, policy.chase_redirect, self.http)
                    except:
                        if match.group('onerror') == b'continue':
                            new_content = b''
                        else:
                            raise
                elif match.group('onerror') == b'continue':
                    new_content = b''
                else:
                    raise
            if new_content:
                # recurse to process any includes in the new content
                new_commented = self._commented(new_content)
                p = self._process_include(new_content, req, comments=new_commented, level=level + 1)
                if p is not None:
                    new_content = p
            new.append(new_content)
            # update index
            index = match.end()
        if not index:
            return None
        new.append(body[index:])
        return b''.join(new)

#
# Exceptions we can raise
#

class InvalidESIMarkup(Exception):
    pass

class RecursionError(Exception):

    def __init__(self, msg, level, body):
        super(RecursionError, self).__init__(msg, level, body)
        self.msg = msg
        self.body = body
        self.level = level

class IncludeError(Exception):
    pass

#
# The internal bits to do the work
#

_POLICIES = {'default': Policy(),
             'akamai': AkamaiPolicy()}

_re_include = re.compile(br'''<esi:include'''
                         br'''(?:\s+(?:''' # whitespace at start of tag
                             br'''src=["']?(?P<src>[^"'\s]*)["']?''' # find src=
                             br'''|alt=["']?(?P<alt>[^"'\s]*)["']?''' # or find alt=
                             br'''|onerror=["']?(?P<onerror>[^"'\s]*)["']?''' # or find onerror=
                             br'''|(?P<other>[^\s><]+)?''' # or find something eles
                         br'''))+\s*/>''') # match whitespace at the end and the end tag

_re_comment = re.compile(br'''<!--esi.*?--''', flags=re.DOTALL)

class _HTTPError(Exception):

    def __init__(self, url, status):
        self.status = status
        message = 'Url returned %s: %s' % (status, url)
        super(_HTTPError, self).__init__(message)


def _forward_all_headers_allowed(origin_host, is_ssl, url):
    """
    Return True if headers can be forwarded to urlparse result ``url``.
    This returns true if ``url`` refers to the same server and same protocol
    (http, https) as ``origin_host``.

    This is overly simplistic,
    """

    # Fail safe in the case that the original host header was not specified
    if not origin_host:
        return False

    # Don't allow headers to be fowarded from https -> http or vice versa
    if is_ssl != bool(url.scheme == 'https'):
        return False

    url_host = url.netloc

    if ':' not in url_host:
        url_host += ':443' if is_ssl else ':80'

    if ':' not in origin_host:
        origin_host += ':443' if is_ssl else ':80'

    return url_host == origin_host


def _include_url(orig_url, req, require_ssl, chase_redirect, http):
    orig_url = orig_url.decode('ascii')
    orig_url = urljoin(req.path_url, orig_url)
    url = urlsplit(orig_url)
    headers = req.headers
    if require_ssl and url.scheme != 'https':
        raise IncludeError('SSL required, cannot include: %s' % (orig_url, ))

    if _forward_all_headers_allowed(headers.get('Host'), require_ssl, url):
        forward_headers = forward_headers_same_origin
    else:
        forward_headers = forward_headers_all_servers

    headers = dict((k, v)
                    for k, v in headers.items()
                    if k.lower() in forward_headers)

    resp, content = http.request(orig_url, headers=dict(headers))
    if resp.status == 200:
        return content
    raise _HTTPError(orig_url, resp.status)
