"""Export comptable mensuel BÉCHÉFAA — lecture seule.

Le module ne modifie ni commandes, ni paiements, ni Z. Il consolide les
snapshots fiscaux existants et le journal des transactions pour fournir un
aperçu mensuel et un PDF téléchargeable.
"""
from datetime import datetime, time
from calendar import monthrange
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Response, jsonify, request

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")
EXCLUDED_METHODS = {"CHEQUE", "CHÈQUE", "VIREMENT"}


def _month_bounds(value):
    raw = str(value or "").strip()
    if not raw:
        raw = datetime.now(PARIS).strftime("%Y-%m")
    try:
        first = datetime.strptime(raw, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise ValueError("Mois invalide (format attendu : AAAA-MM)")
    last = first.replace(day=monthrange(first.year, first.month)[1])
    start = datetime.combine(first, time.min, PARIS)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1, day=1)
    else:
        next_first = first.replace(month=first.month + 1, day=1)
    end = datetime.combine(next_first, time.min, PARIS)
    return raw, first, last, int(start.astimezone(UTC).timestamp() * 1000), int(end.astimezone(UTC).timestamp() * 1000)


def _restaurant_identity(conn):
    defaults = {
        "name": "BÉCHÉFAA", "legal_name": "", "address": "", "postal_code": "",
        "city": "Fontenay-sous-Bois", "phone": "", "email": "", "siret": "", "vat_number": "",
    }
    try:
        rows = conn.execute("SELECT setting_key,setting_value FROM caisse_restaurant_settings").fetchall()
        for row in rows:
            key = row["setting_key"]
            if key in defaults:
                defaults[key] = row["setting_value"] or ""
    except Exception:
        pass
    return defaults


def _summary(conn, start_ms, end_ms):
    sales = conn.execute("""
        SELECT COUNT(*) AS orders_count,
               COALESCE(SUM(COALESCE(total_ht, ROUND(total / 1.10, 2))),0) AS ht,
               COALESCE(SUM(COALESCE(tax_amount, total - ROUND(total / 1.10, 2))),0) AS vat,
               COALESCE(SUM(COALESCE(total_ttc, total)),0) AS ttc
        FROM caisse_orders
        WHERE created_at >= %s AND created_at < %s
          AND COALESCE(cancellation_hidden,FALSE)=FALSE
    """, (start_ms, end_ms)).fetchone()

    cashflow = conn.execute("""
        SELECT COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS payments,
               COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunds
        FROM caisse_payment_transactions
        WHERE created_at >= %s AND created_at < %s
    """, (start_ms, end_ms)).fetchone()

    method_rows = conn.execute("""
        SELECT UPPER(COALESCE(NULLIF(method,''),'AUTRE')) AS method,
               COALESCE(SUM(CASE
                 WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount
                 WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN -amount
                 ELSE 0 END),0) AS net
        FROM caisse_payment_transactions
        WHERE created_at >= %s AND created_at < %s
        GROUP BY 1 ORDER BY net DESC, method
    """, (start_ms, end_ms)).fetchall()
    methods = []
    for row in method_rows:
        method = str(row["method"] or "AUTRE").strip().upper()
        if method in EXCLUDED_METHODS:
            continue
        methods.append({"method": method, "net": float(row["net"] or 0)})

    # Canaux métier : Salle/Table = RESTAURANT ; Livraison = LIVRAISON ; sinon = À EMPORTER.
    source_rows = conn.execute("""
        SELECT CASE
                 WHEN table_number IS NOT NULL THEN 'RESTAURANT'
                 WHEN UPPER(COALESCE(source,'')) IN ('LIVRAISON','DELIVERY') THEN 'LIVRAISON'
                 ELSE 'À EMPORTER'
               END AS source,
               COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_ttc,total)),0) AS total
        FROM caisse_orders
        WHERE created_at >= %s AND created_at < %s
          AND COALESCE(cancellation_hidden,FALSE)=FALSE
        GROUP BY 1 ORDER BY total DESC, source
    """, (start_ms, end_ms)).fetchall()

    daily_sales = conn.execute("""
        SELECT TO_CHAR(TO_TIMESTAMP(created_at/1000.0) AT TIME ZONE 'Europe/Paris','YYYY-MM-DD') AS day,
               COUNT(*) AS count,
               COALESCE(SUM(COALESCE(total_ttc,total)),0) AS ttc
        FROM caisse_orders
        WHERE created_at >= %s AND created_at < %s
          AND COALESCE(cancellation_hidden,FALSE)=FALSE
        GROUP BY 1 ORDER BY 1
    """, (start_ms, end_ms)).fetchall()

    daily_tx = conn.execute("""
        SELECT TO_CHAR(TO_TIMESTAMP(created_at/1000.0) AT TIME ZONE 'Europe/Paris','YYYY-MM-DD') AS day,
               COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS payments,
               COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunds
        FROM caisse_payment_transactions
        WHERE created_at >= %s AND created_at < %s
        GROUP BY 1 ORDER BY 1
    """, (start_ms, end_ms)).fetchall()

    days = {}
    for row in daily_sales:
        days[row["day"]] = {"day": row["day"], "orders": int(row["count"] or 0), "ttc": float(row["ttc"] or 0), "payments": 0.0, "refunds": 0.0}
    for row in daily_tx:
        d = days.setdefault(row["day"], {"day": row["day"], "orders": 0, "ttc": 0.0, "payments": 0.0, "refunds": 0.0})
        d["payments"] = float(row["payments"] or 0)
        d["refunds"] = float(row["refunds"] or 0)

    payments = float(cashflow["payments"] or 0)
    refunds = float(cashflow["refunds"] or 0)
    return {
        "sales": {"orders": int(sales["orders_count"] or 0), "ht": float(sales["ht"] or 0), "vat": float(sales["vat"] or 0), "ttc": float(sales["ttc"] or 0)},
        "cashflow": {"payments": payments, "refunds": refunds, "net": payments - refunds},
        "methods": methods,
        "sources": [{"source": r["source"], "count": int(r["count"] or 0), "total": float(r["total"] or 0)} for r in source_rows],
        "daily": [days[k] for k in sorted(days)],
    }


