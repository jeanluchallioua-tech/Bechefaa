"""Phase 4.4 — identité restaurant sur ticket client.

Couche isolée : ne modifie pas printing_phase1.py. Le ticket cuisine reste
strictement inchangé. Les données proviennent de caisse_restaurant_settings.
"""
from html import escape
from flask import request


def register_restaurant_ticket_identity_phase44(app, db):
    def load_identity():
        try:
            with db() as conn:
                rows = conn.execute("SELECT setting_key,setting_value FROM caisse_restaurant_settings").fetchall()
            return {r["setting_key"]: (r["setting_value"] or "") for r in rows}
        except Exception:
            return {}

    @app.after_request
    def restaurant_ticket_identity_after_phase44(response):
        if not request.path.startswith('/impression/client/') or response.status_code != 200 or response.mimetype != 'text/html':
            return response
        cfg = load_identity()
        name = str(cfg.get('name') or 'BÉCHÉFAA').strip()
        details = []
        address = str(cfg.get('address') or '').strip()
        cp = str(cfg.get('postal_code') or '').strip()
        city = str(cfg.get('city') or '').strip()
        locality = ' '.join(x for x in (cp, city) if x)
        if address: details.append(escape(address))
        if locality: details.append(escape(locality))
        phone = str(cfg.get('phone') or '').strip()
        email = str(cfg.get('email') or '').strip()
        siret = str(cfg.get('siret') or '').strip()
        vat = str(cfg.get('vat_number') or '').strip()
        if phone: details.append('Tél. ' + escape(phone))
        if email: details.append(escape(email))
        if siret: details.append('SIRET ' + escape(siret))
        if vat: details.append('TVA ' + escape(vat))
        html = response.get_data(as_text=True)
        html = html.replace('<div class="ctitle">BÉCHÉFAA</div>', '<div class="ctitle">' + escape(name) + '</div>', 1)
        if details:
            block = '<div class="restaurant-identity-phase44" style="text-align:center;font-size:10px;line-height:1.25;margin:3px 0 6px">' + '<br>'.join(details) + '</div>'
            html = html.replace('<div class="sep"></div>', block + '<div class="sep"></div>', 1)
        response.set_data(html)
        return response
