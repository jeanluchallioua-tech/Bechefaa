"""Phase 3.8 — quantités tactiles dans le bloc Commande du POS.

Modification purement front-end : ajoute - / quantité / + sur chaque ligne.
Le backend PostgreSQL sait déjà enregistrer qty ; aucun changement fiscal, Z,
Cuisine, ticket ou catalogue.
"""
from flask import request


def register_pos_quantity_phase38(app):
    @app.after_request
    def inject_pos_quantity_phase38(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        addon = r'''
<style>
.phase38-qty{display:flex;align-items:center;gap:7px;margin-top:8px}
.phase38-qty button{width:38px;height:34px;border:1px solid #cfd4dc;border-radius:8px;background:#f4f5f7;font-size:20px;font-weight:900;cursor:pointer;touch-action:manipulation}
.phase38-qty .qval{min-width:34px;text-align:center;font-size:16px;font-weight:900}
.phase38-line-total{margin-left:auto;font-size:13px;font-weight:800}
</style>
<script>
(function(){
 function enhance(){
   const order=document.getElementById('order');
   if(!order || !Array.isArray(window.ORDER || (typeof ORDER!=='undefined'?ORDER:null))) return;
   const lines=order.querySelectorAll('.order-line');
   lines.forEach((node,i)=>{
     if(node.querySelector('.phase38-qty') || !ORDER[i]) return;
     const q=Math.max(1,Number(ORDER[i].qty||1));
     const unit=Number(ORDER[i].unit_price||0);
     const box=document.createElement('div'); box.className='phase38-qty';
     box.innerHTML='<button type="button" data-qminus="'+i+'">−</button><span class="qval">'+q+'</span><button type="button" data-qplus="'+i+'">+</button><span class="phase38-line-total">'+(unit*q).toFixed(2).replace('.',',')+' €</span>';
     const remove=node.querySelector('[data-action="remove-line"]');
     if(remove) node.insertBefore(box,remove); else node.appendChild(box);
   });
 }
 document.addEventListener('click',function(e){
   const minus=e.target.closest('[data-qminus]'),plus=e.target.closest('[data-qplus]');
   if(!minus&&!plus)return;
   e.preventDefault();
   const i=Number((minus||plus).getAttribute(minus?'data-qminus':'data-qplus'));
   if(!Number.isInteger(i)||!ORDER[i])return;
   const current=Math.max(1,Number(ORDER[i].qty||1));
   ORDER[i].qty=minus?Math.max(1,current-1):current+1;
   renderOrder(); setTimeout(enhance,0);
 });
 const order=document.getElementById('order');
 if(order)new MutationObserver(enhance).observe(order,{childList:true,subtree:true});
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enhance);else enhance();
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
