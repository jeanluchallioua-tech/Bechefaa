"""Phase 6 — nettoyage contrôlé des commandes de recette Edenred UAT.

But: permettre de neutraliser une commande de test UAT partiellement payée
avant le Z, sans toucher aux ventes réelles. La neutralisation est autorisée
uniquement si tous les paiements réussis de la commande proviennent
d'EDENRED_EDPS et ont été créés par EDENRED_UAT.
"""
import os
import time
import uuid
from decimal import Decimal

from flask import jsonify


def _enabled():
    return str(os.getenv("BECHEFAA_EDENRED_ENABLED") or "").strip().lower() in {"1","true","yes","on"}


def _ensure_cleanup_schema(conn, ensure_order_schema):
    ensure_order_schema(conn)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancelled_at BIGINT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS original_operational_num BIGINT NULL")


def _eligible_orders(conn):
    return conn.execute("""
        SELECT
            o.id,o.num,o.customer_name,o.total,o.status,o.payment_status,
            COALESCE(o.paid_amount,0) AS paid_amount,o.fiscal_ticket_number,o.z_closure_id,
            COUNT(*) FILTER (
                WHERE t.transaction_type='PAYMENT' AND t.status='SUCCEEDED'
                  AND t.provider='EDENRED_EDPS' AND t.created_by='EDENRED_UAT'
            ) AS edenred_uat_payments,
            COUNT(*) FILTER (
                WHERE t.transaction_type='PAYMENT' AND t.status='SUCCEEDED'
                  AND NOT (t.provider='EDENRED_EDPS' AND t.created_by='EDENRED_UAT')
            ) AS other_success_payments
        FROM caisse_orders o
        LEFT JOIN caisse_payment_transactions t ON t.order_id=o.id
        WHERE COALESCE(o.cancellation_hidden,FALSE)=FALSE
          AND o.z_closure_id IS NULL
          AND UPPER(COALESCE(o.payment_status,''))='PARTIELLEMENT PAYÉE'
        GROUP BY o.id,o.num,o.customer_name,o.total,o.status,o.payment_status,
                 o.paid_amount,o.fiscal_ticket_number,o.z_closure_id
        HAVING COUNT(*) FILTER (
            WHERE t.transaction_type='PAYMENT' AND t.status='SUCCEEDED'
              AND t.provider='EDENRED_EDPS' AND t.created_by='EDENRED_UAT'
        ) > 0
        AND COUNT(*) FILTER (
            WHERE t.transaction_type='PAYMENT' AND t.status='SUCCEEDED'
              AND NOT (t.provider='EDENRED_EDPS' AND t.created_by='EDENRED_UAT')
        ) = 0
        ORDER BY MAX(o.created_at) DESC
    """).fetchall()


