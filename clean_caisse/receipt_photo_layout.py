"""Approved kitchen and client paper layouts.

One monochrome renderer supplies both Epson raster data and browser previews.
No order or payment data is modified.
"""
import base64
import io
import re
import textwrap
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
        for detail in re.split(r',\s+(?!\d)', value):
            detail = detail.strip()
            if sep and group.lower().startswith('sans') and not detail.lower().startswith('sans'):
                detail = 'Sans ' + detail
            if detail:
                result.append(detail)
    return result


class Paper:
    def __init__(self):
        self.rows = []
        self.font = ImageFont.truetype(str(ASSETS / 'DejaVuSansMono-receipt.ttf'), 24)
        self.bold_font = ImageFont.truetype(str(ASSETS / 'DejaVuSansMono-Bold-receipt.ttf'), 24)

    def text(self, text='', *, columns=48, center=False, height=1, bold=False):
        # Match thermal character cells and automatic line endings in the photo.
        text = str(text)
        font = self.bold_font if bold else self.font
        for start in range(0, max(1, len(text)), columns):
            line = text[start:start + columns]
            cell = WIDTH // columns
            row = Image.new('1', (WIDTH, 28 * height), 0)
            if line:
                glyph = Image.new('L', (max(1, int(font.getlength(line)) + 2), 28), 0)
                ImageDraw.Draw(glyph).text((0, 0), line, font=font, fill=255, anchor='lt')
                glyph = glyph.resize((len(line) * cell, 24 * height), Image.Resampling.LANCZOS).point(lambda p: 255 if p >= 100 else 0).convert('1')
                row.paste(glyph, ((WIDTH - glyph.width)//2 if center else 0, 0))
            self.rows.append(row)

    def gap(self, dots=20):
        self.rows.append(Image.new('1', (WIDTH, dots), 0))

    def option(self, value):
        lines = textwrap.wrap(str(value), width=44, break_long_words=False,
                              break_on_hyphens=False)
        for index, line in enumerate(lines):
            self.text(('  - ' if index == 0 else '    ') + line)

    def rule(self):
        self.text('-' * 40, center=True)

    def price(self, label, value, bold=False):
        amount = f'{Decimal(str(value or 0)):.2f}'.replace('.', ',') + ' €'
        available = 48 - len(amount) - 1
        while len(label) > available:
            self.text(label[:available])
            label = label[available:]
        self.text(label + ' ' * (48 - len(label) - len(amount)) + amount, bold=bold)

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
        p.text('BECHEFAA', columns=24, center=True, height=2)
        p.rule()
        p.text(mode, columns=24, center=True, height=2, bold=True)
        if order.get('table_number'):
            p.text('TABLE ' + str(order['table_number']), center=True, bold=True)
        if order.get('customer_name'):
            p.text(order['customer_name'], center=True, bold=True)
        p.rule()
        for item in order.get('items') or []:
            label = f"{item.get('qty') or 1} x {item.get('name') or ''}"
            for line in textwrap.wrap(label, width=48, break_long_words=False, break_on_hyphens=False):
                p.text(line, bold=True)
            for value in option_values(item):
                p.option(value)
            p.gap(12)
        p.rule()
    else:
        p.text(identity.get('name') or 'BECHEFAA', columns=24, center=True, height=2, bold=True)
        def without_country(value):
            return re.sub(r'(?:[,;\s]+)?France\s*$', '', str(value or '').strip(), flags=re.IGNORECASE).rstrip(' ,;')
        address = without_country(identity.get('address'))
        if address:
            p.text(address, center=True)
        locality = ' '.join(without_country(identity.get(k)) for k in ('postal_code','city')).strip()
        if locality: p.text(locality, center=True)
        if identity.get('phone'): p.text('Tel. ' + str(identity['phone']), center=True)
        if mode != 'LIVRAISON':
            if identity.get('siret'): p.text('SIRET : ' + str(identity['siret']), center=True)
            if identity.get('vat_number'): p.text('TVA : ' + str(identity['vat_number']), center=True)
        p.rule()
        p.text(mode, columns=24, center=True, bold=True)
        if order.get('table_number'): p.text('Table ' + str(order['table_number']), center=True)
        if order.get('customer_name'): p.text(order['customer_name'], center=True)
        if mode == 'LIVRAISON':
            for key in ('phone','address','postal_code','city'):
                if order.get(key): p.text(order[key], center=True)
        p.rule()
        for item in order.get('items') or []:
            qty = item.get('qty') or 1
            p.price(f"{qty} x {item.get('name') or ''}", Decimal(str(item.get('unit_price') or 0)) * Decimal(str(qty)), bold=True)
            for value in option_values(item):
                p.option(value)
            p.gap(12)
        p.rule()
        ht, tax, total, rate = _tax_values(order)
        p.price('Total HT', ht)
        p.price(f'TVA {rate:g} %', tax)
        p.text('TOTAL TTC ' + f'{total:.2f}'.replace('.', ',') + ' €', columns=24, bold=True)
        p.text('Paiement: ' + str(order.get('payment') or 'A ENCAISSER'))
        p.rule()
        p.gap(28)
        p.text('Merci', center=True)
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
