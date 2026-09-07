"""Phase 1 — ajout d'un plat lors de la modification d'une commande.

Le catalogue et les options proviennent exclusivement de catalog_admin_v2 via les API clean.
Aucun Wix / V1 / localStorage.
"""
from flask import request


def register_history_add_product(app):
    @app.after_request
    def inject_history_add_product(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
.phase1-add-product{width:100%;margin:10px 0 4px;border:1px solid #14804a;background:#e8f7ee;color:#176438;border-radius:9px;padding:12px;font-weight:800;cursor:pointer}
.phase1-product-modal{position:fixed;inset:0;background:#0009;display:none;align-items:center;justify-content:center;padding:18px;z-index:12000}
.phase1-product-modal.open{display:flex}.phase1-product-panel{background:#fff;width:min(820px,96vw);max-height:90vh;overflow:auto;border-radius:15px;padding:18px}.phase1-product-head{display:flex;gap:10px;align-items:center}.phase1-product-head h2{margin:0;flex:1}.phase1-product-search{width:100%;margin:12px 0;padding:12px;border:1px solid #ccd1d8;border-radius:9px;font-size:16px}.phase1-product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}.phase1-product-card{border:1px solid #d9dde3;border-radius:10px;padding:12px;background:#fff;cursor:pointer;text-align:left}.phase1-product-card b{display:block;font-size:15px}.phase1-product-card span{display:block;color:#667085;font-size:12px;margin-top:5px}.phase1-product-card strong{display:block;font-size:18px;margin-top:8px}.phase1-options{margin-top:10px}.phase1-opt-group{border-top:1px solid #eee;padding-top:11px;margin-top:11px}.phase1-opt-head{display:flex;justify-content:space-between;gap:10px;margin-bottom:7px}.phase1-opt-rule{font-size:11px;color:#667085}.phase1-opt{width:100%;display:flex;justify-content:space-between;gap:8px;padding:10px;margin:5px 0;border:1px solid #d9dde3;border-radius:8px;background:#f7f8fa;cursor:pointer;text-align:left}.phase1-opt.selected{background:#111827;color:#fff;border-color:#111827}.phase1-add-confirm{width:100%;margin-top:14px;border:0;border-radius:9px;padding:13px;background:#14804a;color:#fff;font-weight:800;cursor:pointer}.phase1-back{border:1px solid #ccd1d8;background:#fff;border-radius:8px;padding:9px 11px;font-weight:700;cursor:pointer}.phase1-product-error{padding:10px;background:#fff0ee;color:#9d261d;border-radius:8px;margin:10px 0}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const lines=document.getElementById('mlines');
   if(!lines)return;
   const add=document.createElement('button');add.type='button';add.className='phase1-add-product';add.textContent='+ Ajouter un plat';lines.insertAdjacentElement('afterend',add);

   const modal=document.createElement('div');modal.className='phase1-product-modal';modal.innerHTML='<div class="phase1-product-panel"><div class="phase1-product-head"><h2 id="p1-title">Ajouter un plat</h2><button type="button" class="phase1-back" id="p1-close">Fermer</button></div><input id="p1-search" class="phase1-product-search" placeholder="Rechercher un produit…"><div id="p1-content"></div></div>';document.body.appendChild(modal);
   const content=document.getElementById('p1-content'),search=document.getElementById('p1-search');
   let products=[],currentProduct=null,currentGroups=[],selections={};

   function money(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
   function e(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
   function optionInfo(v){if(v===null||v===undefined)return{name:'',price:0};if(Array.isArray(v))return{name:String(v[0]??''),price:Number(v[1]||0)};if(typeof v==='string'||typeof v==='number')return{name:String(v),price:0};if(typeof v==='object')return{name:String(v.name||v.label||v.title||v.value||v.id||''),price:Number(v.price||v.extraPrice||v.supplement||0)};return{name:String(v),price:0}}
   function groupInfo(g,i){let name=(g&&typeof g==='object'&&!Array.isArray(g)?(g.name||g.label||g.title):'')||('Groupe '+(i+1));let vals=(g&&typeof g==='object'&&!Array.isArray(g)?(g.options||g.values||g.items||g.choices):null);if(!Array.isArray(vals))vals=Array.isArray(g)?g:[];let max=0,required=false;if(g&&typeof g==='object'&&!Array.isArray(g)){max=Number(g.max??g.maxChoices??g.maximum??0)||0;required=Boolean(g.required)}return{name,vals,max,required}}
   function key(gi,vi){return gi+':'+vi}
   function picked(gi){return Object.keys(selections).filter(k=>k.startsWith(gi+':')&&selections[k])}
   function selectedOptions(){let out=[];currentGroups.forEach((g,gi)=>{let info=groupInfo(g,gi);info.vals.forEach((v,vi)=>{if(selections[key(gi,vi)]){let oi=optionInfo(v);out.push({group:info.name,name:oi.name,price:oi.price})}})});return out}
   function totalExtra(){return selectedOptions().reduce((s,o)=>s+Number(o.price||0),0)}
   function requiredMissing(){return currentGroups.some((g,gi)=>{let info=groupInfo(g,gi);return info.required&&picked(gi).length===0})}

   function renderProducts(){let q=search.value.toLowerCase().trim(),rows=products.filter(p=>!q||String(p.name||'').toLowerCase().includes(q)||String(p.category||'').toLowerCase().includes(q));content.innerHTML='<div class="phase1-product-grid">'+rows.map(p=>`<button type="button" class="phase1-product-card" data-product="${e(p.id)}"><b>${e(p.name)}</b><span>${e(p.category||'')}</span><strong>${money(p.price)}</strong>${Number(p.optionGroups||0)>0?'<span>Options disponibles</span>':''}</button>`).join('')+'</div>';content.querySelectorAll('[data-product]').forEach(b=>b.onclick=()=>chooseProduct(products.find(p=>String(p.id)===String(b.dataset.product))))}
   async function openPicker(){if(typeof EDIT==='undefined'||!EDIT)return;modal.classList.add('open');document.getElementById('p1-title').textContent='Ajouter un plat';search.style.display='block';search.value='';content.innerHTML='<div>Chargement du catalogue…</div>';try{let r=await fetch('/api/catalog/summary',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Catalogue indisponible');products=d.items||[];renderProducts();setTimeout(()=>search.focus(),50)}catch(err){content.innerHTML='<div class="phase1-product-error">'+e(err.message)+'</div>'}}
   function closePicker(){modal.classList.remove('open');currentProduct=null;currentGroups=[];selections={}}
   function addLine(options){if(!EDIT||!currentProduct)return;let opts=options||[],unit=Number(currentProduct.price||0)+opts.reduce((s,o)=>s+Number(o.price||0),0);EDIT.items=EDIT.items||[];EDIT.items.push({line_id:'line-edit-'+Date.now()+'-'+Math.random().toString(16).slice(2),product_id:String(currentProduct.id||''),name:String(currentProduct.name||''),qty:1,unit_price:Number(unit.toFixed(2)),options:opts,options_text:opts.map(o=>(o.group?o.group+': ':'')+o.name).join(' • '),prepared:false});renderEdit();closePicker()}
   async function chooseProduct(p){if(!p)return;currentProduct=p;selections={};if(Number(p.optionGroups||0)===0){addLine([]);return}search.style.display='none';content.innerHTML='<div>Chargement des options…</div>';try{let r=await fetch('/api/catalog/product/'+encodeURIComponent(p.id)+'/options',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Options indisponibles');currentProduct=Object.assign({},p,d.product||{});currentGroups=Array.isArray(d.groups)?d.groups:[];renderOptions()}catch(err){content.innerHTML='<div class="phase1-product-error">'+e(err.message)+'</div><button type="button" class="phase1-back" id="p1-back-error">Retour</button>';document.getElementById('p1-back-error').onclick=()=>{search.style.display='block';renderProducts()}}}
   function renderOptions(){document.getElementById('p1-title').textContent='Options • '+String(currentProduct.name||'');let base=Number(currentProduct.price||0),groups=currentGroups.map((g,gi)=>{let info=groupInfo(g,gi),rule=[];if(info.required)rule.push('obligatoire');if(info.max===1)rule.push('1 choix');else if(info.max>1)rule.push(info.max+' choix max');let vals=info.vals.map((v,vi)=>{let oi=optionInfo(v),sel=!!selections[key(gi,vi)];return `<button type="button" class="phase1-opt ${sel?'selected':''}" data-gi="${gi}" data-vi="${vi}"><span>${sel?'✓ ':''}${e(oi.name)}</span><span>${oi.price?('+'+money(oi.price)):''}</span></button>`}).join('');return `<div class="phase1-opt-group"><div class="phase1-opt-head"><b>${e(info.name)}</b><span class="phase1-opt-rule">${e(rule.join(' • '))}</span></div>${vals}</div>`}).join('');content.innerHTML=`<button type="button" class="phase1-back" id="p1-back">← Produits</button><div class="phase1-options">${groups}</div><div style="font-size:20px;font-weight:800;margin-top:12px">Prix : ${money(base+totalExtra())}</div><div id="p1-opt-msg"></div><button type="button" class="phase1-add-confirm" id="p1-confirm">Ajouter à la commande</button>`;document.getElementById('p1-back').onclick=()=>{document.getElementById('p1-title').textContent='Ajouter un plat';search.style.display='block';renderProducts()};content.querySelectorAll('[data-gi]').forEach(b=>b.onclick=()=>toggle(Number(b.dataset.gi),Number(b.dataset.vi)));document.getElementById('p1-confirm').onclick=()=>{if(requiredMissing()){document.getElementById('p1-opt-msg').innerHTML='<div class="phase1-product-error">Sélectionnez les options obligatoires.</div>';return}addLine(selectedOptions())}}
   function toggle(gi,vi){let info=groupInfo(currentGroups[gi],gi),k=key(gi,vi);if(selections[k])delete selections[k];else{if(info.max===1)picked(gi).forEach(x=>delete selections[x]);else if(info.max>1&&picked(gi).length>=info.max)return;selections[k]=true}renderOptions()}

   add.onclick=openPicker;search.oninput=renderProducts;document.getElementById('p1-close').onclick=closePicker;modal.addEventListener('click',ev=>{if(ev.target===modal)closePicker()});document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&modal.classList.contains('open'))closePicker()});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
