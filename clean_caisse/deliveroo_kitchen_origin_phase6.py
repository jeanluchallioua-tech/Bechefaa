"""Presentation contract for Deliveroo orders in BÉCHÉFAA.

Pure functions only. Not yet connected to kitchen screens or printer.
"""
from html import escape

DELIVEROO_LABEL = "DELIVEROO"
DELIVEROO_COLOR = "#00CCBC"


def kitchen_origin(channel, external_number=None):
    if str(channel or "").strip().upper() != DELIVEROO_LABEL:
        return None
    number = str(external_number or "").strip()
    return {
        "channel": DELIVEROO_LABEL,
        "label": "COMMANDE DELIVEROO",
        "color": DELIVEROO_COLOR,
        "order_number": number,
        "print_header": "COMMANDE DELIVEROO" + (" - " + number if number else ""),
    }


def kitchen_origin_html(channel, external_number=None):
    """Escaped markup for a future kitchen UI integration."""
    origin = kitchen_origin(channel, external_number)
    if origin is None:
        return ""
    return (
        '<span class="order-origin-deliveroo" '
        'style="background-color:#00CCBC;color:#002F2C;'
        'font-weight:700;padding:3px 8px;border-radius:5px">'
        + escape(origin["label"])
        + (" #" + escape(origin["order_number"]) if origin["order_number"] else "")
        + "</span>"
    )
