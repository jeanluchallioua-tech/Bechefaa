"""Preproduction-only POS notice persistence. No order, payment or print writes."""
import os
from pathlib import Path


def replace_deliveroo_poller(html):
    start = html.find('async function checkDeliveroo(){')
    end_marker = 'checkDeliveroo();setInterval(checkDeliveroo,5000);'
    end = html.find(end_marker, start)
    if start < 0 or end < 0:
        return html
    script = Path(__file__).with_name('static').joinpath('deliveroo-notice-preprod.js').read_text()
    return html[:start] + script + html[end + len(end_marker):]


def register_deliveroo_notice_preprod_phase6(app):
    from flask import request

    @app.after_request
    def deliveroo_notice_preprod(response):
        if (os.environ.get('CC_APP_ID', '').strip() != 'app_fad0809f-954d-47e7-983d-afb7c3867cd0'
                or request.path != '/pos' or response.status_code != 200 or response.mimetype != 'text/html'):
            return response
        html = response.get_data(as_text=True)
        patched = replace_deliveroo_poller(html)
        if patched != html:
            response.set_data(patched)
            response.content_length = len(response.get_data())
        return response
