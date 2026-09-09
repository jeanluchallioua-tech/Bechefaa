"""Phase 4.4 — compatibilité Z avec les commandes annulées.

Correction isolée sans modifier cash_z_phase35.py :
- ANNULÉE ne bloque plus l'état du Z ;
- ANNULÉE n'est pas visible dans le compteur opérationnel du Z ;
- ANNULÉE reste en base et est verrouillée avec la journée ;
- ANNULÉE est exclue du CA, des totaux et du nombre de commandes commerciales du Z ;
- le comptage espèces définitif est exigé et rattaché au Z dans la même transaction.
"""
import json
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from flask import jsonify

PARIS = ZoneInfo("Europe/Paris")
TERMINAL_STATUSES = {"TERMINÉE", "TERMINEE"}
CANCELLED_STATUSES = {"ANNULÉE", "ANNULEE"}


def _norm_status(value):
    return str(value or "").strip().upper()


def _fallback_tax(ttc):
    total = Decimal(str(ttc or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ht = (total / Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ht, (total - ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), total


def _snapshot(rows):
    ht = Decimal("0.00")
    tax = Decimal("0.00")
    ttc = Decimal("0.00")
    payments = {}
    for row in rows:
        fht, ftax, fttc = _fallback_tax(row.get("total"))
        rh = Decimal(str(row.get("total_ht") if row.get("total_ht") is not None else fht))
        rt = Decimal(str(row.get("tax_amount") if row.get("tax_amount") is not None else ftax))
        rc = Decimal(str(row.get("total_ttc") if row.get("total_ttc") is not None else fttc))
        ht += rh
        tax += rt
        ttc += rc
        p = str(row.get("payment") or "À ENCAISSER")
        payments[p] = payments.get(p, Decimal("0.00")) + rc
    nums = [int(r["num"]) for r in rows]
    return {
        "count": len(rows),
        "first": min(nums) if nums else None,
        "last": max(nums) if nums else None,
        "ht": ht.quantize(Decimal("0.01")),
        "tax": tax.quantize(Decimal("0.01")),
        "ttc": ttc.quantize(Decimal("0.01")),
        "payments": payments,
    }


def _ensure_z_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_z_closures (
        id BIGSERIAL PRIMARY KEY,
        business_date TEXT NOT NULL UNIQUE,
        closed_at BIGINT NOT NULL,
        first_order_num BIGINT NULL,
        last_order_num BIGINT NULL,
        order_count INTEGER NOT NULL DEFAULT 0,
        total_ht NUMERIC(12,2) NOT NULL DEFAULT 0,
        tax_rate NUMERIC(6,3) NOT NULL DEFAULT 10,
        tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
        total_ttc NUMERIC(12,2) NOT NULL DEFAULT 0,
        payments_json JSONB NOT NULL DEFAULT '{}'::jsonb
    )""")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2)")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2)")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2)")


def _ensure_cash_link_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_z_cash_details (
        id BIGSERIAL PRIMARY KEY,
        z_closure_id BIGINT NOT NULL UNIQUE,
        business_date TEXT NOT NULL UNIQUE,
        opening_amount NUMERIC(12,2) NOT NULL,
        cash_sales NUMERIC(12,2) NOT NULL,
        theoretical_amount NUMERIC(12,2) NOT NULL,
        counted_amount NUMERIC(12,2) NOT NULL,
        difference_amount NUMERIC(12,2) NOT NULL,
        counted_at BIGINT NOT NULL,
        linked_at BIGINT NOT NULL
    )""")


def register_z_cancelled_guard_phase44(app, db):
    if app.view_functions.get("z_status") is None or app.view_functions.get("z_close") is None:
        raise RuntimeError("Routes Z introuvables")

    def _bounds():
        now = datetime.now(PARIS)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return now, start, int(start.timestamp() * 1000), int(now.timestamp() * 1000)

    def z_status_cancelled_phase44():
        now, start, start_ms, end_ms = _bounds()
        day = start.strftime("%Y-%m-%d")
        try:
            with db() as conn:
                _ensure_z_schema(conn)
                conn.commit()
                closed = conn.execute("SELECT id FROM caisse_z_closures WHERE business_date=%s", (day,)).fetchone()
                rows = conn.execute(
                    "SELECT num,status FROM caisse_orders WHERE created_at >= %s AND created_at <= %s ORDER BY num",
                    (start_ms, end_ms),
                ).fetchall()
            visible_rows = [r for r in rows if _norm_status(r.get("status")) not in CANCELLED_STATUSES]
            open_rows = [
                r for r in visible_rows
                if _norm_status(r.get("status")) not in TERMINAL_STATUSES
            ]
            return jsonify({
                "ok": True,
                "business_date": day,
                "already_closed": bool(closed),
                "orders": len(visible_rows),
                "open_orders": [{"num": r["num"], "status": r["status"]} for r in open_rows],
                "can_close": not closed and len(visible_rows) > 0 and not open_rows,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "État Z indisponible", "detail": str(exc)}), 500

    def z_close_cancelled_phase44():
        now, start, start_ms, end_ms = _bounds()
        day = start.strftime("%Y-%m-%d")
        closed_at = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_z_schema(conn)
                    _ensure_cash_link_schema(conn)

                    if conn.execute(
                        "SELECT id FROM caisse_z_closures WHERE business_date=%s FOR UPDATE",
                        (day,),
                    ).fetchone():
                        return jsonify({"ok": False, "error": "La journée est déjà clôturée par un Z"}), 409

                    cash = conn.execute("""
                        SELECT business_date,opening_amount,cash_sales,theoretical_amount,
                               counted_amount,difference_amount,counted_at
                        FROM caisse_cash_counts
                        WHERE business_date=%s
                        FOR UPDATE
                    """, (day,)).fetchone()
                    if not cash:
                        return jsonify({
                            "ok": False,
                            "error": "Z refusé : le comptage espèces définitif doit être enregistré avant la clôture."
                        }), 409

                    rows = conn.execute("""
                        SELECT id,num,payment,status,total,total_ttc,total_ht,tax_amount,z_closure_id
                        FROM caisse_orders
                        WHERE created_at >= %s AND created_at <= %s
                        ORDER BY num
                        FOR UPDATE
                    """, (start_ms, end_ms)).fetchall()
                    if not rows:
                        return jsonify({"ok": False, "error": "Aucune commande à clôturer aujourd'hui"}), 409

                    active_rows = [r for r in rows if _norm_status(r.get("status")) not in CANCELLED_STATUSES]
                    opened = [r for r in active_rows if _norm_status(r.get("status")) not in TERMINAL_STATUSES]
                    if opened:
                        return jsonify({
                            "ok": False,
                            "error": "Z refusé : toutes les commandes actives doivent être terminées",
                            "open_orders": [{"num": r["num"], "status": r["status"]} for r in opened],
                        }), 409

                    if any(r.get("z_closure_id") is not None for r in rows):
                        return jsonify({"ok": False, "error": "Z refusé : une commande du jour appartient déjà à une clôture"}), 409

                    snap = _snapshot(active_rows)
                    closure = conn.execute("""
                        INSERT INTO caisse_z_closures
                        (business_date,closed_at,first_order_num,last_order_num,order_count,
                         total_ht,tax_rate,tax_amount,total_ttc,payments_json)
                        VALUES (%s,%s,%s,%s,%s,%s,10,%s,%s,%s::jsonb)
                        RETURNING id
                    """, (
                        day, closed_at, snap["first"], snap["last"], snap["count"],
                        snap["ht"], snap["tax"], snap["ttc"],
                        json.dumps({k: float(v) for k, v in snap["payments"].items()}, ensure_ascii=False),
                    )).fetchone()
                    closure_id = closure["id"]

                    conn.execute(
                        "UPDATE caisse_orders SET z_closure_id=%s WHERE id = ANY(%s)",
                        (closure_id, [r["id"] for r in rows]),
                    )

                    linked_at = int(time.time() * 1000)
                    conn.execute("""
                        INSERT INTO caisse_z_cash_details
                        (z_closure_id,business_date,opening_amount,cash_sales,theoretical_amount,
                         counted_amount,difference_amount,counted_at,linked_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        closure_id, day, cash["opening_amount"], cash["cash_sales"],
                        cash["theoretical_amount"], cash["counted_amount"],
                        cash["difference_amount"], cash["counted_at"], linked_at,
                    ))

            return jsonify({
                "ok": True,
                "closed": True,
                "business_date": day,
                "closure_id": closure_id,
                "orders": snap["count"],
                "total_ht": float(snap["ht"]),
                "tax_amount": float(snap["tax"]),
                "total_ttc": float(snap["ttc"]),
                "cash_linked": True,
                "cash": {
                    "opening_amount": float(Decimal(str(cash["opening_amount"]))),
                    "cash_sales": float(Decimal(str(cash["cash_sales"]))),
                    "theoretical_amount": float(Decimal(str(cash["theoretical_amount"]))),
                    "counted_amount": float(Decimal(str(cash["counted_amount"]))),
                    "difference_amount": float(Decimal(str(cash["difference_amount"]))),
                },
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Clôture Z impossible", "detail": str(exc)}), 500

    z_status_cancelled_phase44.__name__ = "z_status_cancelled_phase44"
    z_close_cancelled_phase44.__name__ = "z_close_cancelled_phase44"
    app.view_functions["z_status"] = z_status_cancelled_phase44
    app.view_functions["z_close"] = z_close_cancelled_phase44
