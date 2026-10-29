"""Reconcile sandbox order amounts in integer cents; never apply a discount twice."""
from decimal import Decimal, InvalidOperation


def cents(value, *, default=None):
    if value is None:
        return default
    if not isinstance(value, dict) or value.get('currency_code', 'EUR') != 'EUR':
        raise ValueError('Expected an EUR amount')
    raw = value.get('fractional')
    if isinstance(raw, bool):
        raise ValueError('Invalid money amount')
    try:
        amount = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError('Invalid money amount') from exc
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError('Expected nonnegative integer cents')
    return int(amount)


def net_item_cents(order):
    items = order['items']
    amounts = [cents(item.get('total_price')) for item in items]
    if any(amount is None for amount in amounts):
        raise ValueError('Item total missing')
    discounts = [cents(item.get('discount_amount'), default=0) for item in items]
    expected = cents(order.get('total_price'))
    offer = order.get('offer_discount')
    if isinstance(offer, dict) and 'amount' in offer:
        offer = offer['amount']
    offer = cents(offer, default=0)
    gross = sum(amounts)
    if expected is None:
        if offer or any(discounts):
            raise ValueError('Discounted order total missing')
        return amounts
    if gross == expected:
        # Some payloads already include reductions in item totals.
        return amounts
    if any(discount > amount for discount, amount in zip(discounts, amounts)):
        raise ValueError('Item discount exceeds its price')
    net = [amount - discount for amount, discount in zip(amounts, discounts)]
    if sum(net) == expected:
        return net
    # A basket offer can include item discounts. Reconcile the remaining reduction
    # only when the explicit order-level offer explains the full difference.
    if gross - expected != offer or expected > sum(net) or not sum(net):
        raise ValueError('Unexplained Deliveroo total difference')
    base = sum(net)
    allocated = [amount * expected // base for amount in net]
    remainder = expected - sum(allocated)
    ranking = sorted(range(len(net)), key=lambda i: (net[i] * expected % base, -i), reverse=True)
    for i in ranking[:remainder]:
        allocated[i] += 1
    return allocated
