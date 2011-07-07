import os
from unittest import TestCase

import webob
from mock import patch, Mock, mocksignature

all_tests = False
if os.environ.get('WESGI_ALL_TESTS', 'false').lower() in ('true', '1', 't'):
    all_tests = True

patch_Http = patch('wesgi.Http', mocksignature=True)

def mock_http_request(http, response=None, content=None):
    """Return a httplib2.Http with request() mocked out"""
    http.request = Mock(spec_set=[])
    mock = http.request
    if content is not None or response is not None:
        if content is None:
            content = ''
        if response is None:
            response = Response()
        mock.return_value = response, content

def Response(status=200, headers=None):
    import httplib2
    assert isinstance(status, int)
    d = dict(status=str(status))
    if headers is not None:
        d.update(headers)
    return httplib2.Response(d)

def run_mw(mw):
    start_response = Mock()
    request = webob.Request.blank("")
    response = mw(request.environ, start_response)
    return ''.join(response)

def make_mw(app=None, **kw):
    status = kw.pop('http_status', 200)
    headers = kw.pop('http_headers', None)
    content = kw.pop('http_content', '')
    if app is None:
        body = kw.pop('app_body', '')
        app = make_app(body=body)
    from wesgi import MiddleWare
    mw = MiddleWare(app, **kw)
    mock_http_request(mw.http, Response(status=status, headers=headers), content)
    return mw

def make_app(body='', content_type='text/html', status=200):
    def _app(environ, start_response):
        response = webob.Response(body, content_type=content_type)
        response.status = status
        return response(environ, start_response)
    return _app


