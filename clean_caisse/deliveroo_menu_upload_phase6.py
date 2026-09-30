"""Upload réel du menu BÉCHÉFAA vers Deliveroo Sandbox.

Le menu est construit par deliveroo_menu_builder_phase6. Ce module ne stocke
aucun secret et utilise uniquement les variables d'environnement Deliveroo.
"""
import json
import os
import urllib.parse
import urllib.request
import time
from urllib.error import HTTPError

from flask import jsonify, request, Response

from .deliveroo_menu_builder_phase6 import build_deliveroo_menu_preview


def _oauth_token():
    client_id=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_ID") or "").strip()
    client_secret=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_SECRET") or "").strip()
    auth_url=(os.environ.get("BECHEFAA_DELIVEROO_AUTH_URL") or "https://auth-sandbox.developers.deliveroo.com").rstrip("/")
    if not client_id or not client_secret:
        raise RuntimeError("Identifiants Deliveroo manquants")
    body=urllib.parse.urlencode({
        "client_id":client_id,
        "client_secret":client_secret,
        "grant_type":"client_credentials",
    }).encode("utf-8")
    req=urllib.request.Request(
        auth_url+"/oauth2/token",
        data=body,
        headers={
            "Content-Type":"application/x-www-form-urlencoded; charset=utf-8",
            "Accept":"application/json",
            "User-Agent":"Bechefaa-Deliveroo-Integration/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req,timeout=15) as resp:
        data=json.loads(resp.read().decode("utf-8"))
    token=str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Token Deliveroo absent")
    return token


def _api_json(url, token, method="GET", payload=None):
    raw_body=None
    headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/json",
        "User-Agent":"Bechefaa-Deliveroo-Integration/1.0",
    }
    if payload is not None:
        raw_body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        headers["Content-Type"]="application/json; charset=utf-8"
    req=urllib.request.Request(url,data=raw_body,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=35) as resp:
            raw=resp.read().decode("utf-8","replace")
            try:
                body=json.loads(raw) if raw else {}
            except Exception:
                body={"raw":raw[:1200]}
            return int(resp.status),body
    except HTTPError as exc:
        raw=exc.read().decode("utf-8","replace")
        try:
            body=json.loads(raw) if raw else {}
        except Exception:
            body={"raw":raw[:1200]}
        return int(exc.code),body


def register_deliveroo_menu_upload_phase6(app, db):
    @app.post("/api/deliveroo/menu-upload-phase6")
    def deliveroo_menu_upload_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()

        if not site_id:
            return jsonify({"ok":False,"error":"site_id Sandbox requis"}),400

        try:
            preview=build_deliveroo_menu_preview(db)
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")

            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,
                    "stage":"brand_lookup",
                    "site_id":site_id,
                    "http_status":brand_status,
                    "response":brand_data,
                }),502

            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({
                    "ok":False,
                    "stage":"brand_lookup",
                    "site_id":site_id,
                    "error":"brand_id absent de la réponse Deliveroo",
                    "response":brand_data,
                }),502

            body={
                "menu":preview["payload"]["menu"],
                "site_ids":[site_id],
                "pos_name":"BÉCHÉFAA Caisse",
            }
            url=(
                api_url+"/menu/v1/brands/"
                +urllib.parse.quote(brand_id,safe="")
                +"/menus/"
                +urllib.parse.quote(menu_id,safe="")
            )
            status,response=_api_json(url,token,method="PUT",payload=body)
            ok=200 <= status < 300
            return jsonify({
                "ok":ok,
                "environment":"sandbox" if "sandbox" in api_url else "configured",
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "http_status":status,
                "markup_percentage":preview.get("markup_percentage"),
                "summary":preview.get("summary"),
                "response":response,
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,
                "stage":"upload",
                "error":"Upload Deliveroo impossible",
                "detail":str(exc),
            }),500

    @app.post("/api/deliveroo/scenario8-unavailabilities-phase6")
    def deliveroo_scenario8_unavailabilities_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,"stage":"brand_lookup","http_status":brand_status,
                    "response":brand_data
                }),502
            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            first_payload={"item_unavailabilities":[
                {"item_id":"orange_juice","status":"unavailable"},
                {"item_id":"granola","status":"unavailable"},
            ]}
            first_status,first_response=_api_json(url,token,method="POST",payload=first_payload)
            if not 200 <= first_status < 300:
                return jsonify({
                    "ok":False,"stage":"first_post","brand_id":brand_id,
                    "site_id":site_id,"menu_id":menu_id,"http_status":first_status,
                    "response":first_response
                }),502

            # Deliveroo limite cet endpoint à 1 requête / 100 ms / site.
            time.sleep(0.20)

            second_payload={"item_unavailabilities":[
                {"item_id":"orange_juice","status":"available"},
                {"item_id":"whole_milk","status":"unavailable"},
            ]}
            second_status,second_response=_api_json(url,token,method="POST",payload=second_payload)
            ok=200 <= second_status < 300
            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "first_post":{"http_status":first_status,"response":first_response},
                "second_post":{"http_status":second_status,"response":second_response},
                "expected_final_state":{
                    "orange_juice":"available",
                    "granola":"unavailable",
                    "whole_milk":"unavailable"
                }
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario8","error":"Scenario 8 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario9-replace-unavailabilities-phase6")
    def deliveroo_scenario9_replace_unavailabilities_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,"stage":"brand_lookup","http_status":brand_status,
                    "response":brand_data
                }),502
            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )

            get_status,current=_api_json(url,token,method="GET")
            if not 200 <= get_status < 300:
                return jsonify({
                    "ok":False,"stage":"get_unavailabilities","brand_id":brand_id,
                    "site_id":site_id,"menu_id":menu_id,"http_status":get_status,
                    "response":current
                }),502

            unavailable=list(current.get("unavailable_ids") or []) if isinstance(current,dict) else []
            hidden=list(current.get("hidden_ids") or []) if isinstance(current,dict) else []

            if "whole_milk" not in unavailable:
                unavailable.append("whole_milk")

            put_payload={
                "unavailable_ids":unavailable,
                "hidden_ids":hidden,
            }
            put_status,put_response=_api_json(url,token,method="PUT",payload=put_payload)
            ok=200 <= put_status < 300

            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "get":{"http_status":get_status,"response":current},
                "put":{"http_status":put_status,"payload":put_payload,"response":put_response},
                "expected_final_state":{
                    "orange_juice":"unavailable",
                    "granola":"hidden",
                    "whole_milk":"unavailable"
                }
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario9",
                "error":"Scenario 9 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario10-reset-unavailabilities-phase6")
    def deliveroo_scenario10_reset_unavailabilities_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,"stage":"brand_lookup","http_status":brand_status,
                    "response":brand_data
                }),502
            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            reset_payload={
                "unavailable_ids":[],
                "hidden_ids":[],
            }
            put_status,put_response=_api_json(url,token,method="PUT",payload=reset_payload)
            ok=200 <= put_status < 300
            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "put":{"http_status":put_status,"payload":reset_payload,"response":put_response},
                "expected_final_state":{
                    "orange_juice":"available",
                    "granola":"available",
                    "whole_milk":"available"
                }
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario10",
                "error":"Scenario 10 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario11-morning-reset-phase6")
    def deliveroo_scenario11_morning_reset_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,"stage":"brand_lookup","http_status":brand_status,
                    "response":brand_data
                }),502
            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            post_payload={"item_unavailabilities":[
                {"item_id":"granola","status":"unavailable"},
                {"item_id":"orange_juice","status":"hidden"},
            ]}
            post_status,post_response=_api_json(url,token,method="POST",payload=post_payload)
            ok=200 <= post_status < 300
            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "post":{"http_status":post_status,"payload":post_payload,"response":post_response},
                "initial_state":{
                    "granola":"unavailable",
                    "orange_juice":"hidden",
                    "whole_milk":"available"
                },
                "expected_after_morning_reset":{
                    "granola":"available",
                    "orange_juice":"hidden",
                    "whole_milk":"available"
                }
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario11",
                "error":"Scenario 11 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario12-ignore-morning-reset-phase6")
    def deliveroo_scenario12_ignore_morning_reset_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({
                    "ok":False,"stage":"brand_lookup","http_status":brand_status,
                    "response":brand_data
                }),502
            brand_id=str(
                brand_data.get("brand_id")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            ).strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            post_payload={"item_unavailabilities":[
                {"item_id":"whole_milk","status":"unavailable"},
            ]}
            post_status,post_response=_api_json(url,token,method="POST",payload=post_payload)
            ok=200 <= post_status < 300
            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "post":{"http_status":post_status,"payload":post_payload,"response":post_response},
                "expected_final_state":{
                    "orange_juice":"unavailable",
                    "whole_milk":"unavailable",
                    "granola":"available"
                }
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12",
                "error":"Scenario 12 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.get("/administration/deliveroo-upload")
    def deliveroo_upload_page_phase6():
        return Response("""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Deliveroo Sandbox</title><style>*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#f4f7fb;color:#14213d;margin:0}.w{max-width:760px;margin:32px auto;padding:18px}.b{background:#fff;border:1px solid #e5eaf1;border-radius:18px;padding:24px;box-shadow:0 8px 24px #25466e12}h1{margin-top:0}label{display:block;font-weight:900;margin:16px 0 6px}input,button{width:100%;min-height:48px;border-radius:10px;border:1px solid #ccd5e2;padding:10px;font-size:16px}button{margin-top:20px;background:#111827;color:#fff;font-weight:900;cursor:pointer}.m{color:#667085}.out{white-space:pre-wrap;background:#0b1220;color:#dce6f4;padding:16px;border-radius:12px;margin-top:18px;min-height:90px}</style></head><body><div class="w"><div class="b"><h1>Upload Deliveroo Sandbox</h1><p class="m">Envoie réellement le menu BÉCHÉFAA validé vers le site Sandbox indiqué.</p><label>Site ID Sandbox</label><input id="site" placeholder="Collez le Site ID Deliveroo"><label>Menu ID</label><input id="menu" value="bechefaa-menu-01"><button id="send">ENVOYER LE MENU SANDBOX</button><button id="s8">SCENARIO 8 • ENVOYER LES 2 POST INDISPONIBILITÉS</button><button id="s9">SCENARIO 9 • GET + PUT INDISPONIBILITÉS</button><button id="s10">SCENARIO 10 • RÉINITIALISER LE STOCK</button><button id="s11">SCENARIO 11 • ÉTAT AVANT RESET MATINAL</button><button id="s12">SCENARIO 12 • BLOQUER LE RESET MATINAL</button><div id="out" class="out">Prêt.</div></div></div><script>const out=document.getElementById('out'),btn=document.getElementById('send'),s8=document.getElementById('s8'),s9=document.getElementById('s9'),s10=document.getElementById('s10'),s11=document.getElementById('s11'),s12=document.getElementById('s12');btn.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site){out.textContent='Site ID requis.';return}btn.disabled=true;out.textContent='Upload en cours…';try{const r=await fetch('/api/deliveroo/menu-upload-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{btn.disabled=false}};s8.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s8.disabled=true;out.textContent='Scenario 8 : envoi des 2 POST…';try{const r=await fetch('/api/deliveroo/scenario8-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s8.disabled=false}};s9.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s9.disabled=true;out.textContent='Scenario 9 : GET puis PUT…';try{const r=await fetch('/api/deliveroo/scenario9-replace-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s9.disabled=false}};s10.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s10.disabled=true;out.textContent='Scenario 10 : réinitialisation du stock…';try{const r=await fetch('/api/deliveroo/scenario10-reset-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s10.disabled=false}};s11.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s11.disabled=true;out.textContent='Scenario 11 : état initial avant reset matinal…';try{const r=await fetch('/api/deliveroo/scenario11-morning-reset-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s11.disabled=false}};s12.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12.disabled=true;out.textContent='Scenario 12 : changement après minuit…';try{const r=await fetch('/api/deliveroo/scenario12-ignore-morning-reset-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12.disabled=false}};</script></body></html>""",content_type="text/html; charset=utf-8")
