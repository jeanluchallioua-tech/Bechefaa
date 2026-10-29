"""One sandbox stock POST, without redirects or retries; redacted transport evidence."""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlsplit

STOCK_URL = ('https://api-sandbox.developers.deliveroo.com/menu/v1/brands/'
             'bceaa87a-74db-434e-b548-6da7e7de67a6/menus/bechefaa-menu-01/item_unavailabilities/101')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_stock_once(url, token, payload):
    if url != STOCK_URL:
        raise ValueError('Only the fixed sandbox stock URL is permitted')
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=raw, method='POST', headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'Bechefaa-Deliveroo-Integration/1.0'})
    transport = {'revision': 'stock-transport-v1-20261029', 'method': req.get_method(),
                 'request_url': url, 'redirects_allowed': False, 'automatic_retries': 0,
                 'request_body_sha256': hashlib.sha256(raw).hexdigest(),
                 'sent_at_utc': datetime.now(timezone.utc).isoformat()}
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=35)
    except HTTPError as exc:
        response = exc
    with response as stream:
        status = int(stream.code)
        data = stream.read()
        effective = stream.geturl()
        headers = stream.headers
    transport.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                     effective_url=effective if effective == url else '[unexpected URL]',
                     url_unchanged=(effective == url), response_http_status=status,
                     response_content_type=headers.get('Content-Type', ''),
                     response_bytes=len(data), response_sha256=hashlib.sha256(data).hexdigest())
    # Do not expose arbitrary response headers, cookies, HTML, or redirect queries.
    if 300 <= status < 400:
        location = urlsplit(headers.get('Location', ''))
        transport['redirect_target_host'] = location.hostname
        transport['redirect_blocked'] = True
    try:
        body = json.loads(data.decode('utf-8')) if data else {}
    except (ValueError, UnicodeDecodeError):
        body = {'format': 'non_json', 'body_not_displayed': True}
    return status, body, transport
