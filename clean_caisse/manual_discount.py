"""Cashier-entered euro discounts; catalogue item prices remain unchanged."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def discount_total(subtotal, value, source, *, coupon_code=None, sales_channel=None, explicit=True):
    try:
        amount = Decimal(str(value or 0).replace(',', '.'))
        if not amount.is_finite() or amount < 0:
            raise ValueError("Saisissez une remise positive en euros.")
        amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise ValueError("Montant de remise invalide.")
    if amount and amount >= subtotal:
        raise ValueError("La remise doit laisser au moins 0,01 € à régler.")
    if amount and explicit:
        if str(source).upper() not in {'EMPORTER', 'TAKEAWAY', 'COMPTOIR'}:
            raise ValueError("La remise manuelle est réservée aux commandes à emporter.")
        if coupon_code or str(sales_channel or '').upper() in {'SITE','DELIVEROO','UBER','UBER_EATS'}:
            raise ValueError("La remise caisse ne se cumule pas avec une remise ou commande en ligne.")
    return amount, subtotal - amount
