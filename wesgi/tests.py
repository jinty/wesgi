from unittest import TestCase

import webob
from mock import patch, Mock

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
    def test_invalid(self, get_url):
        from wesgi import _process_include, InvalidESIMarkup
        self.assertRaises(InvalidESIMarkup, _process_include, 'before<esi:include krud src="http://www.example.com"/>after')
        self.assertRaises(InvalidESIMarkup, _process_include, 'before<esi:include krud="krud" src="http://www.example.com"/>after')
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
