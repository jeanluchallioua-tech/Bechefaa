"""Phase 4.4 — régularisation ponctuelle des tickets comptables de test.

Réattribue une séquence 1..N à toutes les commandes payées visibles, dans
l'ordre chronologique de paiement (puis création/id en repli), et synchronise
la séquence TICKET. Outil de développement à exécuter une seule fois.
"""
from flask import jsonify


def register_fiscal_backfill_phase44(app, db, ensure_order_schema):
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
            return jsonify({'ok': True, 'count': len(result), 'tickets': result, 'next_ticket': len(result)+1})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Régularisation impossible', 'detail': str(exc)}), 500
