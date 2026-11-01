"""BÉCHÉFAA — moteur de promotion isolé (préproduction uniquement).

Aucune mutation des commandes, aucune connexion DB, aucun déploiement.
Les lignes attendues sont des articles unitaires avec product_id, quantity,
unit_price_cents, is_formula et éventuellement extras_total_cents.
La remise porte sur le prix de base, jamais sur les suppléments.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP


def calculate_identical_second_half_off(lines, eligible_product_ids, enabled=True):
    """Retourne les remises en centimes par produit, sans modifier les lignes.

    Seules les paires d'un même product_id sont prises en compte.
    Un produit en formule ne contribue jamais aux paires.
    Le prix de base de chaque unité est utilisé, hors options/suppléments.
    Si des prix de base différents existent pour le même produit, les unités
    les moins chères sont remisées en premier.
    """
    if not enabled:
        return {"total_discount_cents": 0, "discounts": []}
    eligible = {str(p) for p in eligible_product_ids}
    groups = defaultdict(list)
    for line in lines:
        product_id = str(line.get("product_id", ""))
        if not product_id or product_id not in eligible or line.get("is_formula"):
            continue
        quantity = int(line.get("quantity", 1))
        price = int(line.get("unit_price_cents", 0))
        if quantity < 0 or price < 0:
            raise ValueError("Quantité ou prix invalide")
        groups[product_id].extend([price] * quantity)

    discounts = []
    for product_id, prices in sorted(groups.items()):
        count = len(prices) // 2
        if not count:
            continue
        discounted_prices = sorted(prices)[:count]
        amount = sum(
            int((Decimal(price) / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            for price in discounted_prices
        )
        discounts.append({
            "product_id": product_id,
            "discounted_quantity": count,
            "discount_cents": amount,
        })
    return {
        "total_discount_cents": sum(d["discount_cents"] for d in discounts),
        "discounts": discounts,
    }