class TestProcessInclude(TestCase):

    def test_return_none_if_no_match(self):
        mw = make_mw()
        mock = mw.http.request
        data = mw._process_include('')
        self.assertEquals(data, None)
        self.assertFalse(mock.called)
        data = mw._process_include('something')
        self.assertEquals(data, None)
        self.assertFalse(mock.called)
        data = mw._process_include('<html><head></head><body><h1>HI</h1><esi:not_an_include whatever="bobo"/></body></html>')
        self.assertEquals(data, None)
        self.assertFalse(mock.called)

    def test_match(self):
        mw = make_mw(http_content='<div>example</div>')
        data = mw._process_include('before<esi:include src="http://www.example.com"/>after')
        self.assertEquals(data, 'before<div>example</div>after')
        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('http://www.example.com', ), ))
        # onerror="continue" has no effect
        mw.http.request.reset_mock()
        data = mw._process_include('before<esi:include src="http://www.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'before<div>example</div>after')
        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('http://www.example.com', ), ))

    def test_recursive(self):
        from wesgi import RecursionError, AkamaiPolicy
        counter = range(10)
        def side_effect(*args):
            if not counter:
                return Response(), '-last'
            count = counter.pop(0)
            fragment = count + 1 # the nth fragment that we are including
            count += 2 # count starts at 0, but first time we include is level 2
            return Response(), '-%s<esi:include src="http://www.example.com/%s"/>' % (count, fragment)
        mw = make_mw()
        mock = mw.http.request
        mock.side_effect = side_effect
        data = mw._process_include('level-1<esi:include src="http://www.example.com"/>-after')
        self.assertEquals(data, 'level-1-2-3-4-5-6-7-8-9-10-11-last-after')
        self.assertEquals(mock.call_count, 11)
        self.assertEquals(mock.call_args, (('http://www.example.com/10', ), ))
        # Akamai FAQ http://www.akamai.com/dl/technical_publications/esi_faq.pdf
        # claims that they support 5 levels of nested includes. Ours should do the same
        # when using the akami policy
        counter.extend(range(5))
        mw.policy = AkamaiPolicy()
        self.assertRaises(RecursionError, mw._process_include, 'level-1<esi:include src="http://www.example.com"/>-after')
        counter.extend(range(4))
        data = mw._process_include('level-1<esi:include src="http://www.example.com"/>-after')
        self.assertEquals(data, 'level-1-2-3-4-5-last-after')
        self.assertEquals(mock.call_args, (('http://www.example.com/4', ), ))
        # Even with the akamai policy, if we're not in debug mode, no error is raised
        counter.extend(range(10))
        mw.debug = False
        data = mw._process_include('level-1<esi:include src="http://www.example.com"/>-after')
        self.assertEquals(data, 'level-1-2-3-4-5-6-7-8-9-10-11-last-after')

    def test_invalid(self):
        from wesgi import InvalidESIMarkup
        mw = make_mw()
        invalid1 = 'before<esi:include krud src="http://www.example.com"/>after'
        invalid2 = 'before<esi:include krud="krud" src="http://www.example.com"/>after'
        self.assertRaises(InvalidESIMarkup, mw._process_include, invalid1)
        self.assertRaises(InvalidESIMarkup, mw._process_include, invalid2)
        # if debug is False, these errors are not raised
        mw.debug = False
        self.assertEquals(mw._process_include(invalid1), 'beforeafter')
        self.assertEquals(mw._process_include(invalid2), 'beforeafter')
        self.assertFalse(mw.http.request.called)

    def test_some_http_error_cases(self):
        class Oops(Exception):
            pass
        def side_effect(*args):
            def second_call(*args):
                return Response(), '<div>example alt</div>'
            mw.http.request.side_effect = second_call
            raise Oops('oops')
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        # without src we get our exception
        self.assertRaises(Oops, mw._process_include, 'before<esi:include src="http://www.example.com"/>after')
        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('http://www.example.com', ), ))
        # it is still raised if we turn off debug mode (it's specified in the ESI spec)
        mw.http.request.side_effect = side_effect
        mw.debug = False
        self.assertRaises(Oops, mw._process_include, 'before<esi:include src="http://www.example.com"/>after')
        # unless onerror="continue", in which case the include is silently deleted
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        data = mw._process_include('before<esi:include src="http://www.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'beforeafter')
        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('http://www.example.com', ), ))
        # if we add a alt we get back the info from alt
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        data = mw._process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after')
        self.assertEquals(data, 'before<div>example alt</div>after')
        self.assertEquals(mw.http.request.call_args_list, [(('http://www.example.com', ), ),
                                                   (('http://alt.example.com', ), )])
        # onerror = "continue" has no effect if there is only one error and alt is specified
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        data = mw._process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'before<div>example alt</div>after')
        self.assertEquals(mw.http.request.call_args_list, [(('http://www.example.com', ), ),
                                                   (('http://alt.example.com', ), )])
        # If both calls to mw.http.request fail, the second exception is raised
        class OopsAlt(Exception):
            pass
        def side_effect(*args):
            def second_call(*args):
                raise OopsAlt('oops')
            mw.http.request.side_effect = second_call
            raise Oops('oops')
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        self.assertRaises(OopsAlt, mw._process_include, 'before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after')
        self.assertEquals(mw.http.request.call_args_list, [(('http://www.example.com', ), ),
                                                   (('http://alt.example.com', ), )])
        # it is still raised if we turn off debug mode (it's specified in the ESI spec)
        mw.http.request.side_effect = side_effect
        mw.debug = False
        self.assertRaises(OopsAlt, mw._process_include, 'before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after')
        # unless onerror="continue", in which case the include is silently deleted
        mw = make_mw()
        mw.http.request.side_effect = side_effect
        data = mw._process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'beforeafter')
        self.assertEquals(mw.http.request.call_args_list, [(('http://www.example.com', ), ),
                                                   (('http://alt.example.com', ), )])

    def test_regression_regex_performance_extra_data(self):
        # processing this data used to take a LOONG time
        import time
        mw = make_mw(http_content='<div>example</div>')
        this_dir = os.path.dirname(__file__)
        test_data = '<esi:include src="http://www.google.com" />\n\t\t\r\n\t\t\t\r\n\t\t\t\t\r\n\t\t\t\t\r\n\t\t\t\r\n\t\t</p>\r\n'
        now = time.time()
        data = mw._process_include(test_data)
        used = time.time() - now
        self.assertTrue(used < 0.01, 'Test took too long: %s seconds' % used)

