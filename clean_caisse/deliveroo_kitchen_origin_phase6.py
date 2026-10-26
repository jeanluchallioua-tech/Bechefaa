"""Presentation contract for Deliveroo orders in BÉCHÉFAA.

Pure functions only. Not yet connected to kitchen screens or printer.
"""
from html import escape
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError

DELIVEROO_LABEL = "DELIVEROO"
DELIVEROO_COLOR = "#00CCBC"


def kitchen_origin(channel, external_number=None):
    if str(channel or "").strip().upper() != DELIVEROO_LABEL:
        return None
    if external_number is not None and (isinstance(external_number, bool)
                                         or not isinstance(external_number, (str, int))):
        raise DeliverooMappingError("Invalid Deliveroo display number")
    number = str(external_number if external_number is not None else "").strip()
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in number):
        raise DeliverooMappingError("Unsafe Deliveroo display number")
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
