"""Optimisation tactile POS : ajout immédiat au panier des produits sans options.

Module isolé, sans Wix / V1 / localStorage.
"""
from flask import request


def register_pos_quick_add(app):
    @app.after_request
    def inject_quick_add(response):
        if request.path == "/pos" and response.status_code == 200 and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            script = r'''
<script>
(function(){
  if(window.__BECHEFAA_QUICK_ADD__) return;
  window.__BECHEFAA_QUICK_ADD__ = true;
  let catalogMap = {};

  function loadMap(){
    fetch('/api/catalog/summary',{cache:'no-store'})
      .then(r=>r.json())
      .then(d=>{(d.items||[]).forEach(p=>{catalogMap[String(p.id)] = p;});})
      .catch(()=>{});
  }

  function directAdd(p){
    if(!p) return;
    ORDER.push({
      line_id:'line-'+Date.now()+'-'+Math.random().toString(16).slice(2),
      product_id:String(p.id||''),
      name:String(p.name||''),
      qty:1,
      unit_price:Number(Number(p.price||0).toFixed(2)),
      options:[]
    });
    document.getElementById('order-message').innerHTML='';
    renderOrder();
  }

  document.addEventListener('click',function(e){
    const card=e.target.closest && e.target.closest('.product');
    if(!card || !document.getElementById('grid') || !document.getElementById('grid').contains(card)) return;
    const p=catalogMap[String(card.dataset.id||'')];
    if(!p || Number(p.optionGroups||0)!==0) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    directAdd(p);
  },true);

  loadMap();
})();
</script>
'''
            html = html.replace("</body>", script + "</body>")
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response
