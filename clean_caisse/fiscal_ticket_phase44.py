"""Phase 4.4 — numérotation comptable continue à l'encaissement.

Le numéro de commande reste opérationnel et immuable. Le numéro de ticket
comptable est attribué une seule fois, uniquement quand l'encaissement est
validé. La séquence est centralisée dans PostgreSQL et verrouillée en
transaction pour éviter les doublons en cas d'encaissements concurrents.
"""


def ensure_fiscal_ticket_schema(conn, ensure_order_schema):
    ensure_order_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caisse_fiscal_sequences (
            sequence_name TEXT PRIMARY KEY,
            last_number BIGINT NOT NULL DEFAULT 0
        )
    """)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS fiscal_ticket_number BIGINT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS fiscal_ticket_issued_at BIGINT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_caisse_orders_fiscal_ticket_number ON caisse_orders(fiscal_ticket_number) WHERE fiscal_ticket_number IS NOT NULL")


def allocate_fiscal_ticket_number(conn, ensure_order_schema, order_id, issued_at):
    """Attribue un numéro comptable une seule fois et retourne ce numéro."""
    ensure_fiscal_ticket_schema(conn, ensure_order_schema)

    order = conn.execute(
        "SELECT fiscal_ticket_number FROM caisse_orders WHERE id=%s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if not order:
        raise ValueError("Commande introuvable")
    if order.get("fiscal_ticket_number") is not None:
        return int(order["fiscal_ticket_number"])

    conn.execute("""
        INSERT INTO caisse_fiscal_sequences(sequence_name,last_number)
        VALUES ('TICKET',0)
        ON CONFLICT (sequence_name) DO NOTHING
    """)
    seq = conn.execute(
        "SELECT last_number FROM caisse_fiscal_sequences WHERE sequence_name='TICKET' FOR UPDATE"
    ).fetchone()
    next_number = int(seq["last_number"] or 0) + 1
    conn.execute(
        "UPDATE caisse_fiscal_sequences SET last_number=%s WHERE sequence_name='TICKET'",
        (next_number,),
    )
    conn.execute("""
        UPDATE caisse_orders
        SET fiscal_ticket_number=%s, fiscal_ticket_issued_at=%s
        WHERE id=%s
    """, (next_number, issued_at, order_id))
    return next_number