class TestMiddleWare(TestCase):

    def test_process(self):
        mw = make_mw(app_body='before<esi:include src="http://www.example.com"/>after',
                     http_content="<div>example</div>")

        response = run_mw(mw)

        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('http://www.example.com', ), ))
        self.assertEquals(response, 'before<div>example</div>after')

    def test_process_ssl(self):
        from wesgi import IncludeError
        mw = make_mw(app_body='before<esi:include src="http://www.example.com"/>after',
                     http_content='<div>example</div>')

        # trying to include an http: url from an https page raises an error
        start_response = Mock()
        request = webob.Request.blank("")
        request.environ['wsgi.url_scheme'] = 'https'
        response = self.assertRaises(IncludeError, mw, request.environ, start_response)
        self.assertEquals(mw.http.request.call_count, 0)

        # https urls do work
        mw = make_mw(app_body='before<esi:include src="https://www.example.com"/>after',
                     http_content='<div>example</div>')
        response = mw(request.environ, start_response)
        self.assertEquals(mw.http.request.call_count, 1)
        self.assertEquals(mw.http.request.call_args, (('https://www.example.com', ), ))
        self.assertEquals(''.join(response), 'before<div>example</div>after')
    
    def test_comment(self):
        result = '<div>example</div>'
        this_dir = os.path.dirname(__file__)
        include = '<esi:include src="http://www.example.com" />'
        test_data = [(include, result),
                     '<!-- html comment',
                     (include, result),
                     '-->',
                     'blah',
                     '<!--esi half open esi',
                     (include, result),
                     '<!--esi esi comment 1',
                     (include, include),
                     '-->',
                     (include, result),
                     '<!--esi esi comment 2',
                     (include, include),
                     '-->',
                     '<!--esi esi comment 3 containing a single -',
                     (include, include),
                     '-->',
                     (include, result)]
        expected = []
        data = []
        for i in test_data:
            input = res = i
            if not isinstance(i, basestring):
                input, res = i
            expected.append(res)
            data.append(input)
        mw = make_mw(http_content=result,
                     app_body='\n'.join(data))
        data = run_mw(mw)
        expected = u'\n'.join(expected)
        self.assertEquals(data, expected)
        # regression test for an error
        data = '<!--esi %s --'
        self.assertEquals(mw._process_include(data % include), data % result)


class TestPolicy(TestCase):

    def test_chase_redirect(self):
        from wesgi import Policy
        policy = Policy()
        self.assertEquals(policy.http().follow_redirects, False)
        # unless it's specified in the policy
        policy = Policy()
        policy.chase_redirect = True
        self.assertEquals(policy.http().follow_redirects, True)

    def test_cache(self):
        # no caching by default
        from wesgi import Policy
        policy = Policy()
        self.assertEquals(policy.cache, None)

