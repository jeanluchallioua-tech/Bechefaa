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


def order_discount(subtotal, payload, source, existing=None):
    """Recompute a saved percentage when the basket changes; retain legacy euros."""
    existing = existing or {}
    try:
        subtotal = Decimal(str(subtotal))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Sous-total invalide.')
    if not subtotal.is_finite() or subtotal < 0:
        raise ValueError('Sous-total invalide.')
    percent = None
    explicit = 'manual_discount_percent' in payload or 'manual_discount_amount' in payload
    if 'manual_discount_percent' in payload:
        raw = payload['manual_discount_percent']
    elif 'manual_discount_amount' not in payload:
        raw = existing.get('manual_discount_percent')
    else:
        raw = None
    if raw is not None:
        try:
            percent = Decimal(str(raw or 0).replace(',', '.'))
            if not percent.is_finite() or percent < 0 or percent >= 100:
                raise ValueError('Saisissez un pourcentage entre 0 et 99,99 %.')
            percent = percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if percent >= 100:
                raise ValueError('La remise doit être inférieure à 100 %.')
        except (InvalidOperation, TypeError):
            raise ValueError('Pourcentage de remise invalide.')
        amount = (subtotal * percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        amount = payload.get('manual_discount_amount') if explicit else existing.get('discount_amount')
    amount, total = discount_total(subtotal, amount, source,
        coupon_code=existing.get('coupon_code') or payload.get('coupon_code'),
        sales_channel=existing.get('sales_channel') or payload.get('sales_channel'), explicit=explicit)
    return amount, total, percent
