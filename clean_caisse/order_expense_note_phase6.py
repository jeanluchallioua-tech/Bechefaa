"""Note de frais thermique liée à une commande existante.

Ajoute un bouton dans Commandes / Historique. Le nombre de repas est choisi
au clic puis la note est générée en 80 mm à partir des données de la commande.
"""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from flask import Response, request


def register_order_expense_note_phase6(app, db, ensure_order_schema):
    def money(v):
        return f"{float(v or 0):.2f}".replace(".", ",") + " EUR"

    def identity(conn):
        try:
            rows = conn.execute(
                "SELECT setting_key,setting_value FROM caisse_restaurant_settings"
            ).fetchall()
            return {str(r["setting_key"]): str(r["setting_value"] or "") for r in rows}
        except Exception:
            return {}

    @app.get("/impression/note-de-frais/<order_id>")
    def print_expense_note_phase6(order_id):
        try:
            persons = int(request.args.get("persons") or 1)
        except (TypeError, ValueError):
            persons = 1
        persons = max(1, min(persons, 99))

        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2) NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(5,2) NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2) NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2) NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_status TEXT NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_method TEXT NULL")
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12,2) NULL")
                row = conn.execute(
                    """SELECT id,total,created_at,
                              total_ht,tax_rate,tax_amount,total_ttc,
                              payment_status,payment_method,paid_amount
                       FROM caisse_orders WHERE id=%s LIMIT 1""",
                    (order_id,),
                ).fetchone()
                cfg = identity(conn)
                conn.commit()
            if not row:
                return "Commande introuvable", 404
        except Exception as exc:
            return "Note de frais indisponible : " + escape(str(exc)), 500

        total_ttc = float(row.get("total_ttc") if row.get("total_ttc") is not None else row.get("total") or 0)
        rate = float(row.get("tax_rate") if row.get("tax_rate") is not None else 10)
        total_ht = row.get("total_ht")
        tax_amount = row.get("tax_amount")
        if total_ht is None or tax_amount is None:
            total_ht = round(total_ttc / (1 + rate / 100), 2)
            tax_amount = round(total_ttc - total_ht, 2)
        else:
            total_ht = float(total_ht)
            tax_amount = float(tax_amount)

        paid_amount = float(row.get("paid_amount") or 0)
        payment_status = str(row.get("payment_status") or "").strip().upper()
        if paid_amount <= 0 and payment_status not in {"PAYÉE","PAYEE","PAID","ENCAISSÉE","ENCAISSEE"}:
            return "Note de frais disponible uniquement après encaissement.", 409

        created = row.get("created_at")
        try:
            dt = datetime.fromtimestamp(float(created) / 1000, tz=ZoneInfo("Europe/Paris"))
        except Exception:
            dt = datetime.now(ZoneInfo("Europe/Paris"))

        name = str(cfg.get("name") or "BÉCHÉFAA").strip()
        address = str(cfg.get("address") or "").strip()
        postal = str(cfg.get("postal_code") or "").strip()
        city = str(cfg.get("city") or "Fontenay-sous-Bois").strip()
        siret = str(cfg.get("siret") or "").strip()
        phone = str(cfg.get("phone") or "").strip()
        rate_text = f"{rate:g}".replace(".", ",")

        details = []
        if address:
            details.append(escape(address))
        locality = " ".join(x for x in (postal, city) if x)
        if locality:
            details.append(escape(locality))
        if siret:
            details.append("Siret : " + escape(siret))
        if phone:
            details.append("Tel : " + escape(phone))

        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Note de frais</title>
