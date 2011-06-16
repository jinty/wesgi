from unittest import TestCase
from mock import patch

patch_get_url = patch('wesgi.get_url', mocksignature=True)

class TestProcessInclude(TestCase):

    @patch_get_url
    def test_return_none_if_no_match(self, get_url):
        from wesgi import process_include
        data = process_include('')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)
        data = process_include('something')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)
        data = process_include('<html><head></head><body><h1>HI</h1><esi:not_an_include whatever="bobo"/></body></html>')
        self.assertEquals(data, None) 
        self.assertFalse(get_url.called)

    @patch_get_url
    def test_match(self, get_url):
        get_url.return_value = '<div>example</div>'
        from wesgi import process_include
        data = process_include('before<esi:include src="http://www.example.com"/>after')
        self.assertEquals(data, 'before<div>example</div>after') 
        self.assertEquals(get_url.call_count, 1)

    @patch_get_url
    def test_invalid(self, get_url):
        from wesgi import process_include, InvalidESIMarkup
        self.assertRaises(InvalidESIMarkup, process_include, 'before<esi:include krud src="http://www.example.com"/>after')
        self.assertRaises(InvalidESIMarkup, process_include, 'before<esi:include krud="krud" src="http://www.example.com"/>after')
        self.assertFalse(get_url.called)