class TestLRUCache(TestCase):

    def test_basic(self):
        from wesgi import LRUCache
        cache = LRUCache()
        self.assertEquals(cache.get('a'), None)
        self.assertEquals(cache.get('b'), None)
        self.assertEquals(cache._refcount, {'a': 1, 'b': 1})
        self.assertEquals(cache._cache, {})
        cache.set('a', 'x')
        self.assertInvariants(cache)
        self.assertEquals(cache.get('a'), 'x')
        self.assertEquals(cache.get('b'), None)
        self.assertEquals(cache._refcount, {'a': 3, 'b': 2})
        self.assertEquals(cache._cache, {'a': 'x'})
        cache.set('b', 'y')
        self.assertInvariants(cache)
        self.assertEquals(cache.get('a'), 'x')
        self.assertEquals(cache.get('b'), 'y')
        self.assertEquals(cache._refcount, {'a': 4, 'b': 4})
        self.assertEquals(cache._cache, {'a': 'x', 'b': 'y'})
        cache.set('b', 'z')
        self.assertInvariants(cache)
        self.assertEquals(cache.get('a'), 'x')
        self.assertEquals(cache.get('b'), 'z')
        self.assertEquals(cache._refcount, {'a': 5, 'b': 6})
        self.assertEquals(cache._cache, {'a': 'x', 'b': 'z'})
        cache.delete('b')
        self.assertInvariants(cache)
        self.assertEquals(cache._refcount, {'a': 5, 'b': 6})
        self.assertEquals(cache.get('a'), 'x')
        self.assertEquals(cache.get('b'), None)
        self.assertEquals(cache._cache, {'a': 'x'})
        cache.delete('a')
        self.assertInvariants(cache)
        self.assertEquals(cache._refcount, {'a': 6, 'b': 7})
        self.assertEquals(cache.get('a'), None)
        self.assertEquals(cache.get('b'), None)
        self.assertEquals(cache._cache, {})
    
    def test_hit_miss(self):
        # an LRU's biggest weakness is the sequential scan
        # this is what happens
        from wesgi import LRUCache
        cache = LRUCache(maxsize=3)
        cache.get('a')
        cache.set('a', 'a')
        self.assertEquals(cache.hits, 0)
        self.assertEquals(cache.misses, 1)
        cache.get('a')
        self.assertEquals(cache.hits, 1)
        self.assertEquals(cache.misses, 1)
        cache.get('b')
        self.assertEquals(cache.hits, 1)
        self.assertEquals(cache.misses, 2)
        cache.get('a')
        self.assertEquals(cache.hits, 2)
        self.assertEquals(cache.misses, 2)
        self.assertInvariants(cache)
    
    def test_repeated_get_and_set_flushes_cache(self):
        # an LRU's biggest weakness is the sequential scan
        # this is what happens
        from wesgi import LRUCache
        cache = LRUCache(maxsize=3)
        cache.get('a')
        cache.set('a', 'a')
        cache.get('b')
        cache.set('b', 'b')
        for i in range(100): 
            cache.get(str(i))
            cache.set(str(i), str(i))
        self.assertEquals(cache._cache, {'99': '99', '98': '98', '97': '97'})
        self.assertEquals(cache.hits, 0)
        self.assertEquals(cache.misses, 102)
        self.assertInvariants(cache)
    
    def test_repeated_set_without_get_does_not_flushe_cache(self):
        from wesgi import LRUCache
        cache = LRUCache(maxsize=3)
        cache.get('a')
        cache.set('a', 'a')
        cache.get('b')
        cache.set('b', 'b')
        for i in range(100): 
            cache.set(str(i), str(i))
        self.assertEquals(cache._cache, {'99': '99', 'a': 'a', 'b': 'b'})
        self.assertInvariants(cache)

    def test_queue_compaction(self):
        from wesgi import LRUCache
        cache = LRUCache(maxsize=10)
        [cache.get(1) for i in range(100)] # fill up to maxqueue
        self.assertEquals(list(cache._queue), [1 for i in xrange(100)]) # our queue is full
        self.assertEquals(cache._refcount, {1: 100})
        cache.get(1) #push us over the limit
        self.assertEquals(list(cache._queue), [1])
        self.assertEquals(cache._refcount, {1: 1})
        self.assertInvariants(cache)

    def test_queue_comaction_different_values(self):
        from wesgi import LRUCache
        # test compaction with a different value first
        cache = LRUCache(maxsize=10)
        cache.get(2)
        [cache.get(1) for i in range(49)]
        cache.get(2)
        [cache.get(1) for i in range(50)] # Push us one over the limit
        self.assertEquals(list(cache._queue), [2, 1])
        self.assertEquals(cache._refcount, {1: 1, 2: 1})
        # and after
        cache = LRUCache(maxsize=10)
        [cache.get(1) for i in range(49)]
        cache.get(2)
        [cache.get(1) for i in range(50)]
        cache.get(2) # Push us one over the limit
        self.assertEquals(list(cache._queue), [1, 2])
        self.assertEquals(cache._refcount, {1: 1, 2: 1})
        self.assertInvariants(cache)

    def test_queue_emptying(self):
        # the queue is emptied when it gets too big and we cannot compact
        from wesgi import LRUCache
        cache = LRUCache(maxsize=10)
        [cache.get(i) for i in range(100)] # fill up to maxqueue
        self.assertEquals(list(cache._queue), range(100)) # all elements are in the queue
        self.assertEquals(len(cache._queue), 100)
        self.assertEquals(cache._refcount, dict([(i, 1) for i in range(100)]))
        cache.get(100) #push us over the limit
        self.assertEquals(len(cache._queue), 80)
        self.assertEquals(list(cache._queue), range(21, 101))
        self.assertEquals(cache._refcount, dict([(i, 1) for i in range(21, 101)]))
        self.assertInvariants(cache)

    def test_queue_emptying_memory_leak(self):
        # When we empty the queue, we need to make sure that elements in our cache stay in the queue
        from wesgi import LRUCache
        cache = LRUCache(maxsize=10)
        cache.set('x', 'y')
        [cache.get(i) for i in range(100)] # fill queue over maxsize
        self.assertEquals(cache._cache, {'x': 'y'})
        self.assertEquals(len(cache._queue), 80)
        self.assertEquals(list(cache._queue), ['x'] + range(21, 100))
        expected_refcount = dict([(i, 1) for i in range(21, 100)])
        expected_refcount['x'] = 1
        self.assertEquals(cache._refcount, expected_refcount)
        self.assertInvariants(cache)

    def test_thread_fuzzing(self):
        from wesgi import LRUCache
        import threading
        import time
        max = 100
        no_threads = 2
        if all_tests:
            max = 500
            no_threads = 5
        cache = LRUCache(maxsize=5)
        def pound():
            for k in xrange(max):
                for i in range(10):
                    val = cache.get(i)
                    if not val:
                        cache.set(i, k)
                    cache.get(i - 1)
                    cache.get(i - 3)
                    cache.get(i + 3)
                    cache.delete(i + 1)
                    cache.set(i + 2, k)
        threads = []
        for i in range(no_threads):
            threads.append(threading.Thread(target=pound))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertInvariants(cache)

    def assertInvariants(self, cache):
        count = {}
        for k in cache._queue:
            count[k] = count.setdefault(k, 0) + 1
        self.assertEquals(count, cache._refcount)
        for k in cache._cache:
            self.assertTrue(k in count, k)

