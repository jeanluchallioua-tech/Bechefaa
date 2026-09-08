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
            html = html.replace("COMPTOIR / EMPORTER", "SALLE")
            # Remplace directement le bloc client du ticket : une commande Salle doit afficher
            # la table, jamais l'ancien libellé Client comptoir/customer_name.
            if 'class="cclient"' in html:
                html = re.sub(r'<div class="cclient">.*?</div>', '<div class="cclient">' + label + '</div>', html, count=1, flags=re.S)
            if 'class="kclient"' in html:
                html = re.sub(r'<div class="kclient">.*?</div>', '<div class="kclient">' + label + '</div>', html, count=1, flags=re.S)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass
        return response
