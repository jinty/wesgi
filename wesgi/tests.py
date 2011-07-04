import os
from unittest import TestCase

import webob
from mock import patch, Mock

all_tests = False
if os.environ.get('WESGI_ALL_TESTS', 'false').lower() in ('true', '1', 't'):
    all_tests = True

patch_get_url = patch('wesgi._get_url', mocksignature=True)

class TestProcessInclude(TestCase):

    @patch_get_url
    def test_return_none_if_no_match(self, get_url):
        from wesgi import _process_include
        data = _process_include('')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)
        data = _process_include('something')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)
        data = _process_include('<html><head></head><body><h1>HI</h1><esi:not_an_include whatever="bobo"/></body></html>')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)

    @patch_get_url
    def test_match(self, get_url):
        get_url.return_value = '<div>example</div>'
        from wesgi import _process_include
        data = _process_include('before<esi:include src="http://www.example.com"/>after')
        self.assertEquals(data, 'before<div>example</div>after') 
        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, ''), {}))
        # onerror="continue" has no effect
        get_url.reset_mock()
        data = _process_include('before<esi:include src="http://www.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'before<div>example</div>after') 
        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, ''), {}))
    
    @patch_get_url
    def test_recursive(self, get_url):
        counter = range(10)
        def side_effect(*args):
            if not counter:
                return '-last'
            count = counter.pop(0)
            fragment = count + 1 # the nth fragment that we are including
            count += 2 # count starts at 0, but first time we include is level 2
            return '-%s<esi:include src="http://www.example.com/%s"/>' % (count, fragment)
        get_url.side_effect = side_effect
        from wesgi import _process_include, RecursionError, AkamaiPolicy
        data = _process_include('level-1<esi:include src="http://www.example.com"/>-after')
        self.assertEquals(data, 'level-1-2-3-4-5-6-7-8-9-10-11-last-after')
        self.assertEquals(get_url.call_count, 11)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, '/10'), {}))
        # Akamai FAQ http://www.akamai.com/dl/technical_publications/esi_faq.pdf
        # claims that they support 5 levels of nested includes. Ours should do the same
        # when using the akami policy
        counter.extend(range(5))
        self.assertRaises(RecursionError, _process_include, 'level-1<esi:include src="http://www.example.com"/>-after', policy=AkamaiPolicy())
        counter.extend(range(4))
        data = _process_include('level-1<esi:include src="http://www.example.com"/>-after', policy=AkamaiPolicy())
        self.assertEquals(data, 'level-1-2-3-4-5-last-after')
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, '/4'), {}))
        # Even with the akamai policy, if we're not in debug mode, no error is raised
        counter.extend(range(10))
        data = _process_include('level-1<esi:include src="http://www.example.com"/>-after', policy=AkamaiPolicy(), debug=False)
        self.assertEquals(data, 'level-1-2-3-4-5-6-7-8-9-10-11-last-after')

    @patch_get_url
    def test_invalid(self, get_url):
        from wesgi import _process_include, InvalidESIMarkup
        invalid1 = 'before<esi:include krud src="http://www.example.com"/>after'
        invalid2 = 'before<esi:include krud="krud" src="http://www.example.com"/>after'
        self.assertRaises(InvalidESIMarkup, _process_include, invalid1)
        self.assertRaises(InvalidESIMarkup, _process_include, invalid2)
        # if debug is False, these errors are not raised
        self.assertEquals(_process_include(invalid1, debug=False), 'beforeafter')
        self.assertEquals(_process_include(invalid2, debug=False), 'beforeafter')
        self.assertFalse(get_url.called)

    @patch_get_url
    def test_get_url_error_cases(self, get_url):
        class Oops(Exception):
            pass
        def side_effect(*args):
            def second_call(*args):
                return '<div>example alt</div>'
            get_url.side_effect = second_call
            raise Oops('oops')
        get_url.side_effect = side_effect
        from wesgi import _process_include
        # without src we get our exception
        self.assertRaises(Oops, _process_include, 'before<esi:include src="http://www.example.com"/>after')
        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, ''), {}))
        # it is still raised if we turn off debug mode (it's specified in the ESI spec)
        get_url.side_effect = side_effect
        self.assertRaises(Oops, _process_include, 'before<esi:include src="http://www.example.com"/>after', debug=False)
        # unless onerror="continue", in which case the include is silently deleted
        get_url.reset_mock()
        get_url.side_effect = side_effect
        data = _process_include('before<esi:include src="http://www.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'beforeafter') 
        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, ''), {}))
        # if we add a alt we get back the info from alt
        get_url.reset_mock()
        get_url.side_effect = side_effect
        data = _process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after')
        self.assertEquals(data, 'before<div>example alt</div>after') 
        self.assertEquals(get_url.call_args_list, [(('http', 'www.example.com', None, ''), {}),
                                                   (('http', 'alt.example.com', None, ''), {})])
        # onerror = "continue" has no effect if there is only one error and alt is specified
        get_url.reset_mock()
        get_url.side_effect = side_effect
        data = _process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'before<div>example alt</div>after') 
        self.assertEquals(get_url.call_args_list, [(('http', 'www.example.com', None, ''), {}),
                                                   (('http', 'alt.example.com', None, ''), {})])
        # If both calls to get_url fail, the second exception is raised
        class OopsAlt(Exception):
            pass
        def side_effect(*args):
            def second_call(*args):
                raise OopsAlt('oops')
            get_url.side_effect = second_call
            raise Oops('oops')
        get_url.reset_mock()
        get_url.side_effect = side_effect
        self.assertRaises(OopsAlt, _process_include, 'before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after')
        self.assertEquals(get_url.call_args_list, [(('http', 'www.example.com', None, ''), {}),
                                                   (('http', 'alt.example.com', None, ''), {})])
        # it is still raised if we turn off debug mode (it's specified in the ESI spec)
        get_url.side_effect = side_effect
        self.assertRaises(OopsAlt, _process_include, 'before<esi:include src="http://www.example.com" alt="http://alt.example.com"/>after', debug=False)
        # unless onerror="continue", in which case the include is silently deleted
        get_url.reset_mock()
        get_url.side_effect = side_effect
        data = _process_include('before<esi:include src="http://www.example.com" alt="http://alt.example.com" onerror="continue"/>after')
        self.assertEquals(data, 'beforeafter') 
        self.assertEquals(get_url.call_args_list, [(('http', 'www.example.com', None, ''), {}),
                                                   (('http', 'alt.example.com', None, ''), {})])


