"""Phase 4.4 — adaptateur isolé + vendus / - vendus.

IMPORTANT : ce fichier n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il est déployé seul avant toute activation.

Lecture seule uniquement. Aucun Z, aucune clôture, aucune écriture métier.
Le module statistics_phase44.py reste totalement inchangé.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify, request

from clean_caisse.statistics_products_isolated_phase44 import build_product_statistics_query

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")


def _bounds_ms():
    """Calcule la même période que les statistiques principales, en millisecondes."""
    today = datetime.now(PARIS).date()
    period = request.args.get("period", "today")

    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = today + timedelta(days=1)
    elif period == "month":
        start = today.replace(day=1)
        end = today + timedelta(days=1)
    elif period == "custom":
        try:
            start = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
            end = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date() + timedelta(days=1)
        except ValueError as exc:
            raise ValueError("Période personnalisée invalide") from exc
        if end <= start:
            raise ValueError("La date de fin doit être égale ou postérieure à la date de début")
    else:
        period = "today"
        start = today
        end = today + timedelta(days=1)

    a = datetime.combine(start, time.min, PARIS)
    b = datetime.combine(end, time.min, PARIS)
    return (
        int(a.astimezone(UTC).timestamp() * 1000),
        int(b.astimezone(UTC).timestamp() * 1000),
        period,
        start.isoformat(),
        (end - timedelta(days=1)).isoformat(),
    )


def register_statistics_products_adapter_phase44(app, db):
    """Enregistre uniquement l'API de classement produits quand on l'activera plus tard."""

    @app.get("/api/statistics/products-phase44")
    def statistics_products_phase44():
        try:
            start_ms, end_ms, period, start_date, end_date = _bounds_ms()
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        try:
            with db() as conn:
                rows = conn.execute(
                    build_product_statistics_query() + " ORDER BY qty DESC, revenue DESC, i.name ASC",
                    (start_ms, end_ms),
                ).fetchall()
        except Exception as exc:
            return jsonify({"ok": False, "error": "Statistiques produits indisponibles", "detail": str(exc)}), 500

        products = [
            {
                "name": row["name"],
                "qty": int(row["qty"] or 0),
                "revenue": float(row["revenue"] or 0),
            }
            for row in rows
        ]

        top = products[:5]
        bottom = sorted(products, key=lambda x: (x["qty"], x["revenue"], x["name"]))[:5]

        return jsonify(
            {
                "ok": True,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
                "top_sold": top,
                "least_sold": bottom,
            }
        )
