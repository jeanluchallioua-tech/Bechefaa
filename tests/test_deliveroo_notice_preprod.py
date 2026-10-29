import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from clean_caisse.deliveroo_notice_preprod_phase6 import register_deliveroo_notice_preprod_phase6


class NoticeGuardTests(unittest.TestCase):
    def test_only_preproduction_pos_html_is_modified(self):
        source = 'prefix async function checkDeliveroo(){old}checkDeliveroo();setInterval(checkDeliveroo,5000); suffix'
        handlers = []
        app = SimpleNamespace(after_request=lambda f: handlers.append(f))
        request = SimpleNamespace(path='/pos')
        with patch.dict(sys.modules, {'flask': SimpleNamespace(request=request)}):
            register_deliveroo_notice_preprod_phase6(app)
        class Response:
            status_code = 200
            mimetype = 'text/html'
            def __init__(self): self.data = source
            def get_data(self, as_text=False): return self.data if as_text else self.data.encode()
            def set_data(self, value): self.data = value
        handler = handlers[0]
        with patch.dict(os.environ, {'CC_APP_ID': 'production'}):
            self.assertEqual(handler(Response()).data, source)
        with patch.dict(os.environ, {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0'}):
            request.path = '/historique'
            self.assertEqual(handler(Response()).data, source)
            request.path = '/pos'
            response = handler(Response())
            self.assertIn('const deliverooNoticeKey=', response.data)
            self.assertTrue(response.data.endswith(' suffix'))
            self.assertEqual(response.content_length, len(response.data.encode()))


if __name__ == '__main__': unittest.main()