def register_edenred_uat_cleanup_phase6(app, db, ensure_order_schema):
    @app.get("/maintenance/edenred-uat/partial-orders-phase6")
    def edenred_uat_partial_orders_phase6():
        if not _enabled():
            return jsonify({"ok":False,"error":"Edenred UAT désactivé"}),403
        try:
            with db() as conn:
                _ensure_cleanup_schema(conn, ensure_order_schema)
                conn.commit()
                rows = _eligible_orders(conn)
            return jsonify({
                "ok":True,
                "environment":"UAT",
                "orders":[{
                    "id":r["id"],
                    "num":r["num"],
                    "customer_name":r["customer_name"],
                    "total":float(r["total"] or 0),
                    "paid_amount":float(r["paid_amount"] or 0),
                    "payment_status":r["payment_status"],
                    "status":r["status"],
                } for r in rows]
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"Diagnostic UAT impossible","detail":str(exc)}),500

    @app.post("/maintenance/edenred-uat/orders/<order_id>/neutralize-phase6")
    def edenred_uat_neutralize_phase6(order_id):
        if not _enabled():
            return jsonify({"ok":False,"error":"Edenred UAT désactivé"}),403
        now=int(time.time()*1000)
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_cleanup_schema(conn, ensure_order_schema)
                    order=conn.execute("""
                        SELECT id,num,total,status,payment_status,COALESCE(paid_amount,0) AS paid_amount,
                               fiscal_ticket_number,z_closure_id,cancellation_hidden
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """,(order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok":False,"error":"Commande introuvable"}),404
                    if order.get("z_closure_id") is not None:
                        return jsonify({"ok":False,"error":"Commande déjà clôturée par un Z"}),409
                    if order.get("fiscal_ticket_number") is not None:
                        return jsonify({"ok":False,"error":"Commande avec ticket fiscal : neutralisation UAT interdite"}),409
                    if order.get("cancellation_hidden"):
                        return jsonify({"ok":True,"already_neutralized":True,"id":order_id}),200
                    if str(order.get("payment_status") or "").upper() != "PARTIELLEMENT PAYÉE":
                        return jsonify({"ok":False,"error":"La commande n'est pas partiellement payée"}),409

                    payments=conn.execute("""
                        SELECT id,provider,method,amount,status,created_by,external_reference
                        FROM caisse_payment_transactions
                        WHERE order_id=%s AND transaction_type='PAYMENT' AND status='SUCCEEDED'
                        ORDER BY created_at,id
                        FOR UPDATE
                    """,(order_id,)).fetchall()
                    if not payments:
                        return jsonify({"ok":False,"error":"Aucun paiement à neutraliser"}),409
                    bad=[p for p in payments if not (
                        str(p.get("provider") or "").upper()=="EDENRED_EDPS"
                        and str(p.get("created_by") or "")=="EDENRED_UAT"
                    )]
                    if bad:
                        return jsonify({
                            "ok":False,
                            "error":"Neutralisation refusée : la commande contient un paiement autre qu'Edenred UAT."
                        }),409

                    refunded=Decimal("0.00")
                    for p in payments:
                        amount=Decimal(str(p["amount"]))
                        existing=conn.execute("""
                            SELECT id FROM caisse_payment_transactions
                            WHERE parent_transaction_id=%s AND transaction_type='REFUND'
                              AND status='SUCCEEDED' AND created_by='EDENRED_UAT_CLEANUP'
                            LIMIT 1
                        """,(p["id"],)).fetchone()
                        if existing:
                            refunded+=amount
                            continue
                        conn.execute("""
                            INSERT INTO caisse_payment_transactions
                                (id,order_id,transaction_type,provider,method,amount,status,
                                 external_reference,parent_transaction_id,reason,created_by,created_at)
                            VALUES (%s,%s,'REFUND','EDENRED_EDPS',%s,%s,'SUCCEEDED',
                                    %s,%s,%s,'EDENRED_UAT_CLEANUP',%s)
                        """,(
                            "ref_"+uuid.uuid4().hex,order_id,p["method"],amount,
                            p.get("external_reference"),p["id"],
                            "Neutralisation commande de recette Edenred UAT avant Z",now
                        ))
                        refunded+=amount

                    original_num=int(order["num"])
                    archive_row=conn.execute(
                        "SELECT COALESCE(MIN(num),0)-1 AS archive_num FROM caisse_orders WHERE num < 0"
                    ).fetchone()
                    archive_num=int(archive_row["archive_num"] or -1)
                    if archive_num >= 0:
                        archive_num=-1

                    conn.execute("""
                        UPDATE caisse_orders
                        SET status='ANNULÉE',
                            cancellation_hidden=TRUE,
                            original_operational_num=COALESCE(original_operational_num,%s),
                            num=%s,
                            cancelled_at=%s,
                            payment='ANNULÉE TEST UAT',
                            payment_status='REMBOURSÉE',
                            payment_method='TITRE RESTAURANT',
                            paid_amount=0,
                            updated_at=%s
                        WHERE id=%s
                    """,(original_num,archive_num,now,now,order_id))

            return jsonify({
                "ok":True,
                "environment":"UAT",
                "id":order_id,
                "original_num":original_num,
                "status":"ANNULÉE",
                "payment_status":"REMBOURSÉE",
                "refunded_uat_amount":float(refunded),
                "hidden_from_history":True,
                "z_unblocked_for_this_order":True,
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"Neutralisation UAT impossible","detail":str(exc)}),500