if all_tests:
    class TestRealRequest(TestCase):
        # test not run by default as it requires network connectivity

        def test_http(self):
            from wesgi import Policy
            policy = Policy()
            policy.chase_redirect = True
            http = policy.http()
            result, content = http.request('http://www.google.com/')
            self.assertTrue("google" in content.lower())

        def test_cached_http(self):
            from wesgi import LRUCache
            from wesgi import Policy
            policy = Policy()
            policy.cache = LRUCache()
            policy.chase_redirect = True
            http = policy.http()
            self.assertEquals(0, policy.cache.hits + policy.cache.misses)
            result, content = http.request('http://www.google.com/')
            self.assertTrue("google" in content.lower())
            self.assertFalse(result.fromcache)
            self.assertNotEquals(0, policy.cache.hits + policy.cache.misses)
            result, content = http.request('http://www.google.com/')
            self.assertTrue("google" in content.lower())
            self.assertNotEquals(0, policy.cache.hits + policy.cache.misses)

        def test_https(self):
            from wesgi import Policy
            policy = Policy()
            policy.chase_redirect = True
            http = policy.http()
            result, content = http.request('https://encrypted.google.com/')
            self.assertTrue("google" in content.lower())

def load_tests(loader, standard_tests, pattern):
    if all_tests:
        # run tests in our README.txt
        import doctest
        this_dir = os.path.dirname(__file__)
        readme = doctest.DocFileTest(os.path.join(this_dir, '..', 'README.rst'),
                                     module_relative=False)
        standard_tests.addTest(readme)
    return standard_tests
