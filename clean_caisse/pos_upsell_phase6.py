"""Phase 6 — upsell Caisse avant enregistrement.

UI uniquement sur /pos :
- avant l'enregistrement, propose la catégorie Boissons ;
- après ajout d'une boisson ou "Non merci", propose Desserts ;
- après ajout d'un dessert ou "Non merci", reprend l'enregistrement normal.
Aucune modification des API commandes, prix, cuisine ou PostgreSQL.
"""
from flask import request


def register_pos_upsell_phase6(app):
    @app.after_request
    def inject_pos_upsell_phase6(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
#phase6-upsell-bar{display:none;position:sticky;top:0;z-index:8500;margin:0 0 14px;padding:12px 14px;border:2px solid #ffb000;border-radius:12px;background:#111;color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.28)}
#phase6-upsell-bar.show{display:flex;align-items:center;justify-content:space-between;gap:14px}
#phase6-upsell-bar .phase6-upsell-copy{font-size:18px;font-weight:900;color:#ffd21f}
#phase6-upsell-bar .phase6-upsell-sub{display:block;margin-top:2px;font-size:13px;font-weight:700;color:#fff}
#phase6-upsell-skip{border:1px solid #ffb000;border-radius:10px;background:#1b1b1b;color:#ffd21f;padding:10px 16px;font-weight:900;cursor:pointer;white-space:nowrap}
#phase6-upsell-skip:hover{background:#ffb000;color:#111}
</style>
<script>
(function(){
 if(window.__BECHEFAA_POS_UPSELL_PHASE6__)return;
 window.__BECHEFAA_POS_UPSELL_PHASE6__=true;
 let stage=null;
 let bypass=false;
 let baseline=0;
 let bar=null;

 const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
 const lineCount=()=>document.querySelectorAll('#order .order-line').length;

 function ensureBar(){
   if(bar)return bar;
   const grid=document.getElementById('grid');
   if(!grid||!grid.parentNode)return null;
   bar=document.createElement('div');
   bar.id='phase6-upsell-bar';
   bar.innerHTML='<div><div class="phase6-upsell-copy"></div><span class="phase6-upsell-sub"></span></div><button id="phase6-upsell-skip" type="button">NON MERCI</button>';
   grid.parentNode.insertBefore(bar,grid);
   bar.querySelector('#phase6-upsell-skip').addEventListener('click',function(){
     if(stage==='drink')showStage('dessert');else if(stage==='dessert')finishUpsell();
   });
   return bar;
 }

 function openCategory(name){
   const wanted=norm(name);
   const btn=Array.from(document.querySelectorAll('.cat')).find(b=>norm(b.dataset.cat||b.textContent)===wanted);
   if(!btn)return false;
   btn.click();
   setTimeout(()=>document.getElementById('grid')?.scrollIntoView({behavior:'smooth',block:'start'}),50);
   return true;
 }

 function showStage(next){
   stage=next;
   baseline=lineCount();
   const el=ensureBar();
   if(!el){finishUpsell();return}
   const isDrink=next==='drink';
   el.querySelector('.phase6-upsell-copy').textContent=isDrink?'🥤 UNE BOISSON AVEC LA COMMANDE ?':'🍰 UN DESSERT AVEC LA COMMANDE ?';
   el.querySelector('.phase6-upsell-sub').textContent=isDrink?'Choisissez une boisson ci-dessous ou appuyez sur Non merci.':'Choisissez un dessert ci-dessous ou appuyez sur Non merci.';
   el.classList.add('show');
   if(!openCategory(isDrink?'Boissons':'Desserts')){
     if(isDrink)showStage('dessert');else finishUpsell();
   }
 }

 function finishUpsell(){
   stage=null;
   if(bar)bar.classList.remove('show');
   const btn=document.querySelector('[data-action="save-order"]');
   if(!btn)return;
   bypass=true;
   btn.click();
   setTimeout(()=>{bypass=false},0);
 }

 document.addEventListener('click',function(e){
   const save=e.target.closest('[data-action="save-order"]');
   if(save&&!bypass&&!stage){
     e.preventDefault();
     e.stopImmediatePropagation();
     showStage('drink');
   }
 },true);

 const order=document.getElementById('order');
 if(order){
   new MutationObserver(function(){
     if(!stage)return;
     const now=lineCount();
     if(now<=baseline)return;
     if(stage==='drink')showStage('dessert');
     else if(stage==='dessert')finishUpsell();
   }).observe(order,{childList:true,subtree:true});
 }
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
