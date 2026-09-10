"""Phase 5 — interface temporaire isolée pour réparer les statuts terminaux.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.

Ajoute une petite page d'administration temporaire qui appelle uniquement
POST /api/phase5/payment-terminal-status/repair déjà fourni par le module
payment_terminal_status_isolated_phase5.
"""

from flask import Response


def register_payment_terminal_repair_ui_isolated_phase5(app):
    @app.get("/phase5/repair-payment-status")
    def payment_terminal_repair_ui_phase5():
        html = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Réparation statuts paiement — BÉCHÉFAA</title>
<style>
body{font-family:Arial,sans-serif;background:#111;color:#fff;margin:0;padding:32px}
.card{max-width:680px;margin:40px auto;background:#1d1d1d;border:1px solid #333;border-radius:16px;padding:28px}
h1{margin-top:0;font-size:24px}.muted{color:#bbb;line-height:1.5}
button{width:100%;padding:16px;border:0;border-radius:10px;font-size:18px;font-weight:700;cursor:pointer;background:#fff;color:#111;margin-top:18px}
button:disabled{opacity:.5;cursor:not-allowed}
pre{white-space:pre-wrap;background:#0b0b0b;padding:16px;border-radius:10px;margin-top:18px;min-height:48px}
</style>
</head>
<body>
<div class="card">
<h1>Réparer les commandes payées restées « Prête »</h1>
<p class="muted">Cette action ne touche ni aux montants, ni aux paiements, ni au Z. Elle fait uniquement passer les commandes financièrement clôturées de « Prête » à « Terminée ».</p>
<button id="repair">Lancer la réparation</button>
<pre id="result">Aucune action exécutée.</pre>
</div>
<script>
const btn=document.getElementById('repair');
const out=document.getElementById('result');
btn.addEventListener('click', async()=>{
  if(!confirm('Lancer la réparation des commandes payées restées Prête ?')) return;
  btn.disabled=true;
  out.textContent='Réparation en cours…';
  try{
    const r=await fetch('/api/phase5/payment-terminal-status/repair',{method:'POST',headers:{'Accept':'application/json'}});
    const d=await r.json();
    out.textContent=JSON.stringify(d,null,2);
  }catch(e){
    out.textContent='Erreur : '+String(e);
  }finally{
    btn.disabled=false;
  }
});
</script>
</body></html>'''
        return Response(html, mimetype="text/html")
