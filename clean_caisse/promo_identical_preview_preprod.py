"""Isolated preproduction-only promotion preview routes.

Read-only simulation: no order writes, no payment changes.
Activation is intentionally blocked outside preproduction.
"""
import os
from flask import jsonify, request, Response
from .promo_identical_preprod import calculate_identical_second_half_off


def register_promo_identical_preprod(app):
    @app.get("/administration/promo-identique-test")
    def promo_identical_preview():
        if os.getenv("BECHEFAA_PROMO_PREPROD", "") != "1":
            return Response("Disponible uniquement en préproduction.", status=404)
        return Response("""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA — Simulation promotion</title>
<style>body{font:16px Arial;background:#f4f5f7;color:#142b39;margin:0}.wrap{max-width:650px;margin:25px auto;padding:20px;background:white;border-radius:14px}h1{color:#143d53}label{display:block;margin:16px 0}input{width:85px;padding:10px;font-size:18px}button{background:#143d53;color:white;border:0;padding:12px;border-radius:8px}.total{font-size:24px;font-weight:bold}.discount{color:green}</style>
<div class="wrap"><h1>BÉCHÉFAA — Promotion 2ᵉ identique à −50 %</h1><p>Simulation sans encaissement ni commande réelle.</p>
<label>Sandwich Shawarma — 14 € (exemple) <input id="shaw" type="number" min="0" max="50" value="2"></label>
<label>Burger BZH — 15 € (exemple) <input id="bzh" type="number" min="0" max="50" value="0"></label>
<label><input id="formula" type="checkbox" style="width:auto"> Burger BZH en formule (exclu de la promotion)</label>
<button id="run">Calculer</button><p id="result" role="status"></p></div>
<script>document.getElementById('run').onclick=async()=>{let s=+document.getElementById('shaw').value,b=+document.getElementById('bzh').value,f=document.getElementById('formula').checked;if(!Number.isInteger(s)||!Number.isInteger(b)||s<0||b<0||s>50||b>50)return;const items=[{product_id:'shaw',quantity:s,unit_price_cents:1400},{product_id:'bzh',quantity:b,unit_price_cents:1500,is_formula:f}];const r=await fetch('/api/promo-identique-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items})});const d=await r.json();const money=n=>(n/100).toFixed(2).replace('.',',')+' €';document.getElementById('result').innerHTML=d.ok?'Sous-total : '+money(s*1400+b*1500)+'<br><span class="discount">Remise : −'+money(d.total_discount_cents)+'</span><br><span class="total">Total : '+money(s*1400+b*1500-d.total_discount_cents)+'</span>':'Erreur de simulation';};document.getElementById('run').click();</script></html>""", mimetype="text/html")

    @app.post("/api/promo-identique-test")
    def promo_identical_calculate():
        if os.getenv("BECHEFAA_PROMO_PREPROD", "") != "1":
            return jsonify(ok=False, error="Préproduction uniquement"), 404
        data = request.get_json(silent=True) or {}
        lines = data.get("items", [])
        if not isinstance(lines, list) or len(lines) > 100:
            return jsonify(ok=False, error="Panier invalide"), 400
        try:
            if any(not isinstance(x, dict) or int(x.get("quantity", 1)) > 50 for x in lines):
                return jsonify(ok=False, error="Quantité invalide"), 400
            result = calculate_identical_second_half_off(lines, {"shaw", "bzh"})
        except (TypeError, ValueError, OverflowError):
            return jsonify(ok=False, error="Données invalides"), 400
        return jsonify(ok=True, **result)