class TestMiddleWare(TestCase):

    def _one(self, *arg, **kw):
        from wesgi import MiddleWare
        return MiddleWare(*arg, **kw)

    def _make_app(self, body, content_type='text/html', status=200):
        def _app(environ, start_response):
            response = webob.Response(body, content_type=content_type)
            response.status = status
            return response(environ, start_response)
        return _app

    @patch_get_url
    def test_process(self, get_url):
        get_url.return_value = '<div>example</div>'
        mw = self._one(self._make_app('before<esi:include src="http://www.example.com"/>after', content_type='text/html'))

        start_response = Mock()
        request = webob.Request.blank("")
        response = mw(request.environ, start_response)

        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('http', 'www.example.com', None, ''), {}))
        self.assertEquals(''.join(response), 'before<div>example</div>after') 

    @patch_get_url
    def test_process_ssl(self, get_url):
        from wesgi import IncludeError
        get_url.return_value = '<div>example</div>'
        mw = self._one(self._make_app('before<esi:include src="http://www.example.com"/>after', content_type='text/html'))

        # trying to include an http: url from an https page raises an error
        start_response = Mock()
        request = webob.Request.blank("")
        request.environ['wsgi.url_scheme'] = 'https'
        response = self.assertRaises(IncludeError, mw, request.environ, start_response)
        self.assertEquals(get_url.call_count, 0)

        # https urls do work
        mw = self._one(self._make_app('before<esi:include src="https://www.example.com"/>after', content_type='text/html'))
        response = mw(request.environ, start_response)
        self.assertEquals(get_url.call_count, 1)
        self.assertEquals(get_url.call_args, (('https', 'www.example.com', None, ''), {}))
        self.assertEquals(''.join(response), 'before<div>example</div>after') 

if all_tests:
    class TestGetURL(TestCase):
        # test not run by default as it requires network connectivity

        def test_http(self):
            from wesgi import _get_url
            result = _get_url('http', 'www.google.es', None, '/')        
            self.assertTrue("google" in result.lower())

        def test_https(self):
            from wesgi import _get_url
            result = _get_url('https', 'encrypted.google.com', None, '/')        
            self.assertTrue("google" in result.lower())

def load_tests(loader, standard_tests, pattern):
    if all_tests:
        # run tests in our README.txt
        import doctest
        this_dir = os.path.dirname(__file__)
        readme = doctest.DocFileTest(os.path.join(this_dir, '..', 'README.txt'),
                                     module_relative=False)
        standard_tests.addTest(readme)
    return standard_tests
