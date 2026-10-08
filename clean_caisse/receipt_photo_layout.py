"""Paper-only layout from the restaurant's approved photograph.

One monochrome renderer supplies both Epson raster data and browser previews.
No order or payment data is modified.
"""
import base64
import io
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / 'print_assets'
WIDTH = 576


def option_groups(item):
    raw = str(item.get('options_text') or '').strip()
    if raw:
        raw = raw.replace(';;', ' · ').replace('::', ': ')
        return [s.strip(' -') for s in re.split(r'[·•|\n]+', raw) if s.strip(' -')]
    result = []
    for option in item.get('options') or []:
        if isinstance(option, dict):
            value = str(option.get('name') or option.get('label') or '').strip()
            group = str(option.get('group') or '').strip()
            if group.lower().startswith('sans') and value and not value.lower().startswith('sans'):
                value = 'Sans ' + value
            if value:
                result.append((group + ': ' if group else '') + value)
        elif option is not None and str(option).strip():
            result.append(str(option).strip())
    return result


def option_values(item):
    result = []
    for part in option_groups(item):
        group, sep, value = part.partition(':')
        value = (value if sep else group).strip()
        if sep and group.lower().startswith('sans') and not value.lower().startswith('sans'):
            value = 'Sans ' + value
        result.append(value)
    return result


class Paper:
    def __init__(self):
        self.rows = []
        self.font = ImageFont.truetype(str(ASSETS / 'DejaVuSansMono-receipt.ttf'), 24)

    def text(self, text='', *, columns=48, center=False):
        # Match thermal character cells and automatic line endings in the photo.
        text = str(text)
        for start in range(0, max(1, len(text)), columns):
            line = text[start:start + columns]
            cell = WIDTH // columns
            row = Image.new('1', (WIDTH, 28), 0)
            if line:
                glyph = Image.new('L', (max(1, int(self.font.getlength(line)) + 2), 28), 0)
                ImageDraw.Draw(glyph).text((0, 0), line, font=self.font, fill=255, anchor='lt')
                glyph = glyph.resize((len(line) * cell, 24), Image.Resampling.LANCZOS).point(lambda p: 255 if p >= 100 else 0).convert('1')
                row.paste(glyph, ((WIDTH - glyph.width)//2 if center else 0, 0))
            self.rows.append(row)

    def gap(self, dots=20):
        self.rows.append(Image.new('1', (WIDTH, dots), 0))

    def rule(self):
        self.text('-' * 40, center=True)

    def price(self, label, value):
        amount = f'{Decimal(str(value or 0)):.2f}EUR'
        available = 48 - len(amount) - 1
        while len(label) > available:
            self.text(label[:available])
            label = label[available:]
        self.text(label + ' ' * (48 - len(label) - len(amount)) + amount)

    def image(self):
        self.gap(60)
        result = Image.new('1', (WIDTH, sum(r.height for r in self.rows)), 0)
        y = 0
        for row in self.rows:
            result.paste(row, (0, y)); y += row.height
        return result


def render_receipt(order, kind, identity=None):
    from .epson_epos_network_phase6 import _service_label, _tax_values
    identity = identity or {}
    p = Paper()
    mode = _service_label(order)
    p.gap(12)
    if kind == 'kitchen':
        p.text('BECHEFAA', columns=24, center=True)
        p.rule()
        p.text(mode, columns=24, center=True)
        if order.get('table_number'):
            p.text('TABLE ' + str(order['table_number']), center=True)
        if order.get('customer_name'):
            p.text(order['customer_name'], center=True)
        p.rule()
        for item in order.get('items') or []:
            p.text(f"{item.get('qty') or 1} x {item.get('name') or ''}", columns=24)
            groups = option_groups(item)
            if groups:
                p.text(' - ' + ' · '.join(groups))
            p.gap(24)
        p.rule()
    else:
        logo = Image.open(ASSETS / 'bechefaa-receipt-logo.png').convert('1')
        row = Image.new('1', (WIDTH, logo.height), 0)
        row.paste(logo, ((WIDTH-logo.width)//2, 0)); p.rows.append(row)
        p.gap(44)
        p.text('Commande C' + str(order.get('num') or ''), center=True)
        p.text(identity.get('name') or 'Bechefaa Restaurant', center=True)
        address = ' '.join(str(identity.get(k) or '').strip() for k in ('address','postal_code','city')).strip()
        if address: p.text(address, center=True)
        if identity.get('siret'): p.text('Siret : ' + str(identity['siret']), center=True)
        if identity.get('phone'): p.text('Tel: ' + str(identity['phone']), center=True)
        if order.get('created_at'):
            stamp = float(order['created_at'])
            if stamp > 100000000000: stamp /= 1000
            date = datetime.fromtimestamp(stamp, ZoneInfo('Europe/Paris')).strftime('%d-%m-%Y %H:%M:%S')
            p.text('Date & Heure: ' + date, center=True)
        covers = int(order.get('covers') or order.get('persons') or 1)
        total = _tax_values(order)[2]
        p.text(f'Couverts: {covers}  Couvert MOYEN: {total / covers:.2f}', center=True)
        p.text('Type de commande: ' + {'A EMPORTER':'A emporter','SUR PLACE':'Sur place','LIVRAISON':'Livraison'}[mode], center=True)
        if order.get('table_number'): p.text('Table: ' + str(order['table_number']), center=True)
        p.text('Client : ' + str(order.get('customer_name') or 'Client'), center=True)
        if mode == 'LIVRAISON':
            for key in ('phone','address','postal_code','city'):
                if order.get(key): p.text(order[key], center=True)
        p.rule()
        p.text('  Produit                                  Total')
        for item in order.get('items') or []:
            qty = item.get('qty') or 1
            p.price(f"{qty}x {item.get('name') or ''}", Decimal(str(item.get('unit_price') or 0)) * Decimal(str(qty)))
            options = option_values(item)
            if options:
                p.text('  Supplements:')
                for value in options: p.text('    - ' + value)
        p.rule()
        ht, tax, total, rate = _tax_values(order)
        p.price('  TOTAL HT:', ht)
        p.price(f'  2 TVA {rate:g}%:', tax)
        p.price('  TOTAL TTC:', total)
    return p.image()


def receipt_png(order, kind, identity=None):
    output = io.BytesIO()
    render_receipt(order, kind, identity).point(lambda p: 0 if p else 255).save(output, format='PNG')
    return output.getvalue()


def receipt_xml(order, kind, identity=None):
    image = render_receipt(order, kind, identity)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">', '<text align="left"/>']
    for y in range(0, image.height, 512):
        chunk = image.crop((0, y, WIDTH, min(y+512, image.height)))
        parts.append(f'<image width="{WIDTH}" height="{chunk.height}" color="color_1" mode="mono">{base64.b64encode(chunk.tobytes()).decode("ascii")}</image>')
    parts.extend(['<cut type="feed"/>', '</epos-print>'])
    return ''.join(parts)
