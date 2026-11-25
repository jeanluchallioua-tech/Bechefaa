"""Protect the current POS draft without writing a sale or payment."""
from flask import request


def register_active_cart_protection_phase6(app):
    @app.after_request
    def inject_active_cart_protection(response):
        if (request.path != '/pos' or response.status_code != 200
            or response.mimetype != 'text/html' or response.is_streamed):
            return response
        html = response.get_data(as_text=True)
        if 'pos-active-cart-protection' not in html:
            response.set_data(html.replace('</body>', '<script id="pos-active-cart-protection" src="/static/pos-active-cart.js?v=20261125" defer></script></body>', 1))
        return response
