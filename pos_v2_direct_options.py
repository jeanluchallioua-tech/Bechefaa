# BÉCHÉFAA POS V2 — branchement direct des options produit PostgreSQL
# Exécuté après startup_patch et catalog_groups_bootstrap.
# Source d'autorité: p.options chargé depuis catalog_admin_v2.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"

try:
    js = APP_JS.read_text(encoding="utf-8")

    # 1) Le chargeur interne doit conserver les options exactes du produit.
    js = re.sub(
        r'price:(?:Number\(p\.price\|\|0\)|v2Money\(p\.price\)),image:String\(p\.photo\|\|""\),desc:String\(p\.ingredients\|\|p\.description\|\|""\)(?:,options:.*?optionSelections:p\.optionSelections\|\|\{\}[^}]*)?',
        'price:Number(p.price||0),image:String(p.photo||""),desc:String(p.ingredients||p.description||""),options:Array.isArray(p.options)?JSON.parse(JSON.stringify(p.options)):[],optionSelections:p.optionSelections||{}',
        js,
        count=1,
        flags=re.S,
    )

    # 2) profile() ne dépend plus d'une table de profils intermédiaire.
    # Il fabrique les GROUPS directement depuis p.options, dans l'ordre enregistré.
    profile_pattern = r'function profile\(p\)\{.*?\n\}\nfunction rc\(\)\{'
    profile_replacement = r'''function profile(p){ /* BECHEFAA_V2_DIRECT_PROFILE_0612 */
 if(!p)return [];
 const direct=Array.isArray(p.options)?p.options:[];
 const keys=[];
 direct.forEach((g,gi)=>{
  const safeId=String(p.id??p.name??"product").replace(/[^a-zA-Z0-9_-]/g,"_");
  const key=`direct_${safeId}_${gi}`;
  const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)
    ?[String(c[0]??"Option"),Number(c[1]||0)]
    :[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)]);
  GROUPS[key]={
   title:String(g?.title||g?.name||g?.key||"Options"),
   required:!!g?.required,
   max:Math.max(0,Number(g?.max??1)),
   choices
  };
  if(choices.length)keys.push(key);
 });
 return keys;
}
function rc(){'''
    js, profile_count = re.subn(profile_pattern, profile_replacement, js, count=1, flags=re.S)

    # 3) IDs et prix robustes dans le chemin produit -> panier.
    js = js.replace(
        'current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);',
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);'
    )
    js = js.replace(
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=current?profile(current):[];',
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);'
    )
    js = js.replace(
        'let u=price(current.price),x=cart.find(i=>i.id===current.id&&!i.optionsText&&i.unit===u);',
        'let u=Number(price(current.price))||0,x=cart.find(i=>String(i.id)===String(current.id)&&!i.optionsText&&Number(i.unit)===u);'
    )

    APP_JS.write_text(js, encoding="utf-8")
    print(f"BÉCHÉFAA V2 direct options: profile remplacé={profile_count}.")
except Exception as exc:
    print("BÉCHÉFAA V2 direct options ignoré:", exc)
