"""Nettoyage sélectif avant mise en service réelle.

Conserve:
- toute commande avec paiement CB/carte confirmé;
- toute commande déjà rattachée à une clôture Z;
- toutes les transactions liées aux commandes conservées.

Supprime uniquement les commandes de test non protégées et leurs lignes/transactions.
Ne touche jamais aux réglages, clients, catalogue, notifications, matériel, PIN ou Z.
"""
from flask import jsonify, request

CONFIRMATION = "NETTOYAGE_TESTS_SANS_TOUCHER_CB"
CARD_WORDS = ("CB", "CARTE", "CARD", "VISA", "MASTERCARD")


def _has_column(conn, table, column):
    row = conn.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name=%s AND column_name=%s""",
        (table, column),
    ).fetchone()
    return bool(row)


def _protected_order_ids(conn):
    payment_method_exists = _has_column(conn, "caisse_orders", "payment_method")
    z_exists = _has_column(conn, "caisse_orders", "z_closure_id")
    method_expr = "COALESCE(o.payment_method,'')" if payment_method_exists else "''"
    z_expr = "o.z_closure_id IS NOT NULL" if z_exists else "FALSE"

    params = []
    clauses = []
    for word in CARD_WORDS:
        clauses.append(
            "(UPPER(COALESCE(o.payment,'')) LIKE %s OR "
            f"UPPER({method_expr}) LIKE %s)"
        )
        params.extend([f"%{word}%", f"%{word}%"])
    card_text = " OR ".join(clauses) if clauses else "FALSE"

    tx_exists = conn.execute(
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema='public' AND table_name='caisse_payment_transactions'"""
    ).fetchone()
    tx_card = "FALSE"
    if tx_exists:
        # Sécurité maximale : dès qu'une transaction financière existe pour
        # une commande (paiement ou remboursement, réussi ou en attente),
        # la commande et tout son historique sont conservés.
        tx_card = """EXISTS (
            SELECT 1 FROM caisse_payment_transactions t
            WHERE t.order_id=o.id
        )"""

    rows = conn.execute(
        f"""SELECT o.id FROM caisse_orders o
            WHERE ({z_expr}) OR ({tx_card}) OR ({card_text})""",
        tuple(params),
    ).fetchall()
    return {str(r["id"]) for r in rows}


def _preview(conn):
    protected = _protected_order_ids(conn)
    rows = conn.execute(
        """SELECT id,num,total,payment,status,created_at
           FROM caisse_orders ORDER BY created_at,num"""
    ).fetchall()
    keep, delete = [], []
    for r in rows:
        item = {
            "id": str(r["id"]),
            "num": r["num"],
            "total": float(r["total"] or 0),
            "payment": r["payment"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        (keep if str(r["id"]) in protected else delete).append(item)
    return {
        "keep_count": len(keep),
        "keep_total": round(sum(x["total"] for x in keep), 2),
        "delete_count": len(delete),
        "delete_total": round(sum(x["total"] for x in delete), 2),
        "kept_orders": keep,
        "deleted_candidates": delete,
        "notifications_preserved": True,
        "notification_settings_preserved": True,
        "z_preserved": True,
    }


def register_selective_reset_phase6(app, db):
    @app.get("/api/maintenance/selective-reset-phase6/preview")
    def selective_reset_preview_phase6():
        try:
            with db() as conn:
                return jsonify({"ok": True, **_preview(conn)})
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Aperçu du nettoyage sélectif indisponible",
                "detail": str(exc),
            }), 500

    @app.post("/api/maintenance/selective-reset-phase6")
    def selective_reset_execute_phase6():
        payload = request.get_json(silent=True) or {}
        if str(payload.get("confirmation") or "").strip() != CONFIRMATION:
            return jsonify({"ok": False, "error": "Phrase de confirmation incorrecte"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(20260929)")
                    before = _preview(conn)
                    protected = _protected_order_ids(conn)
                    all_rows = conn.execute("SELECT id FROM caisse_orders").fetchall()
                    delete_ids = [str(r["id"]) for r in all_rows if str(r["id"]) not in protected]

                    deleted_tx = deleted_items = deleted_orders = 0
                    if delete_ids:
                        has_tx = conn.execute(
                            """SELECT 1 FROM information_schema.tables
                               WHERE table_schema='public' AND table_name='caisse_payment_transactions'"""
                        ).fetchone()
                        if has_tx:
                            row = conn.execute(
                                "SELECT COUNT(*) AS n FROM caisse_payment_transactions WHERE order_id = ANY(%s)",
                                (delete_ids,),
                            ).fetchone()
                            deleted_tx = int(row["n"] or 0)
                            conn.execute(
                                "DELETE FROM caisse_payment_transactions WHERE order_id = ANY(%s)",
                                (delete_ids,),
                            )

                        row = conn.execute(
                            "SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id = ANY(%s)",
                            (delete_ids,),
                        ).fetchone()
                        deleted_items = int(row["n"] or 0)
                        conn.execute("DELETE FROM caisse_order_items WHERE order_id = ANY(%s)", (delete_ids,))

                        row = conn.execute(
                            "SELECT COUNT(*) AS n FROM caisse_orders WHERE id = ANY(%s)",
                            (delete_ids,),
                        ).fetchone()
                        deleted_orders = int(row["n"] or 0)
                        conn.execute("DELETE FROM caisse_orders WHERE id = ANY(%s)", (delete_ids,))

                    after = _preview(conn)

            return jsonify({
                "ok": True,
                "message": "Nettoyage sélectif terminé",
                "before": before,
                "deleted": {
                    "orders": deleted_orders,
                    "items": deleted_items,
                    "payment_transactions": deleted_tx,
                },
                "after": after,
                "notifications_preserved": True,
            })
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Nettoyage sélectif impossible",
                "detail": str(exc),
            }), 500
