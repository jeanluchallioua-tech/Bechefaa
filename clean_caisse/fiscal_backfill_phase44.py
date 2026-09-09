"""Phase 4.4 — régularisation ponctuelle des tickets comptables de test.

Réattribue une séquence 1..N à toutes les commandes payées visibles, dans
l'ordre chronologique de paiement (puis création/id en repli), et synchronise
la séquence TICKET. Outil de développement à exécuter une seule fois.
"""
from flask import Response, jsonify


def register_fiscal_backfill_phase44(app, db, ensure_order_schema):
    @app.get("/maintenance/phase44/fiscal-backfill")
    def fiscal_backfill_page_phase44():
        body = '''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Régularisation tickets comptables</title>
<style>
body{font-family:Arial,sans-serif;background:#f4f5f7;padding:30px;color:#17191c}
.card{max-width:720px;margin:auto;background:#fff;padding:26px;border-radius:14px;box-shadow:0 2px 10px rgba(0,0,0,.08)}
h1{margin-top:0}.warn{background:#fff4e5;padding:14px;border-radius:10px;margin:18px 0}
button{width:100%;padding:15px;border:0;border-radius:10px;background:#143D53;color:#fff;font-weight:900;font-size:16px;cursor:pointer}
a{color:#143D53}
</style>
</head>
<body>
<div class="card">
<h1>Régularisation des tickets comptables</h1>
<p>Cet outil est réservé aux données de test avant mise en production.</p>
<p>Il attribuera un numéro comptable continu à toutes les commandes déjà payées, dans l'ordre chronologique d'encaissement.</p>
<div class="warn"><b>À exécuter une seule fois.</b> La numérotation des commandes opérationnelles ne sera pas modifiée.</div>
<form method="post">
<button type="submit">RÉGULARISER LES TICKETS COMPTABLES</button>
</form>
<p style="margin-top:18px"><a href="/historique">Retour à l'historique</a></p>
</div>
</body>
</html>'''
        return Response(body, content_type="text/html; charset=utf-8")

    @app.post("/maintenance/phase44/fiscal-backfill")
    def fiscal_backfill_phase44():
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS fiscal_ticket_number BIGINT NULL")
                    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS fiscal_ticket_issued_at BIGINT NULL")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS caisse_fiscal_sequences (
                            sequence_name TEXT PRIMARY KEY,
                            last_number BIGINT NOT NULL DEFAULT 0
                        )
                    """)
                    rows = conn.execute("""
                        SELECT id,num,paid_at,created_at
                        FROM caisse_orders
                        WHERE COALESCE(cancellation_hidden,FALSE)=FALSE
                          AND (
                            COALESCE(paid_amount,0) > 0
                            OR UPPER(COALESCE(payment_status,'')) IN
                               ('PAYÉE','PAYEE','PARTIELLEMENT REMBOURSÉE','PARTIELLEMENT REMBOURSEE','REMBOURSÉE','REMBOURSEE')
                          )
                        ORDER BY COALESCE(paid_at,created_at) ASC, created_at ASC, id ASC
                        FOR UPDATE
                    """).fetchall()

                    # Libère d'abord l'index unique avant de réattribuer 1..N.
                    conn.execute("UPDATE caisse_orders SET fiscal_ticket_number=NULL WHERE fiscal_ticket_number IS NOT NULL")
                    result=[]
                    for index,row in enumerate(rows, start=1):
                        issued_at = row.get('paid_at') or row.get('created_at')
                        conn.execute("""
                            UPDATE caisse_orders
                            SET fiscal_ticket_number=%s,
                                fiscal_ticket_issued_at=COALESCE(fiscal_ticket_issued_at,%s)
                            WHERE id=%s
                        """, (index, issued_at, row['id']))
                        result.append({'order_num': int(row['num']), 'ticket': index})

                    conn.execute("""
                        INSERT INTO caisse_fiscal_sequences(sequence_name,last_number)
                        VALUES ('TICKET',%s)
                        ON CONFLICT (sequence_name)
                        DO UPDATE SET last_number=EXCLUDED.last_number
                    """, (len(rows),))

            rows_html = ''.join(
                f'<li>Commande #{item["order_num"]} → Ticket comptable #{item["ticket"]}</li>'
                for item in result
            ) or '<li>Aucune commande payée trouvée.</li>'
            body = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Régularisation terminée</title>
<style>body{{font-family:Arial,sans-serif;background:#f4f5f7;padding:30px;color:#17191c}}.card{{max-width:720px;margin:auto;background:#fff;padding:26px;border-radius:14px}}a{{color:#143D53;font-weight:700}}</style>
</head><body><div class="card"><h1>Régularisation terminée</h1><p><b>{len(result)}</b> commande(s) payée(s) numérotée(s).</p><ul>{rows_html}</ul><p>Prochain ticket comptable : <b>#{len(result)+1}</b></p><p><a href="/historique">Retour à l'historique</a></p></div></body></html>'''
            return Response(body, content_type="text/html; charset=utf-8")
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Régularisation impossible', 'detail': str(exc)}), 500
