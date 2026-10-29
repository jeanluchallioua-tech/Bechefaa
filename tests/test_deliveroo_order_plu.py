import ast
import json
import unittest
import urllib.request
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
from clean_caisse.deliveroo_order_plu_phase6 import missing_plu_paths


class PluTests(unittest.TestCase):
    def test_missing_blank_and_null_article_ids(self):
        for value in (None, '', '  '):
            self.assertEqual(missing_plu_paths({'body': {'order': {'items': [{'pos_item_id': value}]}}}),
                             ['items[0].pos_item_id'])

    def test_nested_modifier_is_checked(self):
        payload = {'body': {'order': {'items': [{'pos_item_id': 'burger', 'modifiers': [
            {'pos_item_id': 'sauce', 'modifiers': [{}]}]}]}}}
        self.assertEqual(missing_plu_paths(payload), ['items[0].modifiers[0].modifiers[0].pos_item_id'])

    def test_present_identifiers_are_not_catalogue_guesses(self):
        self.assertEqual(missing_plu_paths({'body': {'order': {'items': [{'pos_item_id': 'not-in-local-catalogue'}]}}}), [])

    def test_sync_body_has_failure_reason_or_existing_success(self):
        tree = ast.parse(Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == '_send_sync_status')
        namespace = dict(os=os, urllib=__import__('urllib'), json=json, datetime=datetime,
                         timezone=timezone, _oauth_token=lambda: 'fake-test-token')
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<sync>', 'exec'), namespace)
        send = namespace['_send_sync_status']
        with patch.dict(os.environ, {'BECHEFAA_DELIVEROO_API_URL': 'https://api-sandbox.developers.deliveroo.com'}):
            for kwargs in ({}, {'status': 'failed', 'reason': 'pos_item_id_not_found', 'notes': 'Missing items[0].pos_item_id'}):
                with patch('urllib.request.urlopen', return_value=nullcontext(SimpleNamespace(status=200, read=lambda: b'{}'))) as mock:
                    self.assertEqual(send('fr:test', **kwargs)[0], 200)
                    req = mock.call_args.args[0]
                    body = json.loads(req.data)
                    self.assertIn('api-sandbox.developers.deliveroo.com', req.full_url)
                    self.assertEqual(body['status'], kwargs.get('status', 'succeeded'))
                    self.assertEqual(body['reason'], kwargs.get('reason'))
                    self.assertTrue(body['notes'])
                    self.assertTrue(body['occurred_at'].endswith('Z'))


if __name__ == '__main__': unittest.main()
