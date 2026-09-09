"""Phase 4.4 — adaptateur isolé statistiques produits.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare l'intégration du classement + vendus / - vendus
sans modifier le noyau statistiques validé.

Lecture seule uniquement. Aucun Z, aucune clôture, aucune écriture métier.
"""

from clean_caisse.statistics_products_isolated_phase44 import build_product_statistics_query


def fetch_product_rankings(db, start_ms, end_ms, limit=5):
    """Lit les ventes produits sur une période et retourne les classements.

    Le module reste inactif tant qu'il n'est pas explicitement enregistré.
    Les bornes sont des timestamps Unix en millisecondes, comme caisse_orders.created_at.
    """
    limit = max(1, min(int(limit), 20))
    query = build_product_statistics_query()

    with db() as conn:
        rows = conn.execute(query, (int(start_ms), int(end_ms))).fetchall()

    products = [
        {
            "name": row["name"],
            "qty": int(row["qty"] or 0),
            "revenue": float(row["revenue"] or 0),
        }
        for row in rows
    ]

    most_sold = sorted(
        products,
        key=lambda item: (-item["qty"], -item["revenue"], item["name"].casefold()),
    )[:limit]

    least_sold = sorted(
        products,
        key=lambda item: (item["qty"], item["revenue"], item["name"].casefold()),
    )[:limit]

    return {
        "most_sold": most_sold,
        "least_sold": least_sold,
    }
