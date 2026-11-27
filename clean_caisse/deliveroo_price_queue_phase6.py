"""Queue state transitions; no provider calls."""
TRANSITIONS = {
    "pending": {"submitted", "uncertain", "failed", "confirmed"},
    "submitted": {"confirmed", "uncertain", "failed"},
    "uncertain": {"confirmed", "failed"},
    "failed": {"pending", "confirmed"},
}

def transition(conn, product_id, revision, previous, next_state):
    if next_state not in TRANSITIONS.get(previous, set()):
        raise ValueError("Invalid price synchronization transition")
    row = conn.execute(
        """UPDATE deliveroo_price_sync_queue
           SET state=%s, updated_at=now()
           WHERE product_id=%s AND revision=%s AND state=%s
           RETURNING product_id""",
        (next_state, product_id, revision, previous),
    ).fetchone()
    return row is not None
