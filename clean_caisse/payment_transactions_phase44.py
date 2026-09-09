"""Phase 4.4 — journal de transactions et socle remboursements BÉCHÉFAA.

PostgreSQL reste la source de vérité. Cette phase ajoute un journal financier
séparé des commandes afin de préparer paiements mixtes, SumUp, Stripe et
remboursements partiels/intégraux sans effacer l'historique d'origine.
"""
import time
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

CENT = Decimal("0.01")
EXTERNAL_PROVIDERS = {"SUMUP", "STRIPE"}


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def ensure_payment_transaction_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caisse_payment_transactions (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES caisse_orders(id) ON DELETE RESTRICT,
            transaction_type TEXT NOT NULL CHECK (transaction_type IN ('PAYMENT','REFUND')),
            provider TEXT NOT NULL DEFAULT 'LOCAL',
            method TEXT NOT NULL,
            amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
            status TEXT NOT NULL DEFAULT 'SUCCEEDED',
            external_reference TEXT NULL,
            parent_transaction_id TEXT NULL REFERENCES caisse_payment_transactions(id) ON DELETE RESTRICT,
            reason TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at BIGINT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_payment_tx_order ON caisse_payment_transactions(order_id,created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_payment_tx_provider_ref ON caisse_payment_transactions(provider,external_reference)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_payment_tx_parent ON caisse_payment_transactions(parent_transaction_id)")


def record_payment_transaction(conn, order_id, method, amount, *, provider="LOCAL", external_reference=None, created_by=""):
    ensure_payment_transaction_schema(conn)
    tx_id = "pay_" + uuid.uuid4().hex
    now = int(time.time() * 1000)
    conn.execute("""
        INSERT INTO caisse_payment_transactions
            (id,order_id,transaction_type,provider,method,amount,status,external_reference,created_by,created_at)
        VALUES (%s,%s,'PAYMENT',%s,%s,%s,'SUCCEEDED',%s,%s,%s)
    """, (tx_id, order_id, str(provider or "LOCAL").upper(), method, _money(amount), external_reference, created_by or "", now))
    return tx_id


def _summary(conn, order_id):
    ensure_payment_transaction_schema(conn)
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
            COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded,
            COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='PENDING_EXTERNAL' THEN amount ELSE 0 END),0) AS pending_refund
        FROM caisse_payment_transactions WHERE order_id=%s
    """, (order_id,)).fetchone()
    paid = _money(row["paid"])
    refunded = _money(row["refunded"])
    pending = _money(row["pending_refund"])
    return paid, refunded, pending


def register_payment_transactions_phase44(app, db, ensure_order_schema):
    @app.get("/api/orders/<order_id>/payment-transactions-phase44")
    def payment_transactions_phase44(order_id):
        try:
            with db() as conn:
                ensure_order_schema(conn)
                ensure_payment_transaction_schema(conn)
                conn.commit()
                order = conn.execute("SELECT id,num,total,payment_status FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                rows = conn.execute("""
                    SELECT id,transaction_type,provider,method,amount,status,external_reference,
                           parent_transaction_id,reason,created_by,created_at
                    FROM caisse_payment_transactions WHERE order_id=%s ORDER BY created_at,id
                """, (order_id,)).fetchall()
                paid, refunded, pending = _summary(conn, order_id)
            return jsonify({
                "ok": True,
                "order": {"id": order["id"], "num": order["num"], "total": float(order["total"]), "payment_status": order["payment_status"]},
                "summary": {"paid": float(paid), "refunded": float(refunded), "pending_refund": float(pending), "net_paid": float(paid-refunded)},
                "transactions": [dict(r) | {"amount": float(r["amount"])} for r in rows],
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Transactions indisponibles", "detail": str(exc)}), 500

    @app.post("/api/orders/<order_id>/refund-phase44")
    def refund_phase44(order_id):
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason") or "").strip()
        created_by = str(payload.get("created_by") or "").strip()
        parent_id = str(payload.get("transaction_id") or "").strip()
        if not parent_id:
            return jsonify({"ok": False, "error": "Transaction d'origine obligatoire"}), 400
        try:
            requested = _money(payload.get("amount"))
            if requested <= 0:
                return jsonify({"ok": False, "error": "Montant de remboursement invalide"}), 400
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    ensure_payment_transaction_schema(conn)
                    order = conn.execute("SELECT id,num,total,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    parent = conn.execute("""
                        SELECT id,provider,method,amount,status FROM caisse_payment_transactions
                        WHERE id=%s AND order_id=%s AND transaction_type='PAYMENT' FOR UPDATE
                    """, (parent_id, order_id)).fetchone()
                    if not parent or parent["status"] != "SUCCEEDED":
                        return jsonify({"ok": False, "error": "Paiement d'origine introuvable ou non validé"}), 404
                    already = conn.execute("""
                        SELECT COALESCE(SUM(amount),0) AS total FROM caisse_payment_transactions
                        WHERE parent_transaction_id=%s AND transaction_type='REFUND' AND status IN ('SUCCEEDED','PENDING_EXTERNAL')
                    """, (parent_id,)).fetchone()
                    refundable = _money(parent["amount"]) - _money(already["total"])
                    if requested > refundable:
                        return jsonify({"ok": False, "error": "Montant supérieur au solde remboursable", "refundable": float(refundable)}), 400

                    provider = str(parent["provider"] or "LOCAL").upper()
                    status = "PENDING_EXTERNAL" if provider in EXTERNAL_PROVIDERS else "SUCCEEDED"
                    tx_id = "ref_" + uuid.uuid4().hex
                    now = int(time.time() * 1000)
                    conn.execute("""
                        INSERT INTO caisse_payment_transactions
                            (id,order_id,transaction_type,provider,method,amount,status,parent_transaction_id,reason,created_by,created_at)
                        VALUES (%s,%s,'REFUND',%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (tx_id, order_id, provider, parent["method"], requested, status, parent_id, reason, created_by, now))

                    if status == "SUCCEEDED":
                        paid, refunded, _ = _summary(conn, order_id)
                        if refunded <= 0:
                            payment_status = "PAYÉE"
                        elif refunded >= paid:
                            payment_status = "REMBOURSÉE"
                        else:
                            payment_status = "PARTIELLEMENT REMBOURSÉE"
                        conn.execute("UPDATE caisse_orders SET payment_status=%s,updated_at=%s WHERE id=%s", (payment_status, now, order_id))
                    else:
                        payment_status = "REMBOURSEMENT EN ATTENTE"

            return jsonify({
                "ok": True,
                "refund_id": tx_id,
                "order_id": order_id,
                "amount": float(requested),
                "provider": provider,
                "status": status,
                "payment_status": payment_status,
                "external_action_required": provider in EXTERNAL_PROVIDERS,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Remboursement impossible", "detail": str(exc)}), 500
