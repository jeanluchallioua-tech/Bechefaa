"""Outil Administration — note de frais repas.

Formulaire local et imprimable : aucune écriture comptable automatique et
aucune donnée persistée. L'utilisateur choisit librement le nombre de repas.
"""
from flask import Response


def register_expense_meal_note_phase6(app):
    @app.get("/administration/note-de-frais")
    def expense_meal_note_phase6():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA • Note de frais repas</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font-family:Arial,sans-serif}.top{background:#111827;color:#fff;padding:16px 22px;font-weight:900;font-size:20px}.wrap{max-width:980px;margin:0 auto;padding:26px 18px}.panel{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:22px;box-shadow:0 8px 25px #1f29370d}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.full{grid-column:1/-1}label{display:block;font-weight:900;font-size:13px;margin-bottom:6px;color:#344054}input,textarea{width:100%;min-height:46px;border:1px solid #cfd6df;border-radius:10px;padding:10px 12px;font-size:15px}textarea{min-height:78px;resize:vertical}.actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}.btn{border:0;border-radius:10px;padding:12px 16px;font-weight:900;cursor:pointer;text-decoration:none}.primary{background:#111827;color:#fff}.gold{background:#d99a18;color:#111}.ghost{background:#eef2f6;color:#111827}.preview{margin-top:22px;border:1px dashed #c9ced6;border-radius:14px;padding:24px;background:#fff}.doc-head{display:flex;justify-content:space-between;gap:20px;border-bottom:2px solid #111827;padding-bottom:16px}.brand{font-size:25px;font-weight:1000}.muted{color:#667085;font-size:13px}.doc-title{text-align:center;margin:28px 0 22px;font-size:25px}.summary{width:100%;border-collapse:collapse;margin:20px 0}.summary th,.summary td{border:1px solid #d7dce3;padding:11px;text-align:left}.summary th{background:#f7f8fa}.total{font-size:22px;font-weight:1000;text-align:right;margin-top:14px}.legal{margin-top:28px;font-size:12px;color:#667085;line-height:1.5}@media(max-width:700px){.grid{grid-template-columns:1fr}.full{grid-column:auto}}@media print{body{background:#fff}.top,.panel>.form,.actions,.admin-global-nav-phase6{display:none!important}.wrap{padding:0;max-width:none}.panel{border:0;box-shadow:none;padding:0}.preview{border:0;padding:0;margin:0}}
</style></head><body><div class="top">BÉCHÉFAA • Note de frais repas</div><main class="wrap"><section class="panel"><div class="form"><h1>Créer une note de frais</h1><p class="muted">Renseignez le nombre de repas et le montant. Le document peut ensuite être imprimé ou enregistré en PDF depuis le navigateur.</p><div class="grid">
<div><label>Date</label><input id="date" type="date"></div><div><label>Référence</label><input id="ref" placeholder="Ex. NDF-2026-001"></div>
<div><label>Nom / bénéficiaire</label><input id="name" placeholder="Nom et prénom"></div><div><label>Société (facultatif)</label><input id="company" placeholder="Société"></div>
<div><label>Nombre de repas</label><input id="qty" type="number" min="1" step="1" value="1"></div><div><label>Prix TTC par repas (€)</label><input id="unit" type="number" min="0" step="0.01" value="0"></div>
<div><label>TVA (%)</label><input id="vat" type="number" min="0" step="0.1" value="10"></div><div><label>Lieu</label><input id="place" value="BÉCHÉFAA"></div>
<div class="full"><label>Motif / observations</label><textarea id="reason" placeholder="Repas professionnel, réunion, déplacement…"></textarea></div>
</div><div class="actions"><button class="btn gold" type="button" onclick="refresh()">Mettre à jour l’aperçu</button><button class="btn primary" type="button" onclick="window.print()">Imprimer / Enregistrer en PDF</button><a class="btn ghost" href="/administration">Retour Administration</a></div></div>
<div class="preview" id="preview"></div></section></main>
<script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>Number(n||0).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
function refresh(){const q=Math.max(1,parseInt(document.getElementById('qty').value||'1',10));const u=Math.max(0,Number(document.getElementById('unit').value||0));const vat=Math.max(0,Number(document.getElementById('vat').value||0));const ttc=q*u;const ht=vat?ttc/(1+vat/100):ttc;const tax=ttc-ht;const d=document.getElementById('date').value;document.getElementById('preview').innerHTML=`
<div class="doc-head"><div><div class="brand">BÉCHÉFAA</div><div class="muted">Restaurant • Fontenay-sous-Bois</div></div><div class="muted">Réf. ${esc(document.getElementById('ref').value||'—')}<br>${esc(d||'—')}</div></div>
<h2 class="doc-title">NOTE DE FRAIS — REPAS</h2>
<p><b>Bénéficiaire :</b> ${esc(document.getElementById('name').value||'—')}<br><b>Société :</b> ${esc(document.getElementById('company').value||'—')}<br><b>Lieu :</b> ${esc(document.getElementById('place').value||'BÉCHÉFAA')}</p>
<table class="summary"><thead><tr><th>Désignation</th><th>Quantité</th><th>Prix TTC / repas</th><th>Total TTC</th></tr></thead><tbody><tr><td>Repas</td><td>${q}</td><td>${money(u)}</td><td>${money(ttc)}</td></tr></tbody></table>
<div class="total">TOTAL TTC : ${money(ttc)}</div><p class="muted" style="text-align:right">HT : ${money(ht)} · TVA ${vat.toLocaleString('fr-FR')} % : ${money(tax)}</p>
<p><b>Motif / observations :</b><br>${esc(document.getElementById('reason').value||'—')}</p>
<div class="legal">Document généré depuis BÉCHÉFAA-Caisse. Vérifiez les informations avant impression et conservez les justificatifs nécessaires à votre comptabilité.</div>`}
document.getElementById('date').value=new Date().toISOString().slice(0,10);refresh();
['date','ref','name','company','qty','unit','vat','place','reason'].forEach(id=>document.getElementById(id).addEventListener('input',refresh));
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
