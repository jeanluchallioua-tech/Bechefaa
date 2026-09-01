# BÉCHÉFAA V0.5.43 — sauvegarde fiable des options + import photo sans URL visible
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
INDEX = BASE / "static" / "index.html"


def patch_app_js():
    src = APP_JS.read_text(encoding="utf-8")

    # Le Catalogue central est déjà injecté par sitecustomize.py.
    # On expose simplement une fonction de rechargement immédiat après sauvegarde.
    if "window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogMaster" not in src:
        src = src.replace(
            "setTimeout(loadCentralCatalogMaster,0);",
            "window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogMaster;\nsetTimeout(loadCentralCatalogMaster,0);",
            1,
        )

    # IDs de produits : accepte aussi les IDs texte du catalogue central.
    src = src.replace(
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))',
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(b.dataset.id))',
    )
    src = src.replace(
        'current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);',
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);',
    )

    # L'URL n'est plus présentée à l'utilisateur, mais p.photo est conservé en interne.
    old_photo = '<label>Photo / URL<input id="pfPhoto" value="${p.photo||""}" placeholder="Photo du produit"></label>'
    new_photo = '''<input id="pfPhoto" type="hidden" value="${p.photo||""}">
   <label>Photo du produit<input id="pfPhotoFile" type="file" accept="image/*"></label>
   <div id="pfPhotoPreview" class="catalog-photo-preview">${p.photo?`<img src="${p.photo}" alt="Aperçu">`:`<small>Aucune photo</small>`}</div>'''
    src = src.replace(old_photo, new_photo)

    # Supprime le sens caisse -> catalogue pour éviter d'écraser les options centrales.
    src = src.replace(
        '<button type="button" id="pfAddOptionGroup">+ Groupe</button><button type="button" id="pfReloadOptions">↻ Reprendre caisse</button>',
        '<button type="button" id="pfAddOptionGroup">+ Groupe</button>',
    )
    src = re.sub(
        r'\n\s*\$\("pfReloadOptions"\)\.onclick=\(\)=>\{.*?\n\s*\};',
        '', src, count=1, flags=re.S,
    )

    # Import photo : conserve l'ancienne photo tant qu'une nouvelle n'est pas choisie.
    marker = '   renderPfOptions();\n   $("pfAddOptionGroup").onclick='
    if 'pfPhotoFile' in src and 'compressCatalogPhoto' not in src and marker in src:
        photo_js = r'''   async function compressCatalogPhoto(file){
    return await new Promise((resolve,reject)=>{
     const fr=new FileReader();
     fr.onerror=()=>reject(new Error("Lecture photo impossible"));
     fr.onload=()=>{
      const im=new Image();
      im.onerror=()=>reject(new Error("Image invalide"));
      im.onload=()=>{
       const max=1200,ratio=Math.min(1,max/Math.max(im.width,im.height));
       const c=document.createElement("canvas");
       c.width=Math.max(1,Math.round(im.width*ratio));c.height=Math.max(1,Math.round(im.height*ratio));
       c.getContext("2d").drawImage(im,0,0,c.width,c.height);
       resolve(c.toDataURL("image/jpeg",0.80));
      };
      im.src=fr.result;
     };
     fr.readAsDataURL(file);
    });
   }
   const pfPhotoFile=$("pfPhotoFile"),pfPhotoPreview=$("pfPhotoPreview"),pfPhoto=$("pfPhoto");
   const updatePhotoPreview=()=>{
    if(!pfPhotoPreview)return;
    pfPhotoPreview.innerHTML=pfPhoto?.value?`<img src="${pfPhoto.value}" alt="Aperçu">`:`<small>Aucune photo</small>`;
   };
   pfPhotoFile?.addEventListener("change",async()=>{
    const file=pfPhotoFile.files?.[0];if(!file)return;
    if(!file.type.startsWith("image/"))return alert("Choisissez une image.");
    try{
     pfPhotoFile.disabled=true;
     pfPhoto.value=await compressCatalogPhoto(file);
     updatePhotoPreview();
    }catch(e){alert("Impossible de charger cette photo.")}
    finally{pfPhotoFile.disabled=false;}
   });
   renderPfOptions();
   $("pfAddOptionGroup").onclick='''
        src = src.replace(marker, photo_js, 1)

    # Sauvegarde : on attend réellement la réponse de la base avant de fermer la fiche.
    save_pattern = r'async function save\(\)\{.*?\n \}\n async function loadCentralState\(\)\{'
    save_replacement = r'''async function save(){
   localStorage.setItem(KEY,JSON.stringify(state));
   const st=document.getElementById("catalogSaveStatus");
   try{
     if(st)st.textContent="Enregistrement…";
     const r=await fetch("/api/catalog-admin",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({data:state})});
     if(!r.ok)throw new Error(await r.text());
     if(st)st.textContent="✓ Sauvegardé dans la base centrale";
     await window.BECHEFAA_RELOAD_CATALOG?.();
     return true;
   }catch(e){
     if(st)st.textContent="⚠ Échec de sauvegarde — fiche conservée";
     console.error("Sauvegarde catalogue:",e);
     return false;
   }
 }
 async function loadCentralState(){'''
    src = re.sub(save_pattern, save_replacement, src, count=1, flags=re.S)

    # Enregistrement produit : options capturées, sauvegarde attendue, fermeture seulement si succès.
    pf_pattern = r'\$\("pfSave"\)\.onclick=\(\)=>\{captureOptions\(\);.*?if\(isNew\)state\.products\.push\(p\);save\(\);close\(\);render\(\)\};'
    pf_replacement = r'''$("pfSave").onclick=async()=>{
    captureOptions();
    p.name=$("pfName").value.trim();
    p.category=$("pfCat").value;
    p.price=Number($("pfPrice").value||0);
    p.photo=$("pfPhoto").value;
    p.ingredients=$("pfIngredients").value.trim();
    p.schedule=$("pfSchedule").value;
    p.active=$("pfActive").checked;
    p.channels={caisse:$("chCaisse").checked,site:$("chSite").checked,ubereats:$("chUber").checked,deliveroo:$("chDeliveroo").checked};
    if(!p.name)return alert("Nom obligatoire");
    if(isNew)state.products.push(p);
    const btn=$("pfSave");if(btn){btn.disabled=true;btn.textContent="ENREGISTREMENT…";}
    const ok=await save();
    if(btn){btn.disabled=false;btn.textContent="Enregistrer";}
    if(!ok){if(isNew)state.products=state.products.filter(x=>x!==p);return alert("La sauvegarde n'a pas abouti. La fiche reste ouverte.");}
    close();render();
   };'''
    src = re.sub(pf_pattern, pf_replacement, src, count=1, flags=re.S)

    APP_JS.write_text(src, encoding="utf-8")


def patch_index():
    src = INDEX.read_text(encoding="utf-8")
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0543', src, count=1)
    src = src.replace('<button id="catSyncOptions">⚙ Synchroniser les options</button>\n', '')
    INDEX.write_text(src, encoding="utf-8")


try:
    patch_app_js()
    patch_index()
    print("BÉCHÉFAA V0.5.43: options persistantes + photo importée, URL masquée")
except Exception as exc:
    print("BÉCHÉFAA V0.5.43 patch error:", exc)
