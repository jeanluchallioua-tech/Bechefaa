"""Phase 3.6 — affichage Table X sur les tickets Salle.

Correctif isolé : enrichit le rendu HTML des tickets existants sans toucher aux calculs fiscaux.
"""
import re
from flask import request


def register_table_print_phase36(app, db):
    @app.after_request
    def table_print_phase36(response):
        path = request.path
        if response.status_code != 200 or response.mimetype != "text/html":
            return response
        if not (path.startswith("/impression/client/") or path.startswith("/impression/cuisine/")):
            return response
        order_id = path.rsplit("/", 1)[-1]
        try:
            with db() as conn:
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")
                conn.commit()
                row = conn.execute("SELECT table_number, table_label FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
            if not row or not row.get("table_number"):
                return response
            label = row.get("table_label") or f"Table {row['table_number']}"
            html = response.get_data(as_text=True)
            # Le mode du ticket devient SALLE et le nom comptoir devient Table X.
            html = html.replace("COMPTOIR / EMPORTER", "SALLE")
            html = html.replace("Client comptoir", label)
            # Si un ancien customer_name a été conservé sur une commande Salle, la table reste
            # explicitement visible sous le numéro de commande.
            if label not in html:
                if 'class="cnum"' in html:
                    html = re.sub(r'(</div>)(<div class="cclient")', r'\1<div class="cclient">' + label + r'</div>\2', html, count=1)
                elif 'class="knum"' in html:
                    html = re.sub(r'(</div>)(<div class="kclient")', r'\1<div class="kclient">' + label + r'</div>\2', html, count=1)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass
        return response
