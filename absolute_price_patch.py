# BÉCHÉFAA V0.5.57 — prix total par variante (ex. Nombre de Tender)
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
INDEX = BASE / "static" / "index.html"

try:
    src = APP_JS.read_text(encoding="utf-8")

    # Les listes centrales nommées « Nombre de Tender » utilisent un prix TOTAL,
    # pas un supplément ajouté au prix de base.
    old_group = 'GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};'
    new_group = '''const groupTitle=String(g?.title||g?.key||"Options");
    const priceMode=(g?.priceMode==="absolute"||norm(groupTitle)==="nombre de tender")?"absolute":"extra";
    GROUPS[key]={title:groupTitle,required:!!g?.required,max:Math.max(0,Number(g?.max??1)),priceMode,choices};'''
    if old_group in src:
        src = src.replace(old_group, new_group, 1)

    # Calcul du prix : une option absolute remplace le prix de base.
    old_calc = 'function optionExtra(){return Object.values(selections).flat().reduce((s,x)=>s+price(x.price),0)}\nfunction updateOptionTotal(){$("optTotal").textContent=euro(price(current.price)+optionExtra())}'
    new_calc = '''/* V0.5.57 ABSOLUTE VARIANT PRICE */
function optionBasePrice(){
 for(const [k,vals] of Object.entries(selections||{})){
  if(GROUPS[k]?.priceMode==="absolute" && Array.isArray(vals) && vals.length)return Number(vals[0].price||0);
 }
 return Number(current?.price||0);
}
function optionExtra(){
 return Object.entries(selections||{}).reduce((sum,[k,vals])=>{
  if(GROUPS[k]?.priceMode==="absolute")return sum;
  return sum+(Array.isArray(vals)?vals:[]).reduce((s,x)=>s+price(Number(x.price||0)),0);
 },0);
}
function updateOptionTotal(){$("optTotal").textContent=euro(price(optionBasePrice())+optionExtra())}'''
    if old_calc in src:
        src = src.replace(old_calc, new_calc, 1)

    # Même règle lors de l'ajout au panier / modification de ligne.
    src = src.replace(
        'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=exactKey(current);',
        'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(optionBasePrice())+optionExtra(),ek=exactKey(current);',
        1
    )

    APP_JS.write_text(src, encoding="utf-8")

    html = INDEX.read_text(encoding="utf-8")
    html = re.sub(r'app\.js\?v=\d+', 'app.js?v=0557', html, count=1)
    INDEX.write_text(html, encoding="utf-8")
    print("BÉCHÉFAA V0.5.57: prix total Nombre de Tender actif.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.57 patch error:", exc)
