import re
import threading
import collections
from httplib2 import Http
from urlparse import urlsplit, urlunsplit

import webob

__all__ = ['Policy', 'AkamaiPolicy', 'MiddleWare', 'InvalidESIMarkup', 'RecursionError']

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

#
# Cache
#

_marker = object()

class _Counter(dict):

    def __missing__(self, key):
        return 0

class LRUCache(object):

    def __init__(self, maxsize=1000):
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
            orig_scheme = environ['wsgi.url_scheme']
            new_body = self._process(resp.body, orig_scheme)
            if new_body is not None:
                resp.body = new_body
        return resp(environ, start_response)

    def _process(self, body, orig_scheme):
        commented = self._commented(body)
        return self._process_include(body, orig_scheme=orig_scheme, comments=commented)

    def _commented(self, body):
        # identify parts of body which are comments
        comments = []
        c_idx = 0
        while 1:
            match = _re_comment.search(body, c_idx)
            if match is None:
                break
            c_idx = match.start() + 1
            if len(body) < match.end() + 1:
                continue
            if body[match.end()] != '>':
                #invalid comment, contains --, ignore it
                continue
            # we found a comment
            c_idx = match.end()
            comments.append((match.start(), match.end() + 1))
        return tuple(comments)

    def _process_include(self, body, orig_scheme='http', level=0, comments=()):
        debug = self.debug
        policy = self.policy
        comments = list(comments)
        require_ssl = not (orig_scheme == 'http')
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
                new_content = _include_url(match.group('src'), require_ssl, policy.chase_redirect, self.http)
            except:
                if match.group('alt'):
                    try:
                        new_content = _include_url(match.group('alt'), require_ssl, policy.chase_redirect, self.http)
                    except:
                        if match.group('onerror') == 'continue':
                            new_content = ''
                        else:
                            raise
                elif match.group('onerror') == 'continue':
                    new_content = ''
                else:
                    raise
            if new_content:
                # recurse to process any includes in the new content
                new_commented = self._commented(new_content)
                p = self._process_include(new_content, orig_scheme=orig_scheme, comments=new_commented, level=level + 1)
                if p is not None:
                    new_content = p
            new.append(new_content)
            # update index
            index = match.end()
        if not index:
            return None
        new.append(body[index:])
        return ''.join(new)

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

_re_include = re.compile(r'''<esi:include'''
                         r'''(?:\s+(?:''' # whitespace at start of tag
                             r'''src=["']?(?P<src>[^"'\s]*)["']?''' # find src=
                             r'''|alt=["']?(?P<alt>[^"'\s]*)["']?''' # or find alt=
                             r'''|onerror=["']?(?P<onerror>[^"'\s]*)["']?''' # or find onerror=
                             r'''|(?P<other>[^\s><]+)?''' # or find something eles
                         r'''))+\s*/>''') # match whitespace at the end and the end tag

_re_comment = re.compile(r'''<!--esi.*?--''', flags=re.DOTALL)

class _HTTPError(Exception):

    def __init__(self, url, status):
        self.status = status
        message = 'Url returned %s: %s' % (status, url)
        super(_HTTPError, self).__init__(message)

def _include_url(orig_url, require_ssl, chase_redirect, http):
    url = urlsplit(orig_url)
    if require_ssl and url.scheme != 'https':
        raise IncludeError('SSL required, cannot include: %s' % (orig_url, ))
    resp, content = http.request(orig_url)
    if resp.status == 200:
        return content
    raise _HTTPError(orig_url, resp.status)

