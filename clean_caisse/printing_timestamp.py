"""Complément Phase 1 : date/heure de la commande sur les tickets 80 mm."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import request


def register_printing_timestamp(app, db):
    @app.after_request
    def inject_order_datetime(response):
        path = request.path or ""
        if not (path.startswith("/impression/client/") or path.startswith("/impression/cuisine/")):
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response
        order_id = path.rsplit("/", 1)[-1]
        try:
            with db() as conn:
                row = conn.execute("SELECT created_at FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
            if not row:
                return response
            created_ms = int(row["created_at"])
            stamp = datetime.fromtimestamp(created_ms / 1000, tz=ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y • %H:%M")
            html = response.get_data(as_text=True)
            marker = '<div class="sep"></div><div class="center big">'
            html = html.replace(marker, f'<div class="center muted">{stamp}</div><div class="sep"></div><div class="center big">', 1)
            response.set_data(html)
            response.content_length = len(response.get_data())
        except Exception:
            pass
        return response
