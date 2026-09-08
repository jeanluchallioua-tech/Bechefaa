"""Phase 3.8 — quantités tactiles dans le bloc Commande du POS.

Ajoute directement les contrôles - / quantité / + dans le HTML produit par
renderOrder, puis gère les clics avec le tableau ORDER existant.
Aucun changement backend, fiscal, Z, Cuisine, ticket ou catalogue.
"""
from flask import request


def register_pos_quantity_phase38(app):
    @app.after_request
    def inject_pos_quantity_phase38(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)

        old = '<button class="remove" data-action="remove-line" data-index="${i}">Retirer</button>'
        new = '''<div class="phase38-qty"><button type="button" data-qminus="${i}">−</button><span class="qval">${Number(l.qty||1)}</span><button type="button" data-qplus="${i}">+</button><span class="phase38-line-total">${(Number(l.unit_price||0)*Number(l.qty||1)).toFixed(2).replace('.',',')} €</span></div><button class="remove" data-action="remove-line" data-index="${i}">Retirer</button>'''
        html = html.replace(old, new)

        addon = r'''
<style>
.phase38-qty{display:flex;align-items:center;gap:7px;margin-top:8px;margin-bottom:4px}
.phase38-qty button{width:38px;height:34px;border:1px solid #cfd4dc;border-radius:8px;background:#f4f5f7;font-size:20px;font-weight:900;cursor:pointer;touch-action:manipulation}
.phase38-qty .qval{min-width:34px;text-align:center;font-size:16px;font-weight:900}
.phase38-line-total{margin-left:auto;font-size:13px;font-weight:800}
</style>
<script>
document.addEventListener('click',function(e){
  const minus=e.target.closest('[data-qminus]');
  const plus=e.target.closest('[data-qplus]');
  if(!minus&&!plus)return;
  e.preventDefault();
  e.stopPropagation();
  const node=minus||plus;
  const i=Number(node.getAttribute(minus?'data-qminus':'data-qplus'));
  if(!Number.isInteger(i)||!ORDER[i])return;
  const current=Math.max(1,Number(ORDER[i].qty||1));
  ORDER[i].qty=minus?Math.max(1,current-1):current+1;
  renderOrder();
},true);
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
