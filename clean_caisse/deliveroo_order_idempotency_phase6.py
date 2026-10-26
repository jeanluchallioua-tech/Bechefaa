"""Deterministic external order key for Deliveroo sandbox integration.

Pure functions; no database writes. Database uniqueness must be enforced
before enabling any webhook-to-POS dispatch.
"""
import hashlib

from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError, _canonical_id


def external_order_key(order_id, environment="sandbox"):
    # Match the webhook parser: never collapse distinct external IDs by
    # trimming whitespace or accepting terminal control characters.
    order_id = _canonical_id(order_id, "Deliveroo order ID")
    if environment not in ("sandbox", "production"):
        raise DeliverooMappingError("Unknown Deliveroo environment")
    digest = hashlib.sha256(
        (environment + "\0" + order_id).encode("utf-8")
    ).hexdigest()
    return "deliveroo:" + environment + ":" + digest


def classify_replay(existing_order_id, incoming_order_id, environment="sandbox"):
    """Return create/replay without changing state.

    The caller must enforce a unique key transactionally in PostgreSQL.
    """
    # Validate the incoming ID and environment even when no previous
    # order exists; otherwise a malformed event could be classified "create".
    incoming_key = external_order_key(incoming_order_id, environment)
    if existing_order_id is None or existing_order_id == "":
        return "create"
    if external_order_key(existing_order_id, environment) == incoming_key:
        return "replay"
    return "conflict"
