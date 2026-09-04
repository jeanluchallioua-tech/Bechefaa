// BÉCHÉFAA V2 — identité client / historique / tickets
// Ne touche pas au catalogue ni au moteur POS.
(() => {
  const esc = v => String(v ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  const money = n => Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});

  async function getJSON(url){
    const r=await fetch(url+(url.includes('?')?'&':'?')+'t='+Date.now(),{cache:'no-store'});
    if(!r.ok) throw new Error('HTTP '+r.status);
    return r.json();
  }

  async function resolveOrder(id){
    let o=null;
    try{o=await getJSON('/api/orders/'+encodeURIComponent(id));}catch(e){}
    if(!o) o=window.BECHEFAA_APP?.findOrder?.(id)||null;
    if(!o) return null;

    let clients=[];
    try{clients=await getJSON('/api/clients');}catch(e){clients=window.BECHEFAA_APP?.getClients?.()||[];}
    const norm=v=>String(v||'').trim().toLowerCase();
    let c=null;
    if(o.customerId) c=(clients||[]).find(x=>String(x.id)===String(o.customerId))||null;
    if(!c && o.phone) c=(clients||[]).find(x=>norm(x.phone)===norm(o.phone))||null;
    if(!c && o.email) c=(clients||[]).find(x=>norm(x.email)===norm(o.email))||null;
    if(!c && o.customer && norm(o.customer)!=='client comptoir') c=(clients||[]).find(x=>norm(x.name)===norm(o.customer))||null;

    const first=String(c?.firstName||'').trim();
    const last=String(c?.lastName||'').trim();
    const full=(String(c?.name||'').trim() || [first,last].filter(Boolean).join(' ') || String(o.customer||'').trim() || 'Client comptoir');
    return {
      ...o,
      customer: full,
      firstName:first,
      lastName:last,
      phone:String(c?.phone||o.phone||''),
      email:String(c?.email||o.email||''),
      address:String(c?.address||o.address||''),
      postalCode:String(c?.postalCode||o.postalCode||''),
      city:String(c?.city||o.city||'')
    };
  }

  function fmtOptions(txt){
    if(!txt)return '';
    return String(txt).split(';;').filter(Boolean).map(b=>{
      const [t,r='']=b.split('::');
      const vals=r.split('|').filter(Boolean).map(x=>`<span style="display:block;margin-left:2mm">${esc(x)}</span>`).join('');
      return `<div style="margin:.8mm 0"><strong style="display:block">${esc(t)} :</strong>${vals}</div>`;
    }).join('');
  }

  function closeModal(){
    const m=document.getElementById('orderModal');
    if(m) m.classList.add('hidden');
    document.body.style.overflow='';
    document.documentElement.style.overflow='';
  }

  async function showOrder(id){
    const o=await resolveOrder(id); if(!o)return;
    const title=document.getElementById('orderModalTitle');
    const meta=document.getElementById('orderModalMeta');
    const body=document.getElementById('orderEditBody');
    const save=document.getElementById('saveOrderEdit');
    const modal=document.getElementById('orderModal');
    if(!modal||!body)return;
    if(title)title.textContent=`Commande #${o.num||o.id}`;
    if(meta)meta.textContent=`${o.customer||'Client comptoir'} · ${o.status||''}`;
    if(save)save.style.display='none';
    const identity=[
      ['Client',o.customer],['Téléphone',o.phone],['Email',o.email],['Adresse',o.address],
      ['Code postal',o.postalCode],['Ville',o.city],['Type',o.source]
    ];
    body.innerHTML=`
      <div class="edit-client-grid">
        ${identity.map(([k,v])=>`<label>${esc(k)}<input value="${esc(v)}" disabled></label>`).join('')}
      </div>
      ${(!o.customerId && o.customer==='Client comptoir' && !o.phone && !o.email)?'<div class="sub" style="margin:10px 0">Aucun client n’est associé à cette commande.</div>':''}
      <h3>Articles</h3>
      ${(o.items||[]).map(i=>`<div class="edit-item"><div class="edit-item-main"><input class="edit-qty" value="${Number(i.qty||1)}" disabled><div><strong>${esc(i.name)}</strong>${fmtOptions(i.optionsText)}</div><strong>${money((i.unit||0)*(i.qty||1))}</strong></div></div>`).join('')}`;
    modal.classList.remove('hidden');
    document.body.style.overflow='hidden';
  }

  async function printTicket(id,delivery){
    const o=await resolveOrder(id); if(!o)return alert('Commande introuvable.');
    const name=esc(o.customer||'Client comptoir');
    const identity=delivery
      ? `<section class="customer-block"><div class="customer-name">${name}</div>
          ${o.phone?`<div><b>Tél :</b> ${esc(o.phone)}</div>`:''}
          ${o.email?`<div><b>Email :</b> ${esc(o.email)}</div>`:''}
          ${o.address?`<div><b>Adresse :</b> ${esc(o.address)}</div>`:''}
          ${(o.postalCode||o.city)?`<div><b>CP / Ville :</b> ${esc(o.postalCode)} ${esc(o.city)}</div>`:''}
        </section>`
      : `<section class="customer-block compact"><div class="customer-name">${name}</div></section>`;
    const items=(o.items||[]).map(i=>`<div class="item"><div class="item-main"><span class="qty">${Number(i.qty||1)}×</span><span class="item-name">${esc(i.name)}</span><span class="item-price">${money((i.unit||0)*(i.qty||1))}</span></div>${i.optionsText?`<div class="item-options">${fmtOptions(i.optionsText)}</div>`:''}</div>`).join('');
    const html=`<!doctype html><html><head><meta charset="utf-8"><title>Commande #${esc(o.num||o.id)}</title><style>
      @page{size:80mm auto;margin:2.5mm}*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff}body{width:75mm;margin:0 auto;padding:1.5mm 1mm 4mm;font-family:Arial,Helvetica,sans-serif;font-size:11.5pt;line-height:1.25;color:#000}.brand{text-align:center;font-size:18pt;font-weight:900;margin-bottom:1mm}.mode{text-align:center;font-size:11pt;font-weight:900;border-top:1.5px solid #000;border-bottom:1.5px solid #000;padding:1.5mm 0;margin-bottom:2mm}.order-number{text-align:center;font-size:20pt;font-weight:900;margin:1.5mm 0 2mm}.customer-block{font-size:11pt;margin-bottom:2mm}.customer-name{font-size:14pt;font-weight:900;margin-bottom:1mm}.sep{border-top:1px dashed #000;margin:2mm 0}.item{padding:1.3mm 0;border-bottom:1px dotted #777}.item-main{display:grid;grid-template-columns:9mm 1fr auto;gap:1.5mm}.qty,.item-name,.item-price{font-weight:900}.item-price{text-align:right;white-space:nowrap}.item-options{font-size:10pt;margin:1mm 0 0 10.5mm}.total{display:flex;justify-content:space-between;font-size:17pt;font-weight:900;border-top:2px solid #000;border-bottom:2px solid #000;padding:2mm 0;margin-top:2.5mm}.footer{text-align:center;font-size:9pt;margin-top:3mm}
    </style></head><body><div class="brand">BÉCHÉFAA</div><div class="mode">${delivery?'LIVRAISON':'COMPTOIR / EMPORTER'}</div><div class="order-number">N° ${esc(o.num||o.id)}</div>${identity}<div class="sep"></div>${items}<div class="total"><span>TOTAL</span><span>${money(o.total)}</span></div><div class="footer">Merci</div><script>window.onload=()=>setTimeout(()=>window.print(),150)<\/script></body></html>`;
    const w=window.open('','_blank','width=480,height=760');
    if(!w)return alert('Autorisez les fenêtres pop-up pour imprimer.');
    w.document.open();w.document.write(html);w.document.close();
  }

  document.addEventListener('click',e=>{
    let b=e.target.closest('[data-view-order]');
    if(b){e.preventDefault();e.stopImmediatePropagation();showOrder(b.dataset.viewOrder);return;}
    b=e.target.closest('[data-print-counter]');
    if(b){e.preventDefault();e.stopImmediatePropagation();printTicket(b.dataset.printCounter,false);return;}
    b=e.target.closest('[data-print-delivery]');
    if(b){e.preventDefault();e.stopImmediatePropagation();printTicket(b.dataset.printDelivery,true);return;}
    if(e.target.closest('#closeOrderModal')){e.preventDefault();e.stopImmediatePropagation();closeModal();return;}
    const modal=document.getElementById('orderModal');
    if(modal && !modal.classList.contains('hidden') && e.target===modal){closeModal();}
  },true);

  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
})();
