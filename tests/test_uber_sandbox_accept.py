import copy
import time
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from flask import Flask

from clean_caisse.uber_sandbox_accept import claim_attempt, notified_orders, manager_status
from clean_caisse.uber_sandbox_link import STORE_ID, CLIENT_ID, UberFailure
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6

ORDER = 'd65e5495-7aeb-4e2e-abe6-92b2e7a1e6fe'
M = 'clean_caisse.uber_sandbox_accept'


class ManualAcceptTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        app = Flask(__name__)
        app.secret_key = 'test-only'
        register_uber_webhook_phase6(app, self.db)
        self.client = app.test_client()
        with self.client.session_transaction() as s:
            s['caisse_auth'] = True
            s['uber_sandbox_csrf'] = 'csrf'
        self.ids = patch(M + '.notified_orders', return_value=[ORDER]).start()
        self.manager = patch(M + '.manager_status', return_value=True).start()
        self.token = patch(M + '.get_token', return_value='private-token').start()
        self.api = patch(M + '.call_uber').start()
        self.claim = patch(M + '.claim_attempt', return_value=True).start()
        self.ack = patch(M + '.save_ack').start()
        self.addCleanup(patch.stopall)
        self.raw = {'id': ORDER, 'display_id': '1E6FE', 'store': {'id': STORE_ID},
            'current_state': 'CREATED', 'order_manager_client_id': CLIENT_ID,
            'cart': {'items': [{'id': 'product', 'title': 'Tender <script>unsafe</script>',
                'quantity': 1, 'price': {'total_price': {'amount':1980,'currency_code':'EUR'}},
                'selected_modifier_groups': [{'selected_items': [
                    {'id':'choice', 'title':'10 pièces', 'quantity':1}]}]}]},
            'payment': {'charges': {'total':{'amount':1980,'currency_code':'EUR'}}},
            'eater': {'phone':'secret-phone'}}
        self.api.return_value = self.raw
        self.path = '/administration/uber-sandbox/orders'

    def preview(self):
        response = self.client.get(self.path)
        with self.client.session_transaction() as s:
            p = s.get('uber_sandbox_accept_preview')
        return response, p

    def submit(self, p=None):
        if p is None:
            _, p = self.preview()
        return self.client.post(self.path, data={'csrf':'csrf','nonce':p['nonce'], 'order_id':ORDER})

    def test_get_shows_readonly_preview_and_escapes_content(self):
        response, preview = self.preview()
        self.assertEqual(response.status_code, 200)
        self.assertIn('10 pièces', response.text)
        self.assertIn('19,80 EUR', response.text)
        self.assertIn('&lt;script&gt;', response.text)
        self.assertNotIn('secret-phone', response.text)
        self.assertIn('Accepter cette commande test', response.text)
        self.assertEqual(preview['store_id'], STORE_ID)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.api.assert_called_once_with('https://test-api.uber.com/v2/eats/order/' + ORDER,
            method='GET', token='private-token', response_limit=4*1024*1024)
        self.claim.assert_not_called()
        self.ack.assert_not_called()
        self.db.assert_not_called()

    def test_accept_requires_fresh_read_and_durable_claim_before_post(self):
        log = []
        self.claim.side_effect = lambda *_: log.append('claim') or True
        def call(url, **kwargs):
            log.append(kwargs['method'])
            return copy.deepcopy(self.raw) if kwargs['method'] == 'GET' else {}
        self.api.side_effect = call
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(log, ['GET', 'GET', 'claim', 'POST'])
        self.assertIn('Uber a reçu la demande', response.text)
        self.assertNotIn('private-token', response.text)
        self.token.assert_called_with('client_credentials', scope='eats.order')
        self.api.assert_called_with('https://test-api.uber.com/v1/eats/orders/' + ORDER + '/accept_pos_order',
            method='POST',token='private-token',body={'reason':'Acceptation manuelle — test sandbox BECHEFAA'})
        self.ack.assert_called_once_with(self.db, ORDER)
        self.assertEqual(self.api.call_count, 3)

    def test_no_network_or_database_without_session_csrf_and_preview(self):
        self.assertEqual(self.client.post(self.path).status_code, 403)
        self.assertEqual(self.client.post(self.path, data={'csrf':'csrf'}).status_code, 409)
        with self.client.session_transaction() as s:
            s.clear()
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.ids.assert_not_called()
        self.api.assert_not_called()
        self.db.assert_not_called()

    def test_expired_wrong_store_or_order_preview_is_rejected(self):
        for field, value in [('created',time.time()-181), ('store_id','other'), ('order_id','other')]:
            _, p = self.preview()
            with self.client.session_transaction() as s:
                changed = dict(s['uber_sandbox_accept_preview'])
                changed[field] = value
                s['uber_sandbox_accept_preview'] = changed
            self.api.reset_mock()
            self.assertEqual(self.submit(p).status_code,409)
            self.api.assert_not_called()
        self.claim.assert_not_called()

    def test_canceled_changed_or_different_manager_order_cannot_be_accepted(self):
        for field, value in [('current_state','DENIED'),('order_manager_client_id','other'),('store',{'id':'other'})]:
            self.api.return_value = copy.deepcopy(self.raw)
            _, p = self.preview()
            changed = copy.deepcopy(self.raw)
            changed[field] = value
            self.api.return_value = changed
            self.api.reset_mock()
            response = self.submit(p)
            self.assertIn(response.status_code, (409,503))
            self.assertTrue(all(c.kwargs['method']=='GET' for c in self.api.call_args_list))
        self.claim.assert_not_called()

    def test_changed_prices_require_new_preview(self):
        _, p = self.preview()
        changed = copy.deepcopy(self.raw)
        changed['payment']['charges']['total']['amount'] = 9999
        self.api.return_value = changed
        self.assertEqual(self.submit(p).status_code,409)
        self.claim.assert_not_called()

    def test_notification_and_manager_rechecked_at_submit(self):
        _, p = self.preview()
        self.ids.return_value = []
        self.assertEqual(self.submit(p).status_code,404)
        self.ids.return_value = [ORDER]
        _, p = self.preview()
        self.manager.return_value = False
        self.assertEqual(self.submit(p).status_code,409)
        self.claim.assert_not_called()

    def test_replay_and_duplicate_claim_never_send_second_acceptance(self):
        _, p = self.preview()
        self.assertEqual(self.submit(p).status_code,200)
        self.api.reset_mock()
        self.assertEqual(self.submit(p).status_code,409)
        self.api.assert_not_called()
        self.claim.return_value = False
        _, p = self.preview()
        self.api.reset_mock()
        self.assertEqual(self.submit(p).status_code,409)
        self.assertEqual(self.api.call_count,1)
        self.assertEqual(self.api.call_args.kwargs['method'],'GET')

    def test_timeout_after_post_does_not_retry_and_remains_uncertain(self):
        _, p = self.preview()
        self.api.side_effect = [self.raw,UberFailure('Réponse Uber indisponible.')]
        response = self.submit(p)
        self.assertEqual(response.status_code,502)
        self.assertIn('Ne la renvoyez pas',response.text)
        self.assertNotIn('Aucune acceptation envoyée.',response.text)
        self.ack.assert_not_called()
        self.assertEqual(self.api.call_args.kwargs['method'],'POST')

    def test_missing_manager_exposes_explicit_authorization_not_auto_accept(self):
        self.manager.return_value = False
        response, p = self.preview()
        self.assertIsNone(p)
        self.assertIn('Autoriser la gestion du restaurant test',response.text)
        self.assertNotIn('Accepter cette commande test chez Uber',response.text)


