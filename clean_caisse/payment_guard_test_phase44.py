"""Phase 4.4 — page de contrôle isolée de la garde anti-réencaissement.

La page ne déclenche aucune écriture seule. Le bouton appelle volontairement
la route PUT Phase 4.1 sur la commande de test #65 ; la garde Phase 4.4 doit
intercepter la requête et répondre HTTP 409 avant le moteur d'encaissement.
"""
from flask import Response

TEST_ORDER_ID = "caisse-1c123f071e8c4500bc798b6ec5913df3"


def register_payment_guard_test_phase44(app):
    @app.get("/maintenance/phase44/payment-guard-test")
    def payment_guard_test_phase44():
        html = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test garde encaissement Phase 4.4</title>
<style>
body{{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:24px}}
.box{{max-width:620px;margin:auto;background:#fff;border:1px solid #cbd5e1;border-radius:16px;padding:22px}}
button{{border:0;border-radius:10px;padding:13px 16px;background:#7c3aed;color:#fff;font-weight:900;cursor:pointer}}
pre{{white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:14px;border-radius:10px;min-height:80px}}
.ok{{color:#166534;font-weight:900}}.bad{{color:#b91c1c;font-weight:900}}
</style></head><body><div class="box">
<h2>Contrôle anti-réencaissement — commande #65</h2>
<p>Cette commande est partiellement remboursée. Le résultat attendu est <strong>HTTP 409</strong>. Aucun nouvel encaissement ne doit être créé.</p>
<button id="test" type="button">Tester la protection serveur</button>
<p id="verdict"></p><pre id="result">Test non lancé.</pre>
</div><script>
const orderId={TEST_ORDER_ID!r};
document.getElementById('test').onclick=async function(){{
 this.disabled=true;const verdict=document.getElementById('verdict'),out=document.getElementById('result');
 verdict.textContent='Test en cours…';verdict.className='';
 try{{
   const r=await fetch('/api/orders/'+encodeURIComponent(orderId)+'/payment-phase41',{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{method:'CB'}})}});
   let d={{}};try{{d=await r.json()}}catch(e){{}}
   out.textContent='HTTP '+r.status+'\n'+JSON.stringify(d,null,2);
   if(r.status===409 && d && d.ok===false){{verdict.textContent='✓ PROTECTION ACTIVE — nouvel encaissement refusé.';verdict.className='ok'}}
   else{{verdict.textContent='✕ TEST NON CONFORME — ne pas considérer la garde comme validée.';verdict.className='bad'}}
 }}catch(e){{verdict.textContent='Test impossible : '+e.message;verdict.className='bad';out.textContent=String(e)}}
 this.disabled=false;
}};
</script></body></html>'''
        return Response(html, mimetype="text/html")
