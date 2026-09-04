# BÉCHÉFAA — commandes/clients : PostgreSQL source unique
# Branche d'audit uniquement. Ce bootstrap nettoie le JS servi avant démarrage.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
CLOUD_JS = BASE / "static" / "cloud.js"
MARKER = "BECHEFAA_ORDERS_CLIENTS_POSTGRES_SOURCE_UNIQUE_20260904"


def patch_app_js():
    src = APP_JS.read_text(encoding="utf-8")
    if MARKER in src:
        return

    # 1) Aucun démarrage depuis une ancienne commande / ancien client navigateur.
    old_init = 'clients=JSON.parse(localStorage.getItem("b_clients043")||"[]"),orders=JSON.parse(localStorage.getItem("b_orders043")||"[]")'
    new_init = 'clients=[],orders=[] /* BECHEFAA_ORDERS_CLIENTS_POSTGRES_SOURCE_UNIQUE_20260904 */'
    if old_init not in src:
        raise RuntimeError("initialisation locale commandes/clients introuvable")
    src = src.replace(old_init, new_init, 1)

    # 2) Les tableaux JS restent un cache d'affichage en mémoire seulement.
    src = src.replace(
        'function saveC(){localStorage.setItem("b_clients043",JSON.stringify(clients))}function saveO(){localStorage.setItem("b_orders043",JSON.stringify(orders))}',
        'function saveC(){/* PostgreSQL source unique : aucune persistance client navigateur */}function saveO(){/* PostgreSQL source unique : aucune persistance commande navigateur */}',
        1,
    )

    # 3) Création commande : serveur d'abord, puis relecture de la vérité serveur.
    create_pattern = re.compile(
        r' let o=\{id:Date\.now\(\),num:1000\+orders\.length\+1,customerId:sel\?\.id\|\|null,customer:sel\?\.name\|\|"Client comptoir",phone:sel\?\.phone\|\|"",email:sel\?\.email\|\|"",address:sel\?\.address\|\|"",postalCode:sel\?\.postalCode\|\|"",city:sel\?\.city\|\|"",source:ch,payment:ch==="WIX"\?"PAYÉ EN LIGNE / STRIPE":ch==="CAISSE"\?"À ENCAISSER":"PAYÉ PLATEFORME",status:"À préparer",items:cart\.map\(x=>\(\{\.\.\.x\}\)\),total\};\n orders\.unshift\(o\);saveO\(\);cart=\[\];sel=null;\$\("selected"\)\.classList\.add\("hidden"\);rCart\(\);boards\(\);alert\("Commande envoyée en cuisine\."\);'
    )
    create_replacement = ''' let o={id:Date.now(),num:1000+orders.length+1,customerId:sel?.id||null,customer:sel?.name||"Client comptoir",phone:sel?.phone||"",email:sel?.email||"",address:sel?.address||"",postalCode:sel?.postalCode||"",city:sel?.city||"",source:ch,payment:ch==="WIX"?"PAYÉ EN LIGNE / STRIPE":ch==="CAISSE"?"À ENCAISSER":"PAYÉ PLATEFORME",status:"À préparer",items:cart.map(x=>({...x})),total};
 try{
   const created=await fetch("/api/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(o)});
   if(!created.ok)throw new Error(await created.text()||("HTTP "+created.status));
   const freshResponse=await fetch("/api/orders?t="+Date.now(),{cache:"no-store"});
   if(!freshResponse.ok)throw new Error(await freshResponse.text()||("HTTP "+freshResponse.status));
   const fresh=await freshResponse.json();
   orders.length=0;(Array.isArray(fresh)?fresh:[]).forEach(x=>orders.push(x));
   cart=[];sel=null;$("selected").classList.add("hidden");rCart();boards();alert("Commande envoyée en cuisine.");
 }catch(e){alert("Commande non enregistrée : "+(e?.message||"erreur serveur"));return;}'''
    src, n_create = create_pattern.subn(create_replacement, src, count=1)
    if n_create != 1:
        raise RuntimeError("bloc création commande introuvable")

    # 4) Création client : serveur d'abord, puis relecture serveur.
    src = src.replace('$("saveClient").onclick=()=>{', '$("saveClient").onclick=async()=>{', 1)
    old_client = ''' clients.unshift(c);saveC();rClients();
 $("clientModal").classList.add("hidden");'''
    new_client = ''' try{
   const created=await fetch("/api/clients",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(c)});
   if(!created.ok)throw new Error(await created.text()||("HTTP "+created.status));
   const freshResponse=await fetch("/api/clients?t="+Date.now(),{cache:"no-store"});
   if(!freshResponse.ok)throw new Error(await freshResponse.text()||("HTTP "+freshResponse.status));
   const fresh=await freshResponse.json();
   clients.length=0;(Array.isArray(fresh)?fresh:[]).forEach(x=>clients.push(x));
   rClients();
 }catch(e){alert("Client non enregistré : "+(e?.message||"erreur serveur"));return;}
 $("clientModal").classList.add("hidden");'''
    if old_client not in src:
        raise RuntimeError("bloc création client introuvable")
    src = src.replace(old_client, new_client, 1)

    # Supprime les anciennes données métier locales si elles existent encore dans ce navigateur.
    purge = '''\nwindow.addEventListener("load",()=>{\n try{["b_orders043","b_clients043","bechefaa_orders"].forEach(k=>localStorage.removeItem(k));}catch(e){}\n});\n'''
    src += purge

    APP_JS.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA ORDERS: PostgreSQL = source unique commandes/clients (app.js).")


def patch_cloud_js():
    src = CLOUD_JS.read_text(encoding="utf-8")
    if MARKER in src:
        return

    # refreshOrders peut mettre à jour le cache mémoire d'affichage, jamais localStorage.
    src = src.replace(
        '        localStorage.setItem("bechefaa_orders",JSON.stringify(local));\n',
        '        /* PostgreSQL source unique : pas de copie persistante des commandes navigateur. */\n',
        1,
    )

    # app.js effectue maintenant le POST création de façon transactionnelle serveur-first.
    validate_pattern = re.compile(
        r'    const validate = \$\("#validate"\);\n    if\(validate\) \{.*?\n    \}\n\n    const saveClient = \$\("#saveClient"\);',
        re.S,
    )
    validate_replacement = '''    /* BECHEFAA_ORDERS_CLIENTS_POSTGRES_SOURCE_UNIQUE_20260904
       Création commande gérée serveur-first par app.js. Aucun second POST cloud. */
    const saveClient = $("#saveClient");'''
    src, n_validate = validate_pattern.subn(validate_replacement, src, count=1)
    if n_validate != 1:
        raise RuntimeError("hook cloud création commande introuvable")

    # Même principe pour les clients : aucun POST différé concurrent.
    client_pattern = re.compile(
        r'    if\(saveClient\) \{\n      saveClient\.addEventListener\("click", \(\) => \{.*?\n      \}\);\n    \}\n\n    document\.addEventListener\("click", async \(e\) => \{',
        re.S,
    )
    client_replacement = '''    /* Client créé serveur-first par app.js : aucun POST cloud concurrent. */

    document.addEventListener("click", async (e) => {'''
    src, n_client = client_pattern.subn(client_replacement, src, count=1)
    if n_client != 1:
        raise RuntimeError("hook cloud création client introuvable")

    CLOUD_JS.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA ORDERS: hooks cloud concurrents supprimés (cloud.js).")


def apply():
    patch_app_js()
    patch_cloud_js()


apply()