class SandboxAcceptanceDatabaseTests(unittest.TestCase):
    def test_unique_attempt_is_committed_even_when_already_claimed(self):
        db = MagicMock()
        conn = db.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        for row, expected in [(None,False),({'order_id':ORDER},True)]:
            cur.fetchone.return_value = row
            self.assertEqual(claim_attempt(db, ORDER), expected)
        sql, params = cur.execute.call_args.args
        self.assertIn('ON CONFLICT (order_id) DO NOTHING', sql)
        self.assertEqual(params,(ORDER,STORE_ID))
        self.assertEqual(conn.commit.call_count,2)
        self.assertTrue(all('uber_sandbox_accept_attempts' in c.args[0] for c in cur.execute.call_args_list))

    def test_notification_list_filters_fixed_store_without_any_write(self):
        db = MagicMock()
        conn = db.return_value.__enter__.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = {'inbox_exists':True}
        cur.fetchall.return_value = [(ORDER,),(ORDER,),('invalid',)]
        self.assertEqual(notified_orders(db),[ORDER])
        sql, params = cur.execute.call_args.args
        self.assertEqual(params,(STORE_ID,))
        self.assertIn("event_type = 'orders.notification'",sql)
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in cur.execute.call_args_list))
        conn.commit.assert_not_called()

    def test_pending_inactive_wrong_store_and_redacted_manager_fail_closed(self):
        for changed in ({'is_order_manager_pending':True},{'integration_enabled':False},
                        {'order_manager_client_id':'redacted'},{'store_id':'other'}):
            details={'store_id':STORE_ID,'integration_enabled':True,'order_manager_client_id':CLIENT_ID}
            details.update(changed)
            with patch(M+'.get_token'), patch(M+'.call_uber',return_value=details):
                if changed.get('store_id'):
                    with self.assertRaises(UberFailure): manager_status()
                else:
                    self.assertFalse(manager_status())


if __name__ == '__main__': unittest.main()
