"""Phase 4.4 — activation de la garde complément d'encaissement.

Le module validé payment_topup_guard_isolated_phase44 devient la garde active
sans modifier le moteur d'encaissement ni le WSGI.
"""

from clean_caisse.payment_topup_guard_isolated_phase44 import (
    register_payment_topup_guard_isolated_phase44,
)


def register_payment_refund_guard_phase44(app, db):
    return register_payment_topup_guard_isolated_phase44(app, db)
