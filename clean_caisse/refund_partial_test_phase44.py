"""Phase 4.4 — remboursement partiel LOCAL de test.

Route volontairement isolée. Le moteur stable de remboursement reste
l'autorité métier. Une page de test dédiée permet de déclencher uniquement
un remboursement de 1,00 € sur la commande de développement #65.
"""
from flask import jsonify, request, render_template_string

TEST_ORDER_ID = "caisse-1c123f071e8c4500bc798b6ec5913df3"
TEST_TRANSACTION_ID = "pay_e492b9540f5b44c0b5224af93d6e4e26"
TEST_AMOUNT = 1.00


def register_refund_partial_test_phase44(app):
    @app.get("/api/refund-partial-phase44-test")
    def refund_partial_test_phase44_info():
        return jsonify({
            "ok": True,
            "test_only": True,
            "write": True,
            "method": "POST",
            "target": "/api/orders/<order_id>/refund-phase44",
            "required": ["order_id", "transaction_id", "amount"],
            "note": "Cette route GET n'effectue aucun remboursement. Le POST de test doit etre explicite.",
        })

    @app.get("/maintenance/phase44/refund-test")
    def refund_partial_test_phase44_page():
        return render_template_string("""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test remboursement Phase 4.4</title>
<style>
body{font-family:Arial,sans-serif;background:#f5f6f8;margin:0;padding:32px;color:#17202a}
.card{max-width:720px;margin:auto;background:white;border-radius:16px;padding:28px;box-shadow:0 8px 30px rgba(0,0,0,.08)}
h1{margin-top:0}.warn{background:#fff4e5;border:1px solid #f0c36d;padding:14px;border-radius:10px;margin:18px 0}
button{font-size:20px;font-weight:700;padding:16px 22px;border:0;border-radius:12px;cursor:pointer;background:#143D53;color:white}
button:disabled{opacity:.5;cursor:not-allowed}pre{white-space:pre-wrap;background:#111;color:#eee;padding:16px;border-radius:10px;margin-top:18px}
</style>
</head>
<body>
<div class="card">
  <h1>Test remboursement Phase 4.4</h1>
  <p><strong>Commande :</strong> #65</p>
  <p><strong>Paiement :</strong> CB — 31,50 €</p>
  <p><strong>Montant du test :</strong> 1,00 €</p>
  <div class="warn"><strong>Attention :</strong> ce bouton écrit réellement un remboursement de 1,00 € dans PostgreSQL. Il ne doit être cliqué qu'une seule fois pour ce test.</div>
  <button id="refundBtn">TEST — Rembourser 1,00 € sur commande #65</button>
  <pre id="result">Aucun remboursement déclenché.</pre>
</div>
<script>
const btn=document.getElementById('refundBtn');
const out=document.getElementById('result');
btn.addEventListener('click', async ()=>{
  if(!confirm('Confirmer le remboursement TEST de 1,00 € sur la commande #65 ?')) return;
  btn.disabled=true;
  out.textContent='Remboursement en cours...';
  try{
    const r=await fetch('/api/refund-partial-phase44-test',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        order_id:'{{ order_id }}',
        transaction_id:'{{ transaction_id }}',
        amount:{{ amount }},
        reason:'TEST PHASE 4.4',
        created_by:'JEAN-LUC'
      })
    });
    const data=await r.json();
    out.textContent=JSON.stringify(data,null,2);
    if(!r.ok || !data.ok) btn.disabled=false;
  }catch(e){
    out.textContent='Erreur: '+e;
    btn.disabled=false;
  }
});
</script>
</body>
</html>
        """, order_id=TEST_ORDER_ID, transaction_id=TEST_TRANSACTION_ID, amount=TEST_AMOUNT)

    @app.post("/api/refund-partial-phase44-test")
    def refund_partial_test_phase44():
        payload = request.get_json(silent=True) or {}
        order_id = str(payload.get("order_id") or "").strip()
        transaction_id = str(payload.get("transaction_id") or "").strip()
        amount = payload.get("amount")
        if not order_id or not transaction_id or amount is None:
            return jsonify({"ok": False, "error": "order_id, transaction_id et amount obligatoires"}), 400

        if order_id != TEST_ORDER_ID or transaction_id != TEST_TRANSACTION_ID:
            return jsonify({"ok": False, "error": "Ce test est limité à la commande #65 et à son paiement validé"}), 400
        try:
            if float(amount) != TEST_AMOUNT:
                return jsonify({"ok": False, "error": "Ce test est limité à un remboursement exact de 1,00 €"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Montant invalide"}), 400

        endpoint = app.view_functions.get("refund_phase44")
        if endpoint is None:
            return jsonify({"ok": False, "error": "Moteur remboursement Phase 4.4 indisponible"}), 503

        original_json = request.get_json(silent=True) or {}
        cached = getattr(request, "_cached_json", None)
        try:
            request._cached_json = ({
                "transaction_id": transaction_id,
                "amount": TEST_AMOUNT,
                "reason": str(original_json.get("reason") or "TEST PHASE 4.4").strip(),
                "created_by": str(original_json.get("created_by") or "TEST").strip(),
            },) * 2
            return endpoint(order_id)
        finally:
            if cached is None:
                try:
                    delattr(request, "_cached_json")
                except AttributeError:
                    pass
            else:
                request._cached_json = cached
