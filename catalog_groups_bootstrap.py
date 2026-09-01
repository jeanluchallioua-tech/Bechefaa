# BÉCHÉFAA V0.5.58 — lien sûr options + garde-fou produits POS + prix total variantes
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"
APP_JS = BASE / "static" / "app.js"

try:
    src = INDEX.read_text(encoding="utf-8")

    # Nettoyage des anciens scripts expérimentaux.
    for tag in (
        '<script src="catalog-groups.js?v=0546"></script>\n',
        '<script src="catalog-options-workspace.js?v=0547"></script>\n',
        '<script src="catalog-options-workspace.js?v=0548"></script>\n',
    ):
        src = src.replace(tag, '')

    # Supprime les anciens boutons expérimentaux s'ils existent.
    src = src.replace('      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n', '')
    src = src.replace('      <a id="catalogOptionsManager" href="/options.html">⚙ Listes d\'options</a>\n', '')

    # Ajoute uniquement un lien HTML vers une page indépendante.
    anchor = '      <button id="catNewProduct">+ Produit</button>\n'
    link = anchor + '      <a id="catalogOptionsManager" href="/options.html" style="display:inline-block;padding:9px 12px;border:1px solid #bbb;border-radius:8px;text-decoration:none;color:#111;background:#fff;font-weight:700">⚙ Listes d\'options</a>\n'
    if 'id="catalogOptionsManager"' not in src and anchor in src:
        src = src.replace(anchor, link, 1)

    js = APP_JS.read_text(encoding="utf-8")

    # Garde-fou : si le Catalogue central renvoie 0 produit, ne jamais écraser
    # les produits embarqués dans index.html.
    guard_marker = 'V0.5.54 EMPTY CENTRAL CATALOG SAFETY'
    target = 'if(!data||!Array.isArray(data.products)||!Array.isArray(data.categories))return;'
    if guard_marker not in js and target in js:
        guard = target + '\n  /* V0.5.54 EMPTY CENTRAL CATALOG SAFETY */\n  if(data.products.length===0){\n   console.warn("BÉCHÉFAA: catalogue central vide, conservation de la carte embarquée.");\n   rc();rp();\n   return;\n  }'
        js = js.replace(target, guard, 1)

    # V0.5.58 : les listes "Nombre de Tender" et "Nombre d'oignons" utilisent
    # les montants saisis comme PRIX TOTAL du produit, et non comme supplément.
    if 'V0.5.58 ABSOLUTE QUANTITY PRICE' not in js:
        old_group = 'GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};'
        new_group = '''const centralTitle=String(g?.title||g?.key||"Options");
    const centralTitleNorm=norm(centralTitle);
    const centralPriceMode=(g?.priceMode==="absolute"||centralTitleNorm==="nombre de tender"||centralTitleNorm==="nombre d oignons")?"absolute":"extra";
    GROUPS[key]={title:centralTitle,required:!!g?.required,max:Math.max(0,Number(g?.max??1)),priceMode:centralPriceMode,choices};'''
        if old_group in js:
            js = js.replace(old_group, new_group, 1)

        old_render = '''function renderGroup(k){
 const g=GROUPS[k],meta=[g.required?"Obligatoire":"Facultatif",g.max?`max. ${g.max}`:"plusieurs choix"].join(" · ");
 return `<div class="optgroup"><h3>${g.title}</h3><div class="optmeta">${meta}</div><div class="optchoices">${g.choices.map(([n,p])=>`<button class="optchoice" data-g="${k}" data-n="${encodeURIComponent(n)}" data-p="${p}">${n}${p?` +${euro(price(p))}`:""}</button>`).join("")}</div></div>`
}'''
        new_render = '''function renderGroup(k){
 const g=GROUPS[k],meta=[g.required?"Obligatoire":"Facultatif",g.max?`max. ${g.max}`:"plusieurs choix"].join(" · ");
 return `<div class="optgroup"><h3>${g.title}</h3><div class="optmeta">${meta}</div><div class="optchoices">${g.choices.map(([n,p])=>`<button class="optchoice" data-g="${k}" data-n="${encodeURIComponent(n)}" data-p="${p}">${n}${g.priceMode==="absolute"?` · ${euro(price(p))}`:(p?` +${euro(price(p))}`:"")}</button>`).join("")}</div></div>`
}'''
        if old_render in js:
            js = js.replace(old_render, new_render, 1)

        old_calc = '''function optionExtra(){return Object.values(selections).flat().reduce((s,x)=>s+price(x.price),0)}
function updateOptionTotal(){$("optTotal").textContent=euro(price(current.price)+optionExtra())}'''
        new_calc = '''/* V0.5.58 ABSOLUTE QUANTITY PRICE */
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
        if old_calc in js:
            js = js.replace(old_calc, new_calc, 1)

        old_add = 'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=exactKey(current);'
        new_add = 'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(optionBasePrice())+optionExtra(),ek=exactKey(current);'
        if old_add in js:
            js = js.replace(old_add, new_add, 1)

    APP_JS.write_text(js, encoding="utf-8")

    # Force le navigateur à reprendre le JS corrigé après déploiement.
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0558', src, count=1)

    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V0.5.58: options centrales + prix total variantes actifs.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.58 bootstrap ignoré:", exc)
