import json
import unittest
import urllib.request
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from clean_caisse.deliveroo_stock_transport_phase6 import STOCK_URL, NoRedirect, post_stock_once

PAYLOAD = {'item_unavailabilities': [{'item_id': 'whole_milk', 'status': 'unavailable'}]}

class StockTransportTests(unittest.TestCase):
    def response(self, code=200, body=b'{}', headers=None):
        return nullcontext(SimpleNamespace(code=code, read=lambda:body, geturl=lambda:STOCK_URL,
                                           headers=headers or {'Content-Type':'application/json'}))

    def test_exact_post_once_with_actual_url_and_no_secrets_in_trace(self):
        opener=Mock();opener.open.return_value=self.response()
        with patch('urllib.request.build_opener',return_value=opener) as build:
            code,body,trace=post_stock_once(STOCK_URL,'secret-token',PAYLOAD)
        self.assertEqual(code,200); self.assertEqual(body,{})
        req=opener.open.call_args.args[0]
        self.assertEqual(req.get_method(),'POST'); self.assertEqual(json.loads(req.data),PAYLOAD)
        self.assertIsInstance(build.call_args.args[0],NoRedirect)
        self.assertTrue(trace['url_unchanged']); self.assertFalse(trace['redirects_allowed'])
        self.assertEqual(opener.open.call_count,1)
        self.assertNotIn('secret-token',json.dumps(trace))

    def test_redirect_handler_refuses_post_to_get_rewrite(self):
        req=urllib.request.Request(STOCK_URL,data=b'{}',method='POST')
        for code in (301,302,303,307,308):
            self.assertIsNone(NoRedirect().redirect_request(req,None,code,'redirect',{},'https://other.invalid'))

    def test_redirect_is_reported_without_following_or_exposing_query(self):
        opener=Mock();opener.open.side_effect=HTTPError(STOCK_URL,302,'redirect',
            {'Location':'https://other.invalid/path?token=do-not-expose'},BytesIO(b''))
        with patch('urllib.request.build_opener',return_value=opener):
            code,body,trace=post_stock_once(STOCK_URL,'secret',PAYLOAD)
        self.assertEqual(code,302);self.assertTrue(trace['redirect_blocked'])
        self.assertEqual(trace['redirect_target_host'],'other.invalid')
        self.assertNotIn('do-not-expose',json.dumps(trace));opener.open.assert_called_once()

    def test_non_json_response_cannot_masquerade_as_json_success(self):
        opener=Mock();opener.open.return_value=self.response(body=b'<html>login</html>')
        with patch('urllib.request.build_opener',return_value=opener):
            _,body,trace=post_stock_once(STOCK_URL,'secret',PAYLOAD)
        self.assertEqual(body['format'],'non_json');self.assertNotIn('login',json.dumps(body))

    def test_production_or_other_site_url_never_sends(self):
        with patch('urllib.request.build_opener') as build:
            for url in (STOCK_URL.replace('api-sandbox','api'),STOCK_URL+'/',STOCK_URL[:-3]+'102'):
                with self.assertRaises(ValueError):post_stock_once(url,'secret',PAYLOAD)
        build.assert_not_called()

if __name__=='__main__':unittest.main()