<style>
@page{{size:80mm auto;margin:2.5mm}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#000;font-family:"Courier New",monospace}}
.ticket{{width:74mm;margin:0 auto;padding:2mm 1mm;font-size:11px;line-height:1.25}}
.brand{{text-align:center;font:bold 21px Arial,sans-serif;margin:1mm 0 2mm}}
.title{{text-align:center;font-weight:bold;margin:1mm 0}}.center{{text-align:center}}.sep{{border-top:1px dashed #000;margin:2.5mm 0}}
.row{{display:flex;justify-content:space-between;gap:3mm}}.row b{{white-space:nowrap}}.totals .row{{margin:1mm 0}}.grand{{font-weight:bold;border-top:1px dashed #000;border-bottom:1px dashed #000;padding:2mm 0;margin-top:2mm}}
.actions{{display:flex;gap:8px;justify-content:center;margin:14px}}.actions button{{padding:10px 14px;border:0;border-radius:8px;background:#111;color:#fff;font-weight:bold;cursor:pointer}}
@media print{{.actions{{display:none}}}}
</style></head><body><div class="ticket">
<div class="brand">{escape(name)}</div>
<div class="title">Ticket Note de Frais</div>
<div class="center">{escape(name)} Restaurant</div>
<div class="center">{'<br>'.join(details)}</div>
<div class="center">Date &amp; Heure : {dt.strftime("%d/%m/%Y %H:%M")}</div>
<div class="center">Nombre de repas : {persons}</div>
<div class="sep"></div>
<div class="totals">
<div class="row"><span>TOTAL HT {escape(rate_text)}% :</span><b>{money(total_ht)}</b></div>
<div class="row"><span>TVA {escape(rate_text)}% :</span><b>{money(tax_amount)}</b></div>
<div class="grand">
<div class="row"><span>TOTAL HT :</span><b>{money(total_ht)}</b></div>
<div class="row"><span>TOTAL TVA :</span><b>{money(tax_amount)}</b></div>
<div class="row"><span>TOTAL TTC :</span><b>{money(total_ttc)}</b></div>
</div></div>
</div><div class="actions"><button onclick="window.print()">Imprimer</button><button onclick="window.close()">Fermer</button></div>
</body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.after_request
    def inject_expense_note_button_phase6(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        if "bechefaa-expense-note-phase6" in html:
            return response
        addon = r'''
<style id="bechefaa-expense-note-phase6">
.expense-note-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#111;background:#e0ad2f;cursor:pointer;margin-left:6px}
.expense-note-backdrop{position:fixed;inset:0;background:#0008;z-index:999999;display:flex;align-items:center;justify-content:center;padding:18px}
.expense-note-modal{width:min(390px,95vw);background:#fff;border-radius:16px;padding:20px;box-shadow:0 20px 60px #0005}
.expense-note-modal h3{margin:0 0 8px}.expense-note-modal p{color:#667085;font-size:13px}.expense-note-modal input{width:100%;min-height:48px;border:1px solid #cfd4dc;border-radius:9px;padding:10px;font-size:18px}
.expense-note-actions{display:flex;gap:8px;margin-top:14px}.expense-note-actions button{flex:1;border:0;border-radius:9px;padding:11px;font-weight:900;cursor:pointer}.expense-note-cancel{background:#e5e7eb}.expense-note-print{background:#111827;color:#fff}
</style>
<script id="bechefaa-expense-note-script-phase6">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function orderId(card){
   const btns=[...card.querySelectorAll('button')];
   for(const b of btns){
     const oc=b.getAttribute('onclick')||'';
     let m=oc.match(/viewOrder\('([^']+)'\)/);
     if(!m)m=oc.match(/editOrder\('([^']+)'\)/);
     if(m)return m[1];
   }
   return '';
 }
 function open(id){
   const back=document.createElement('div');back.className='expense-note-backdrop';
   back.innerHTML='<div class="expense-note-modal"><h3>Note de frais</h3><p>Indiquez le nombre de repas à faire apparaître sur le justificatif.</p><input type="number" min="1" max="99" step="1" value="1" inputmode="numeric"><div class="expense-note-actions"><button type="button" class="expense-note-cancel">Annuler</button><button type="button" class="expense-note-print">Imprimer</button></div></div>';
   document.body.appendChild(back);
   const close=()=>back.remove();
   back.querySelector('.expense-note-cancel').onclick=close;
   back.addEventListener('click',e=>{if(e.target===back)close()});
   back.querySelector('.expense-note-print').onclick=()=>{
     const n=Math.max(1,Math.min(99,parseInt(back.querySelector('input').value||'1',10)||1));
     if(/Android/i.test(navigator.userAgent||'')){
       if(typeof window.bechefaaPrintExpenseNote!=='function'){
         alert('Impression Epson impossible : TM Print Assistant non initialisé.');
         return;
       }
       const btn=back.querySelector('.expense-note-print');
       btn.disabled=true;btn.textContent='Impression…';
       window.bechefaaPrintExpenseNote(id,n)
         .then(()=>close())
         .catch(err=>{alert('Impression Epson impossible : '+((err&&err.message)||err||'Erreur'));btn.disabled=false;btn.textContent='Imprimer';});
       return;
     }
     window.open('/impression/note-de-frais/'+encodeURIComponent(id)+'?persons='+encodeURIComponent(n),'_blank');
     close();
   };
   setTimeout(()=>back.querySelector('input').select(),0);
 }
 async function paidMap(){
   try{
     const r=await fetch('/api/orders/history-meta-phase44',{cache:'no-store'}),d=await r.json();
     return d&&d.ok&&d.orders?d.orders:{};
   }catch(e){return {}}
 }
 async function addPaid(){
   const meta=await paidMap();
   document.querySelectorAll('.order').forEach(card=>{
     if(card.querySelector('.expense-note-btn'))return;
     const id=orderId(card);if(!id)return;
     const m=meta[id]||{};
     const ps=String(m.payment_status||'').toUpperCase();
     const paid=Number(m.paid_amount||0)>0||['PAYÉE','PAYEE','PAID','ENCAISSÉE','ENCAISSEE'].includes(ps);
     if(!paid)return;
     const btn=document.createElement('button');btn.type='button';btn.className='expense-note-btn';btn.textContent='Note de frais';
     btn.addEventListener('click',()=>open(id));card.appendChild(btn);
   });
 }
 ready(function(){
   addPaid();
   const target=document.getElementById('list')||document.body;
   new MutationObserver(()=>addPaid()).observe(target,{childList:true,subtree:true});
 });
})();
</script>'''
        html=html.replace("</body>",addon+"</body>")
        response.set_data(html);response.content_length=len(response.get_data())
        return response
