"""Phase 4.4 — module isolé statistiques produits.

IMPORTANT : ce fichier n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il est déployé seul pour respecter la méthode : isoler,
déployer, vérifier, valider, puis seulement intégrer.

Lecture seule uniquement. Aucun Z, aucune clôture, aucune écriture métier.
"""


def build_product_statistics_query():
    """Retourne uniquement la requête SQL prévue pour la future intégration.

    Ce module n'est pas exécuté tant qu'il n'est pas explicitement enregistré.
    """
    return """
        SELECT i.name,
               COALESCE(SUM(i.qty), 0) AS qty,
               COALESCE(SUM(i.qty * i.unit_price), 0) AS revenue
        FROM caisse_order_items i
        JOIN caisse_orders o ON o.id = i.order_id
        WHERE o.created_at >= %s
          AND o.created_at < %s
          AND COALESCE(o.cancellation_hidden, FALSE) = FALSE
          AND UPPER(COALESCE(o.status, '')) <> 'ANNULÉE'
        GROUP BY i.name
        HAVING COALESCE(SUM(i.qty), 0) > 0
    """
