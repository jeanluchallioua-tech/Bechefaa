"""Status checks for signed Deliveroo order update webhooks. No I/O."""

CANCELLED_STATUSES = {"canceled", "cancelled"}


def order_status_and_log(payload):
    if not isinstance(payload, dict) or str(payload.get("event") or "").lower() != "order.status_update":
        return "", []
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    order = body.get("order") if isinstance(body.get("order"), dict) else {}
    log = order.get("status_log") or body.get("status_log") or []
    log = log if isinstance(log, list) else []
    for node in (order, body):
        for key in ("status", "order_status", "state"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower(), log
    latest = log[-1] if log and isinstance(log[-1], dict) else {}
    return str(latest.get("status") or latest.get("order_status") or latest.get("state") or "").lower(), log


def cancellation_ready(payload):
    status, log = order_status_and_log(payload)
    return status in CANCELLED_STATUSES and any(
        isinstance(entry, dict)
        and str(entry.get("status") or entry.get("order_status") or entry.get("state") or "").lower() in CANCELLED_STATUSES
        for entry in log
    )


def should_sync_order(payload, order_id, accepted_log):
    if not order_id or str(payload.get("event") or "").lower() != "order.status_update":
        return False
    status, _ = order_status_and_log(payload)
    # An old accepted entry must not acknowledge a cancellation prematurely.
    if status in CANCELLED_STATUSES:
        return cancellation_ready(payload)
    return bool(accepted_log)