def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value):
    return f"{float(value or 0):,.2f} €".replace(",", " ")


def _build_pdf(lines):
    pages, current = [], []
    for line in lines:
        current.append(line)
        if len(current) >= 48:
            pages.append(current)
            current = []
    if current or not pages:
        pages.append(current)

    objects = []
    def add(data):
        objects.append(data)
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids = []

    for page_lines in pages:
        stream_parts = ["BT", "/F1 10 Tf", "50 800 Td", "13 TL"]
        first = True
        for text, size, _bold in page_lines:
            if not first:
                stream_parts.append("T*")
            first = False
            stream_parts.append(f"/F1 {size} Tf")
            stream_parts.append(f"({_pdf_escape(text)}) Tj")
        stream_parts.append("ET")
        stream = "\n".join(stream_parts).encode("cp1252", "replace")
        stream_id = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()

    out = BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects)+1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def register_accounting_export_monthly_phase6(app, db):
    def get_payload(month_value):
        month, first, last, start_ms, end_ms = _month_bounds(month_value)
        with db() as conn:
            identity = _restaurant_identity(conn)
            summary = _summary(conn, start_ms, end_ms)
        return {"month": month, "start_date": first.isoformat(), "end_date": last.isoformat(), "restaurant": identity, **summary}

    @app.get("/api/accounting-export/monthly-phase6")
    def accounting_export_preview_phase6():
        try:
            return jsonify({"ok": True, **get_payload(request.args.get("month"))})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Export comptable indisponible", "detail": str(exc)}), 500

    @app.get("/api/accounting-export/monthly-phase6.pdf")
    def accounting_export_pdf_phase6():
        try:
            d = get_payload(request.args.get("month"))
            r, s, c = d["restaurant"], d["sales"], d["cashflow"]
            lines = [
                ("BÉCHÉFAA - EXPORT COMPTABLE MENSUEL", 16, True),
                (f"Période : {d['start_date']} au {d['end_date']}", 11, False),
                ("", 8, False),
                (r.get("legal_name") or r.get("name") or "BÉCHÉFAA", 12, True),
                (" ".join(x for x in [r.get("address"), r.get("postal_code"), r.get("city")] if x), 9, False),
                (f"SIRET : {r.get('siret') or '-'}", 9, False),
                (f"TVA intracommunautaire : {r.get('vat_number') or '-'}", 9, False),
                ("", 8, False),
                ("SYNTHÈSE DES VENTES", 12, True),
                (f"Commandes : {s['orders']}", 10, False),
                (f"Chiffre d'affaires HT : {_money(s['ht'])}", 10, False),
                (f"TVA 10 % : {_money(s['vat'])}", 10, False),
                (f"Chiffre d'affaires TTC : {_money(s['ttc'])}", 10, False),
                ("", 8, False),
                ("ENCAISSEMENTS", 12, True),
                (f"Paiements reçus : {_money(c['payments'])}", 10, False),
                (f"Remboursements : {_money(c['refunds'])}", 10, False),
                (f"Net encaissé : {_money(c['net'])}", 10, False),
                ("", 8, False),
                ("MOYENS DE PAIEMENT - NET", 12, True),
            ]
            for item in d["methods"]:
                lines.append((f"{item['method']} : {_money(item['net'])}", 10, False))
            lines.extend([("", 8, False), ("CANAUX DE VENTE", 12, True)])
            for item in d["sources"]:
                lines.append((f"{item['source']} - {item['count']} commande(s) : {_money(item['total'])}", 10, False))
            lines.extend([("", 8, False), ("DÉTAIL JOURNALIER", 12, True)])
            for day in d["daily"]:
                net = day["payments"] - day["refunds"]
                lines.append((f"{day['day']} | {day['orders']} cmd | ventes {_money(day['ttc'])} | encaissé net {_money(net)}", 9, False))
            lines.extend([("", 8, False), ("Document généré en lecture seule depuis BÉCHÉFAA-Caisse.", 8, False)])
            pdf = _build_pdf(lines)
            return Response(pdf, content_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=bechefaa-export-comptable-{d['month']}.pdf", "Cache-Control": "no-store"})
        except ValueError as exc:
            return Response(str(exc), status=400, content_type="text/plain; charset=utf-8")
        except Exception as exc:
            return Response("Export comptable indisponible : " + str(exc), status=500, content_type="text/plain; charset=utf-8")

    @app.get("/administration/export-comptable")
    def accounting_export_page_phase6():
        current = datetime.now(PARIS).strftime("%Y-%m")
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Export comptable</title><style>*{box-sizing:border-box}body{margin:0;background:#070707;color:#f7f7f7;font-family:Arial,sans-serif}.w{max-width:1050px;margin:0 auto;padding:34px 18px}.hero,.box,.card{background:#101010;border:1px solid #292929;border-radius:15px}.hero{padding:22px;border-color:#735314}.hero h1{margin:0 0 6px;color:#f0bd45}.hero p{margin:0;color:#aaa}.controls{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin:18px 0}.controls label{display:block;color:#aaa;font-size:12px;font-weight:800;margin-bottom:5px}.controls input,.controls button,.controls a{min-height:44px;border-radius:9px;border:1px solid #3a3a3a;padding:9px 12px;font-size:14px}.controls input{background:#111;color:#fff}.controls button,.controls a{background:#d99a18;color:#111;font-weight:900;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{padding:16px}.lab{font-size:11px;color:#9a9a9a;text-transform:uppercase;font-weight:900}.val{font-size:24px;font-weight:900;margin-top:7px}.gold{color:#f0bd45}.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.box{padding:18px}.row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid #252525}.row:last-child{border:0}.muted{color:#999}.disabled{opacity:.45;pointer-events:none}.note{margin-top:14px;color:#999;font-size:12px}@media(max-width:760px){.grid,.cols{grid-template-columns:1fr}.controls{align-items:stretch}}</style></head><body><main class="w"><section class="hero"><h1>Export comptable mensuel</h1><p>Récapitulatif fiscal et encaissements BÉCHÉFAA, en lecture seule.</p></section><div class="controls"><div><label>Mois</label><input id="month" type="month" value="__CURRENT__"></div><button onclick="load()">Afficher</button><a id="pdf" href="#">Télécharger le PDF</a><a class="disabled" href="#">Envoyer par e-mail — bientôt</a></div><section class="grid"><div class="card"><div class="lab">Commandes</div><div class="val" id="orders">—</div></div><div class="card"><div class="lab">CA HT</div><div class="val" id="ht">—</div></div><div class="card"><div class="lab">TVA 10 %</div><div class="val" id="vat">—</div></div><div class="card"><div class="lab">CA TTC</div><div class="val gold" id="ttc">—</div></div><div class="card"><div class="lab">Remboursements</div><div class="val" id="refunds">—</div></div><div class="card"><div class="lab">Net encaissé</div><div class="val gold" id="net">—</div></div></section><section class="cols"><div class="box"><h2>Moyens de paiement</h2><div id="methods"></div></div><div class="box"><h2>Canaux de vente</h2><div id="sources"></div></div></section><div id="msg" class="note"></div></main><script>const $=x=>document.getElementById(x),euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});async function load(){const m=$('month').value;$('pdf').href='/api/accounting-export/monthly-phase6.pdf?month='+encodeURIComponent(m);$('msg').textContent='Chargement…';try{const r=await fetch('/api/accounting-export/monthly-phase6?month='+encodeURIComponent(m),{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('orders').textContent=d.sales.orders;$('ht').textContent=euro(d.sales.ht);$('vat').textContent=euro(d.sales.vat);$('ttc').textContent=euro(d.sales.ttc);$('refunds').textContent=euro(d.cashflow.refunds);$('net').textContent=euro(d.cashflow.net);$('methods').innerHTML=d.methods.length?d.methods.map(x=>`<div class="row"><span>${x.method}</span><b>${euro(x.net)}</b></div>`).join(''):'<div class="muted">Aucun encaissement</div>';$('sources').innerHTML=d.sources.length?d.sources.map(x=>`<div class="row"><span>${x.source} (${x.count})</span><b>${euro(x.total)}</b></div>`).join(''):'<div class="muted">Aucune commande</div>';$('msg').textContent=d.start_date+' → '+d.end_date}catch(e){$('msg').textContent='Erreur : '+e.message}}load()</script></body></html>'''.replace('__CURRENT__', current)
        return Response(html, content_type="text/html; charset=utf-8")
