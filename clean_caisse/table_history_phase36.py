"""Phase 3.6 — affichage Table X dans l'historique."""
from flask import request


def register_table_history_phase36(app):
    @app.after_request
    def table_history_phase36(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        try:
            html = response.get_data(as_text=True)
            old = "#${esc(o.num)} · ${esc(o.customer_name)} </div><div class=\"meta\">${esc(o.status)} · ${esc(o.ticket_type)} · ${money(o.total)}"
            new = "#${esc(o.num)} · ${esc(o.table_label||o.customer_name)} </div><div class=\"meta\">${esc(o.status)} · ${esc(o.table_number?'Salle':o.ticket_type)} · ${money(o.total)}"
            if old in html:
                html = html.replace(old, new, 1)
            # La recherche doit également retrouver Table X.
            old_search = "String(o.customer_name||'').toLowerCase().includes(q)"
            new_search = "String(o.customer_name||'').toLowerCase().includes(q)||String(o.table_label||'').toLowerCase().includes(q)"
            html = html.replace(old_search, new_search, 1)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass
        return response
