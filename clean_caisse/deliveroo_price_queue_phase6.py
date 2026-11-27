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


def confirm_observed_prices(conn, snapshot_rows, verification):
    """Confirm only the captured revisions after a complete remote match."""
    if verification.get("prices_confirmed") is not True:
        return 0
    count = 0
    for row in snapshot_rows:
        if row["state"] in ("pending", "submitted", "uncertain", "failed"):
            count += int(transition(conn, row["product_id"], row["revision"],
                                    row["state"], "confirmed"))
    return count
