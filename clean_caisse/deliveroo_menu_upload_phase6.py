"""Upload réel du menu BÉCHÉFAA vers Deliveroo Sandbox.

Le menu est construit par deliveroo_menu_builder_phase6. Ce module ne stocke
aucun secret et utilise uniquement les variables d'environnement Deliveroo.
"""
import json
import os
import urllib.parse
import urllib.request
import time
from datetime import datetime, timezone, timedelta
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


def _deliveroo_normalize_for_compare(value):
    """Normalise les différences de représentation non sémantiques du GET Deliveroo."""
    if isinstance(value, dict):
        out={}
        for key,val in value.items():
            if key=="drn_id" and (val=="" or val is None):
                continue
            out[key]=_deliveroo_normalize_for_compare(val)
        return out
    if isinstance(value, list):
        return [_deliveroo_normalize_for_compare(x) for x in value]
    return value


def _deliveroo_deep_diff(expected, actual, path="$", limit=200):
    diffs=[]
    def walk(a,b,p):
        if len(diffs) >= limit:
            return
        if isinstance(a,dict) and isinstance(b,dict):
            for key in sorted(set(a.keys()) | set(b.keys())):
                np=p+"."+str(key)
                if key not in a:
                    diffs.append({"path":np,"type":"only_deliveroo","deliveroo":b.get(key)})
                elif key not in b:
                    diffs.append({"path":np,"type":"only_bechefaa","bechefaa":a.get(key)})
                else:
                    walk(a[key],b[key],np)
            return
        if isinstance(a,list) and isinstance(b,list):
            if len(a) != len(b):
                diffs.append({"path":p,"type":"length","bechefaa_length":len(a),"deliveroo_length":len(b)})
            for i in range(min(len(a),len(b))):
                walk(a[i],b[i],p+"["+str(i)+"]")
            return
        if a != b:
            diffs.append({"path":p,"type":"value","bechefaa":a,"deliveroo":b})
    walk(expected,actual,path)
    return diffs


def _deliveroo_compare_by_id(local_menu, remote_menu, limit=300):
    """Compare les collections Deliveroo par id au lieu de leur position."""
    result={
        "items":{"only_bechefaa":[],"only_deliveroo":[],"changed":[]},
        "modifiers":{"only_bechefaa":[],"only_deliveroo":[],"changed":[]},
        "categories":{"only_bechefaa":[],"only_deliveroo":[],"changed":[]},
        "mealtimes":{"only_bechefaa":[],"only_deliveroo":[],"changed":[]},
        "menu_level":[],
    }

    def scalar_norm(path, value):
        if path.endswith(".tax_rate"):
            try:
                return str(float(str(value))).rstrip("0").rstrip(".")
            except Exception:
                return value
        return value

    remote_defaults={
        "highlights","ian","is_eligible_as_replacement",
        "is_eligible_for_substitution","is_meal_card_not_eligible",
        "max_quantity","nutritional_info","barcodes","drn_id",
    }

    def project_remote_to_local(local, remote, path):
        if isinstance(local,dict) and isinstance(remote,dict):
            out={}
            for k,v in local.items():
                if k in remote:
                    out[k]=project_remote_to_local(v,remote[k],path+"."+k)
                else:
                    out[k]=None
            return out
        if isinstance(local,list) and isinstance(remote,list):
            # Sous-listes d'objets identifiables: comparer par id.
            dict_local=[x for x in local if isinstance(x,dict) and x.get("id") is not None]
            dict_remote=[x for x in remote if isinstance(x,dict) and x.get("id") is not None]
            if dict_local and len(dict_local)==len(local) and len(dict_remote)==len(remote):
                rmap={str(x.get("id")):x for x in dict_remote}
                return [
                    project_remote_to_local(x,rmap.get(str(x.get("id")),{}),path+"["+str(x.get("id"))+"]")
                    for x in dict_local
                ]
            return [project_remote_to_local(a,b,path+"[]") for a,b in zip(local,remote)]
        return scalar_norm(path,remote)

    def clean_local(value,path):
        if isinstance(value,dict):
            return {k:clean_local(v,path+"."+k) for k,v in value.items()}
        if isinstance(value,list):
            return [clean_local(v,path+"[]") for v in value]
        return scalar_norm(path,value)

    for coll in ("items","modifiers","categories","mealtimes"):
        llist=local_menu.get(coll) or []
        rlist=remote_menu.get(coll) or []
        lmap={str(x.get("id")):x for x in llist if isinstance(x,dict) and x.get("id") is not None}
        rmap={str(x.get("id")):x for x in rlist if isinstance(x,dict) and x.get("id") is not None}
        result[coll]["only_bechefaa"]=sorted(set(lmap)-set(rmap))
        result[coll]["only_deliveroo"]=sorted(set(rmap)-set(lmap))
        for ident in sorted(set(lmap)&set(rmap)):
            local_obj=clean_local(lmap[ident],"$."+coll+"."+ident)
            remote_obj=project_remote_to_local(lmap[ident],rmap[ident],"$."+coll+"."+ident)
            if local_obj != remote_obj:
                diffs=_deliveroo_deep_diff(local_obj,remote_obj,"$."+coll+"."+ident,limit=40)
                result[coll]["changed"].append({"id":ident,"differences":diffs})
                if sum(len(result[c]["changed"]) for c in ("items","modifiers","categories","mealtimes")) >= limit:
                    break

    for key in ("currency_code","is_pos_integrated"):
        lv=clean_local(local_menu.get(key),"$.menu."+key)
        rv=scalar_norm("$.menu."+key,remote_menu.get(key))
        if lv != rv:
            result["menu_level"].append({"path":"$.menu."+key,"bechefaa":lv,"deliveroo":rv})

    result["summary"]={
        coll:{
            "bechefaa_count":len(local_menu.get(coll) or []),
            "deliveroo_count":len(remote_menu.get(coll) or []),
            "only_bechefaa_count":len(result[coll]["only_bechefaa"]),
            "only_deliveroo_count":len(result[coll]["only_deliveroo"]),
            "changed_same_id_count":len(result[coll]["changed"]),
        } for coll in ("items","modifiers","categories","mealtimes")
    }
    return result


def register_deliveroo_menu_upload_phase6(app, db):
    @app.post("/api/deliveroo/scenario1-fetch-brand-phase6")
    def deliveroo_scenario1_fetch_brand_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        if not site_id:
            return jsonify({"ok":False,"error":"site_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            url=api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe="")
            status,response=_api_json(url,token,method="GET")
            raw_brand_id=(
                response.get("brand_id")
                or response.get("brand_ids")
                or ((response.get("brand") or {}).get("id") if isinstance(response.get("brand"),dict) else "")
                or ""
            ) if isinstance(response,dict) else ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            ok=200 <= status < 300 and bool(brand_id)
            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "http_status":status,
                "brand_id":brand_id,
                "response":response,
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,
                "stage":"scenario1",
                "error":"Scenario 1 Deliveroo impossible",
                "detail":str(exc),
            }),500

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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
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

    @app.post("/api/deliveroo/scenario5-identical-menu-phase6")
    def deliveroo_scenario5_identical_menu_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")

            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            # Le schéma PUT v1 officiel contient menu + site_ids (+ pos_name optionnel).
            # Ne pas ajouter de champ top-level "name".
            body={
                "menu":preview["payload"]["menu"],
                "site_ids":[site_id],
            }

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )

            # Un seul PUT pendant la fenêtre du scénario 5. Le menu doit avoir été
            # préchargé et entièrement traité avant de cliquer Start côté Deliveroo.
            status,response=_api_json(url,token,method="PUT",payload=body)
            ok=200 <= status < 300
            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "http_status":status,
                "response":response,
                "match_existing_menu":(
                    isinstance(response,dict)
                    and str(response.get("result") or "")=="MATCH_EXISTING_MENU"
                ),
                "mode":"single_put_against_existing_menu",
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario5",
                "error":"Scenario 5 Deliveroo impossible","detail":str(exc)
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
            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
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

            # Deliveroo limite cet endpoint à 1 appel toutes les 833 ms / site.
            # On garde une marge pour éviter le 429 Too Many Requests.
            time.sleep(1.10)

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
            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
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

            # Scenario 9 : remplacement complet attendu par le test.
            # orange_juice et whole_milk sont indisponibles ; granola est masqué.
            put_payload={
                "unavailable_ids":["orange_juice","whole_milk"],
                "hidden_ids":["granola"],
            }
            # Même ressource GET/PUT : respecter une marge au-dessus du plafond
            # de 1 appel toutes les 833 ms pour que les 2 appels soient bien observables.
            time.sleep(1.10)
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
            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
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
            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
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
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            menu_url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            stock_url=(
                menu_url+"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )

            # Le runner du Scenario 12 injecte un menu synthétique. Attendre
            # uniquement qu'il soit visible, puis envoyer immédiatement le POST
            # attendu. Ne pas attendre de webhook : notre POS n'a pas uploadé ce menu.
            expected_ids={"orange_juice","granola","whole_milk"}
            observed_item_ids=[]
            menu_ready=False
            for _ in range(40):
                menu_status,menu_response=_api_json(menu_url,token,method="GET")
                items=((menu_response.get("menu") or {}).get("items") or []) if isinstance(menu_response,dict) else []
                observed_item_ids=[
                    str(x.get("id")) for x in items
                    if isinstance(x,dict) and x.get("id") is not None
                ]
                if 200 <= menu_status < 300 and set(observed_item_ids)==expected_ids:
                    menu_ready=True
                    break
                time.sleep(0.25)

            if not menu_ready:
                return jsonify({
                    "ok":False,
                    "stage":"waiting_test_menu",
                    "waiting":True,
                    "observed_item_ids":observed_item_ids,
                    "message":"Menu test exact du Scenario 12 non détecté"
                }),409

            post_payload={"item_unavailabilities":[
                {"item_id":"whole_milk","status":"unavailable"},
            ]}
            post_started_at=datetime.now(timezone.utc)
            post_status,post_response=_api_json(
                stock_url,token,method="POST",payload=post_payload
            )
            ok=200 <= post_status < 300

            return jsonify({
                "ok":ok,
                "brand_id":brand_id,
                "site_id":site_id,
                "menu_id":menu_id,
                "test_menu_ready":True,
                "observed_item_ids":observed_item_ids,
                "post_started_at":post_started_at.isoformat(),
                "post":{
                    "http_status":post_status,
                    "payload":post_payload,
                    "response":post_response
                },
                "mode":"wait_exact_test_menu_then_immediate_single_post"
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12",
                "error":"Scenario 12 Deliveroo impossible","detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario12-state-phase6")
    def deliveroo_scenario12_state_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),token)
            if not 200 <= brand_status < 300:
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status}),502
            raw_brand_id=brand_data.get("brand_id") or brand_data.get("brand_ids") or ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            url=api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")+"/menus/"+urllib.parse.quote(menu_id,safe="")+"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            status,response=_api_json(url,token,method="GET")

            menu_url=api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")+"/menus/"+urllib.parse.quote(menu_id,safe="")
            menu_status,menu_response=_api_json(menu_url,token,method="GET")
            items=[]
            if isinstance(menu_response,dict):
                items=((menu_response.get("menu") or {}).get("items") or [])
            item_ids={
                str(x.get("id")) for x in items
                if isinstance(x,dict) and x.get("id") is not None
            }
            test_ids=["orange_juice","granola","whole_milk"]
            return jsonify({
                "ok":200 <= status < 300 and 200 <= menu_status < 300,
                "read_only":True,
                "http_status":status,
                "state":response,
                "menu_http_status":menu_status,
                "menu_item_count":len(items),
                "test_menu_presence":{item_id:(item_id in item_ids) for item_id in test_ids},
                "test_menu_ready":all(item_id in item_ids for item_id in test_ids)
            }),200 if (200 <= status < 300 and 200 <= menu_status < 300) else 502
        except Exception as exc:
            return jsonify({"ok":False,"stage":"scenario12_state","detail":str(exc)}),500


    @app.post("/api/deliveroo/scenario12-statuses-diagnostic-phase6")
    def deliveroo_scenario12_statuses_diagnostic_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            real_items=[
                x for x in (preview.get("payload",{}).get("menu",{}).get("items") or [])
                if isinstance(x,dict) and x.get("id") and x.get("type") in ("ITEM","BUNDLE")
            ]
            if not real_items:
                return jsonify({"ok":False,"stage":"scenario12_statuses","error":"Aucun item réel disponible"}),500

            target=real_items[0]
            target_item_id=str(target.get("id"))
            target_item_name=str(((target.get("name") or {}).get("fr")) or target_item_id)

            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502

            raw_brand_id=brand_data.get("brand_id") or brand_data.get("brand_ids") or ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )

            steps=[]
            for status_value in ("unavailable","hidden","available"):
                post_payload={"item_unavailabilities":[
                    {"item_id":target_item_id,"status":status_value}
                ]}
                post_status,post_response=_api_json(url,token,method="POST",payload=post_payload)
                time.sleep(1.10)
                get_status,get_response=_api_json(url,token,method="GET")
                steps.append({
                    "status_sent":status_value,
                    "post_http_status":post_status,
                    "post_response":post_response,
                    "get_http_status":get_status,
                    "state_after":get_response,
                })
                time.sleep(1.10)

            return jsonify({
                "ok":all(200 <= step["post_http_status"] < 300 for step in steps),
                "diagnostic":"scenario12_three_statuses",
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "target_item":{"id":target_item_id,"name":target_item_name},
                "steps":steps,
                "note":"Teste unavailable, hidden puis available sur un vrai item, avec GET après chaque POST."
            }),200
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12_statuses",
                "error":"Diagnostic 3 statuts Scenario 12 impossible","detail":str(exc)
            }),500


    @app.post("/api/deliveroo/scenario12-official-body-phase6")
    def deliveroo_scenario12_official_body_phase6():
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
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502
            raw_brand_id=brand_data.get("brand_id") or brand_data.get("brand_ids") or ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            official_payload={"item_unavailabilities":[
                {"item_id":"orange_juice","status":"unavailable"},
                {"item_id":"granola","status":"available"},
                {"item_id":"whole_milk","status":"hidden"},
            ]}
            post_status,post_response=_api_json(url,token,method="POST",payload=official_payload)
            return jsonify({
                "ok":200 <= post_status < 300,
                "diagnostic":"scenario12_official_body",
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "payload_sent":official_payload,
                "post":{"http_status":post_status,"response":post_response},
                "note":"Body identique à l'exemple officiel Deliveroo Update individual unavailabilities."
            }),200
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12_official_body",
                "error":"Diagnostic body officiel Scenario 12 impossible","detail":str(exc)
            }),500


    @app.post("/api/deliveroo/scenario12-v2-diagnostic-phase6")
    def deliveroo_scenario12_v2_diagnostic_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        if not site_id:
            return jsonify({"ok":False,"error":"site_id requis"}),400
        try:
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502
            raw_brand_id=brand_data.get("brand_id") or brand_data.get("brand_ids") or ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v2/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/sites/"+urllib.parse.quote(site_id,safe="")
                +"/menu/item_unavailabilities"
            )
            official_payload={"item_unavailabilities":[
                {"item_id":"orange_juice","status":"unavailable"},
                {"item_id":"granola","status":"available"},
                {"item_id":"whole_milk","status":"hidden"},
            ]}
            post_status,post_response=_api_json(url,token,method="POST",payload=official_payload)
            return jsonify({
                "ok":200 <= post_status < 300,
                "diagnostic":"scenario12_v2_official_body",
                "site_id":site_id,
                "brand_id":brand_id,
                "payload_sent":official_payload,
                "post":{"http_status":post_status,"response":post_response},
                "endpoint_version":"v2"
            }),200
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12_v2",
                "error":"Diagnostic Scenario 12 v2 impossible","detail":str(exc)
            }),500


    @app.post("/api/deliveroo/scenario12-expected-body-phase6")
    def deliveroo_scenario12_expected_body_phase6():
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
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502

            raw_brand_id=brand_data.get("brand_id") or brand_data.get("brand_ids") or ""
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )

            expected_payload={"item_unavailabilities":[
                {"item_id":"orange_juice","status":"unavailable"},
                {"item_id":"whole_milk","status":"unavailable"},
                {"item_id":"granola","status":"available"},
            ]}
            post_status,post_response=_api_json(url,token,method="POST",payload=expected_payload)

            return jsonify({
                "ok":200 <= post_status < 300,
                "diagnostic":"scenario12_expected_body",
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "payload_sent":expected_payload,
                "post":{"http_status":post_status,"response":post_response},
                "reason":"Body aligné sur l'expected_final_state historique du scénario 12."
            }),200
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12_expected_body",
                "error":"Diagnostic body attendu Scenario 12 impossible","detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario12-diagnostic-phase6")
    def deliveroo_scenario12_diagnostic_phase6():
        """Diagnostic actif S12: trace l'appel POST exact et vérifie l'état avant/après."""
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            real_items=[
                x for x in (preview.get("payload",{}).get("menu",{}).get("items") or [])
                if isinstance(x,dict) and x.get("id") and x.get("type") in ("ITEM","BUNDLE")
            ]
            if not real_items:
                return jsonify({"ok":False,"stage":"scenario12_diag","error":"Aucun item réel disponible"}),500

            target=real_items[0]
            target_item_id=str(target.get("id"))
            target_item_name=str(((target.get("name") or {}).get("fr")) or target_item_id)

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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )

            before_status,before_response=_api_json(url,token,method="GET")
            post_payload={"item_unavailabilities":[
                {"item_id":target_item_id,"status":"unavailable"},
            ]}
            started_at=datetime.now(timezone.utc).isoformat()
            post_status,post_response=_api_json(url,token,method="POST",payload=post_payload)
            finished_at=datetime.now(timezone.utc).isoformat()

            time.sleep(1.10)
            after_status,after_response=_api_json(url,token,method="GET")

            return jsonify({
                "ok":200 <= post_status < 300,
                "diagnostic":"scenario12_post_trace",
                "method":"POST",
                "url":url,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "target_item":{"id":target_item_id,"name":target_item_name},
                "payload_sent":post_payload,
                "started_at_utc":started_at,
                "finished_at_utc":finished_at,
                "before":{"http_status":before_status,"response":before_response},
                "post":{"http_status":post_status,"response":post_response},
                "after":{"http_status":after_status,"response":after_response},
                "note":"Ce diagnostic effectue réellement le POST d'indisponibilité attendu par le scénario 12."
            }),200 if 200 <= post_status < 300 else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario12_diag",
                "error":"Diagnostic Scenario 12 impossible","detail":str(exc)
            }),500

    def _scenario13_state_table():
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS deliveroo_scenario13_state (
                        site_id TEXT NOT NULL,
                        menu_id TEXT NOT NULL,
                        brand_id TEXT,
                        upload_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        upload_http_status INTEGER,
                        upload_response JSONB,
                        PRIMARY KEY(site_id, menu_id)
                    )
                """)
            conn.commit()

    @app.post("/api/deliveroo/scenario13-upload-phase6")
    def deliveroo_scenario13_upload_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            menu=json.loads(json.dumps(preview["payload"]["menu"],ensure_ascii=False))
            # Le scénario 13 exige au moins 100 entrées de type ITEM
            # (les CHOICE et BUNDLE ne comptent pas).
            items=menu.get("items") or []
            item_count=sum(1 for x in items if isinstance(x,dict) and x.get("type")=="ITEM")

            if item_count < 100:
                source_items=[
                    x for x in items
                    if isinstance(x,dict) and x.get("type")=="ITEM"
                ]
                if not source_items:
                    return jsonify({
                        "ok":False,
                        "stage":"menu_validation",
                        "error":"Aucun ITEM disponible pour compléter le scénario 13",
                    }),400

                needed=100-item_count
                scenario_ids=[]
                for n in range(needed):
                    src=source_items[n % len(source_items)]
                    clone=json.loads(json.dumps(src,ensure_ascii=False))
                    clone_id="scenario13_item_"+str(n+1)
                    clone["id"]=clone_id
                    clone["plu"]="s13:"+str(n+1)
                    clone["name"]={"fr":"Test Scenario 13 "+str(n+1)}
                    clone["operational_name"]="Test Scenario 13 "+str(n+1)
                    clone["modifier_ids"]=[]
                    clone["external_data"]=json.dumps({
                        "scenario":"13",
                        "source_item_id":src.get("id"),
                    },ensure_ascii=False)
                    clone.setdefault("price_info",{})["overrides"]=[]
                    items.append(clone)
                    scenario_ids.append(clone_id)

                # Les ITEMs de test sont ajoutés à une catégorie existante afin
                # qu'ils fassent partie du menu soumis au validateur Sandbox.
                categories=menu.get("categories") or []
                if categories:
                    categories[0].setdefault("item_ids",[]).extend(scenario_ids)

                item_count=sum(1 for x in items if isinstance(x,dict) and x.get("type")=="ITEM")

            # Force un vrai changement Sandbox afin d'éviter MATCH_EXISTING_MENU.
            marker=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
            target=None
            for item in menu.get("items") or []:
                if isinstance(item,dict) and item.get("type") in {"ITEM","BUNDLE"}:
                    target=item
                    break
            if target is None:
                return jsonify({"ok":False,"stage":"menu_validation","error":"Aucun item principal trouvé"}),400
            desc=target.get("description") if isinstance(target.get("description"),dict) else {}
            base=str(desc.get("fr") or "").strip()
            desc["fr"]=(base+" · Scenario 13 "+marker).strip(" ·")
            target["description"]=desc

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
            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            started_at=datetime.now(timezone.utc)
            body={"menu":menu,"site_ids":[site_id],"pos_name":"BÉCHÉFAA Caisse"}
            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            upload_status,upload_response=_api_json(url,token,method="PUT",payload=body)
            ok=200 <= upload_status < 300

            _scenario13_state_table()
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO deliveroo_scenario13_state
                            (site_id,menu_id,brand_id,upload_started_at,upload_http_status,upload_response)
                        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                        ON CONFLICT(site_id,menu_id) DO UPDATE SET
                            brand_id=EXCLUDED.brand_id,
                            upload_started_at=EXCLUDED.upload_started_at,
                            upload_http_status=EXCLUDED.upload_http_status,
                            upload_response=EXCLUDED.upload_response
                    """,(site_id,menu_id,brand_id,started_at,upload_status,json.dumps(upload_response,ensure_ascii=False)))
                conn.commit()

            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "menu_id":menu_id,
                "brand_id":brand_id,
                "item_count":item_count,
                "upload_started_at":started_at.isoformat(),
                "http_status":upload_status,
                "response":upload_response,
                "next":"Attendre menu.upload_result avant de modifier le stock"
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario13_upload",
                "error":"Upload Scenario 13 impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario13-stock-after-webhook-phase6")
    def deliveroo_scenario13_stock_after_webhook_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            _scenario13_state_table()
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT brand_id, upload_started_at, upload_http_status, upload_response
                        FROM deliveroo_scenario13_state
                        WHERE site_id=%s AND menu_id=%s
                    """,(site_id,menu_id))
                    state=cur.fetchone()
                    if not state:
                        return jsonify({
                            "ok":False,
                            "stage":"waiting_webhook",
                            "error":"Aucun upload Scenario 13 enregistré"
                        }),409
                    cur.execute("""
                        SELECT received_at, accepted, event, error
                        FROM deliveroo_webhook_diag
                        WHERE kind='menu'
                    """)
                    diag=cur.fetchone()

            upload_response=state.get("upload_response") or {}
            if isinstance(upload_response,str):
                try:
                    upload_response=json.loads(upload_response)
                except Exception:
                    upload_response={}

            matched=str(upload_response.get("result") or "").strip()=="MATCH_EXISTING_MENU"
            webhook_ok=bool(
                diag
                and diag.get("accepted") is True
                and str(diag.get("event") or "")=="menu.upload_result"
                and diag.get("received_at")
                and diag.get("received_at") >= state.get("upload_started_at")
            )

            if not matched and not webhook_ok:
                return jsonify({
                    "ok":False,
                    "stage":"waiting_webhook",
                    "waiting":True,
                    "upload_started_at":state.get("upload_started_at").isoformat() if state.get("upload_started_at") else None,
                    "last_menu_webhook_at":diag.get("received_at").isoformat() if diag and diag.get("received_at") else None,
                    "last_menu_event":diag.get("event") if diag else None,
                    "message":"Webhook menu.upload_result pas encore reçu pour cet upload"
                }),409

            brand_id=str(state.get("brand_id") or "").strip()
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
            url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
                +"/item_unavailabilities/"+urllib.parse.quote(site_id,safe="")
            )
            stock_payload={"item_unavailabilities":[
                {"item_id":"item_24","status":"unavailable"},
            ]}
            stock_status,stock_response=_api_json(url,token,method="POST",payload=stock_payload)
            ok=200 <= stock_status < 300
            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "menu_id":menu_id,
                "brand_id":brand_id,
                "webhook_received":webhook_ok,
                "match_existing_menu":matched,
                "stock":{"http_status":stock_status,"payload":stock_payload,"response":stock_response},
                "changed_item":"item_24"
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario13_stock",
                "error":"Mise à jour stock Scenario 13 impossible",
                "detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario14-generate-s3-phase6")
    def deliveroo_scenario14_generate_s3_phase6():
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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v3/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            status,response=_api_json(url,token,method="PUT",payload=None)
            ok=200 <= status < 300

            s3_url=None
            if isinstance(response,dict):
                s3_url=(
                    response.get("url")
                    or response.get("s3_url")
                    or response.get("upload_url")
                    or response.get("presigned_url")
                )

            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "http_status":status,
                "s3_url_received":bool(s3_url),
                "response":response,
                "next":"Réutiliser ce même menu_id pour les scénarios Menu V3 suivants"
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario14",
                "error":"Scenario 14 Deliveroo impossible",
                "detail":str(exc)
            }),500

    def _find_presigned_url(value):
        if isinstance(value,str):
            text=value.strip()
            if text.startswith("http://") or text.startswith("https://"):
                if "amazonaws.com" in text or "X-Amz-" in text or "s3" in text.lower():
                    return text
            return None
        if isinstance(value,dict):
            for key in ("upload_url","presigned_url","s3_url","url"):
                found=_find_presigned_url(value.get(key))
                if found:
                    return found
            for child in value.values():
                found=_find_presigned_url(child)
                if found:
                    return found
        if isinstance(value,list):
            for child in value:
                found=_find_presigned_url(child)
                if found:
                    return found
        return None

    def _put_json_to_presigned_url(url, payload):
        raw=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        req=urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type":"application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req,timeout=35) as resp:
                body=resp.read().decode("utf-8","replace")
                return int(resp.status),body[:1000]
        except HTTPError as exc:
            body=exc.read().decode("utf-8","replace")
            return int(exc.code),body[:1000]

    def _scenario15_state_table():
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS deliveroo_scenario15_state (
                        site_id TEXT NOT NULL,
                        menu_id TEXT NOT NULL,
                        brand_id TEXT NOT NULL,
                        job_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY(site_id, menu_id)
                    )
                """)
            conn.commit()

    @app.post("/api/deliveroo/scenario15-v3-async-upload-phase6")
    def deliveroo_scenario15_v3_async_upload_phase6():
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            menu=preview["payload"]["menu"]

            # Prévalidation minimale exigée par le Scenario 15.
            mealtimes=menu.get("mealtimes") or []
            categories=menu.get("categories") or []
            items=menu.get("items") or []
            valid_mealtime=any(
                isinstance(x,dict)
                and isinstance(x.get("name"),dict) and bool(x.get("name"))
                and isinstance(x.get("description"),dict) and bool(x.get("description"))
                and isinstance(x.get("image"),dict) and bool(x.get("image",{}).get("url"))
                for x in mealtimes
            )
            valid_category=any(
                isinstance(x,dict) and isinstance(x.get("name"),dict) and bool(x.get("name"))
                for x in categories
            )
            categorized_ids=set()
            for cat in categories:
                if isinstance(cat,dict):
                    categorized_ids.update(str(x) for x in (cat.get("item_ids") or []))
            valid_item=any(
                isinstance(x,dict)
                and x.get("id") in categorized_ids
                and isinstance(x.get("name"),dict) and bool(x.get("name"))
                and bool(str(x.get("operational_name") or "").strip())
                and bool(str(x.get("plu") or "").strip())
                and isinstance(x.get("description"),dict) and bool(x.get("description"))
                for x in items
            )
            if not (valid_mealtime and valid_category and valid_item):
                return jsonify({
                    "ok":False,
                    "stage":"prevalidation",
                    "valid_mealtime":valid_mealtime,
                    "valid_category":valid_category,
                    "valid_item":valid_item,
                }),400

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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            # 1) Générer une URL S3 fraîche (expiration ~5 secondes dans le scénario).
            create_url=(
                api_url+"/menu/v3/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            s3_status,s3_response=_api_json(create_url,token,method="PUT",payload=None)
            if not 200 <= s3_status < 300:
                return jsonify({
                    "ok":False,"stage":"generate_s3","http_status":s3_status,
                    "response":s3_response
                }),502

            presigned_url=_find_presigned_url(s3_response)
            if not presigned_url:
                return jsonify({
                    "ok":False,"stage":"generate_s3",
                    "error":"URL S3 introuvable dans la réponse Deliveroo",
                    "response":s3_response
                }),502

            # 2) Upload immédiat du document JSON vers S3.
            document={
                "site_ids":[site_id],
                "menu":menu,
                "pos_name":"BÉCHÉFAA Caisse",
            }
            upload_status,upload_body=_put_json_to_presigned_url(presigned_url,document)
            if not 200 <= upload_status < 300:
                return jsonify({
                    "ok":False,"stage":"s3_upload","http_status":upload_status,
                    "response":upload_body
                }),502

            # 3) Déclencher le traitement asynchrone.
            jobs_url=(
                api_url+"/menu/v3/brands/"+urllib.parse.quote(brand_id,safe="")+"/jobs"
            )
            job_payload={
                "action":"publish_menu_to_live",
                "params":{"menu_id":menu_id},
            }
            job_status,job_response=_api_json(jobs_url,token,method="POST",payload=job_payload)

            # Certaines versions Sandbox infèrent le menu depuis le dernier upload S3
            # et n'acceptent pas params.menu_id : retenter uniquement si le premier appel
            # a été rejeté avant création du job.
            fallback_used=False
            if job_status==400:
                fallback_used=True
                job_payload={"action":"publish_menu_to_live"}
                job_status,job_response=_api_json(jobs_url,token,method="POST",payload=job_payload)

            ok=200 <= job_status < 300
            job_id=None
            if isinstance(job_response,dict):
                job_id=job_response.get("job_id") or job_response.get("id")

            if 200 <= job_status < 300 and job_id:
                _scenario15_state_table()
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO deliveroo_scenario15_state(site_id,menu_id,brand_id,job_id)
                            VALUES (%s,%s,%s,%s)
                            ON CONFLICT(site_id,menu_id) DO UPDATE SET
                                brand_id=EXCLUDED.brand_id,
                                job_id=EXCLUDED.job_id,
                                created_at=NOW()
                        """,(site_id,menu_id,brand_id,str(job_id)))
                    conn.commit()

            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "s3_url_generated":True,
                "s3_http_status":upload_status,
                "job_http_status":job_status,
                "job_id":job_id,
                "job_payload":job_payload,
                "job_response":job_response,
                "webhook_expected":"menu.upload_result",
                "next":"Attendre le webhook de résultat Deliveroo"
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario15",
                "error":"Scenario 15 Deliveroo impossible",
                "detail":str(exc)
            }),500

    def _find_job_id(value):
        if isinstance(value,dict):
            for key in ("job_id","jobId","id"):
                raw=value.get(key)
                if isinstance(raw,str) and raw.strip():
                    # Évite de confondre l'ID du menu avec un job : priorité aux
                    # structures qui contiennent explicitement un contexte de job.
                    if key!="id" or any(k in value for k in ("status","action","job_type","created_at","updated_at")):
                        return raw.strip()
            for key in ("pending_jobs","jobs","job","latest_job"):
                found=_find_job_id(value.get(key))
                if found:
                    return found
            for child in value.values():
                found=_find_job_id(child)
                if found:
                    return found
        elif isinstance(value,list):
            for child in value:
                found=_find_job_id(child)
                if found:
                    return found
        return None

    @app.post("/api/deliveroo/scenario16-job-status-phase6")
    def deliveroo_scenario16_job_status_phase6():
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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            # Scenario 16 doit interroger le job réellement créé au scénario 15.
            # Ne pas créer un nouveau job ici, sinon le validateur du portail voit
            # une séquence différente de celle qu'il attend.
            _scenario15_state_table()
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT brand_id, job_id, created_at
                        FROM deliveroo_scenario15_state
                        WHERE site_id=%s AND menu_id=%s
                    """,(site_id,menu_id))
                    state=cur.fetchone()

            if not state:
                return jsonify({
                    "ok":False,
                    "stage":"job_id",
                    "error":"Aucun job Scenario 15 enregistré pour ce site/menu"
                }),409

            stored_brand_id=str(state.get("brand_id") or "").strip()
            job_id=str(state.get("job_id") or "").strip()
            if not job_id:
                return jsonify({
                    "ok":False,
                    "stage":"job_id",
                    "error":"job_id Scenario 15 absent"
                }),409

            # Le brand_id relu du scénario 15 doit correspondre à celui du site.
            if stored_brand_id:
                brand_id=stored_brand_id

            job_url=(
                api_url+"/menu/v3/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/jobs/"+urllib.parse.quote(job_id,safe="")
            )
            # Le job peut être renvoyé immédiatement avec status="new".
            # Poller le même job jusqu'à un état terminal ou jusqu'au timeout,
            # conformément au flux V3 Deliveroo.
            status=None
            response={}
            attempts=[]
            terminal_statuses={"completed","complete","succeeded","success","failed","error","cancelled","canceled"}
            for attempt in range(12):
                status,response=_api_json(job_url,token,method="GET")
                job_state=str((response or {}).get("status") or "").strip().lower() if isinstance(response,dict) else ""
                attempts.append({"attempt":attempt+1,"http_status":status,"status":job_state})
                if not 200 <= status < 300:
                    break
                if job_state in terminal_statuses:
                    break
                time.sleep(5)

            ok=bool(status is not None and 200 <= status < 300)

            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "job_id":job_id,
                "job_status_http_status":status,
                "response":response,
                "poll_attempts":attempts,
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario16",
                "error":"Scenario 16 Deliveroo impossible",
                "detail":str(exc)
            }),500


    @app.post("/api/deliveroo/scenario5-diagnostic-phase6")
    def deliveroo_scenario5_diagnostic_phase6():
        """Lecture seule : compare notre PUT au menu v1 réellement stocké chez Deliveroo."""
        payload=request.get_json(silent=True) or {}
        site_id=str(payload.get("site_id") or "").strip()
        menu_id=str(payload.get("menu_id") or "bechefaa-menu-01").strip()
        if not site_id or not menu_id:
            return jsonify({"ok":False,"error":"site_id et menu_id requis"}),400
        try:
            preview=build_deliveroo_menu_preview(db)
            token=_oauth_token()
            api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")

            brand_status,brand_data=_api_json(
                api_url+"/site/v1/restaurant_locations/"+urllib.parse.quote(site_id,safe=""),
                token,
            )
            if not 200 <= brand_status < 300:
                return jsonify({"ok":False,"stage":"brand_lookup","http_status":brand_status,"response":brand_data}),502

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            get_url=(
                api_url+"/menu/v1/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            get_status,get_response=_api_json(get_url,token,method="GET")
            if not 200 <= get_status < 300:
                return jsonify({
                    "ok":False,"stage":"get_live_menu","http_status":get_status,
                    "site_id":site_id,"brand_id":brand_id,"menu_id":menu_id,
                    "response":get_response
                }),502

            # Le PUT v1 exige menu + site_ids. pos_name est facultatif et
            # volontairement exclu pour isoler la comparaison Scenario 5.
            local_body={
                "menu":preview["payload"]["menu"],
                "site_ids":[site_id],
            }
            remote_body=get_response if isinstance(get_response,dict) else {}
            remote_compare={
                "menu":remote_body.get("menu"),
                "site_ids":remote_body.get("site_ids"),
            }

            local_norm=_deliveroo_normalize_for_compare(local_body)
            remote_norm=_deliveroo_normalize_for_compare(remote_compare)
            diffs=_deliveroo_deep_diff(local_norm,remote_norm)

            import hashlib
            local_json=json.dumps(local_norm,ensure_ascii=False,separators=(",",":"),sort_keys=True)
            remote_json=json.dumps(remote_norm,ensure_ascii=False,separators=(",",":"),sort_keys=True)

            return jsonify({
                "ok":True,
                "read_only":True,
                "put_performed":False,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "get_http_status":get_status,
                "exact_match_after_normalization":local_norm==remote_norm,
                "bechefaa_sha256":hashlib.sha256(local_json.encode("utf-8")).hexdigest(),
                "deliveroo_sha256":hashlib.sha256(remote_json.encode("utf-8")).hexdigest(),
                "difference_count_returned":len(diffs),
                "difference_limit":200,
                "differences":diffs,
                "semantic_compare_by_id":_deliveroo_compare_by_id(
                    local_body.get("menu") or {},
                    remote_compare.get("menu") or {}
                ),
                "bechefaa_summary":preview.get("summary"),
                "remote_top_level_keys":sorted(remote_body.keys()),
                "note":"Aucun PUT envoyé. GET v1 Deliveroo comparé au payload BÉCHÉFAA sans pos_name."
            }),200
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario5_diagnostic",
                "error":"Diagnostic Scenario 5 impossible","detail":str(exc)
            }),500

    @app.post("/api/deliveroo/scenario17-get-menu-v3-phase6")
    def deliveroo_scenario17_get_menu_v3_phase6():
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

            raw_brand_id=(
                brand_data.get("brand_id")
                or brand_data.get("brand_ids")
                or ((brand_data.get("brand") or {}).get("id") if isinstance(brand_data.get("brand"),dict) else "")
                or ""
            )
            if isinstance(raw_brand_id,(list,tuple)):
                raw_brand_id=raw_brand_id[0] if raw_brand_id else ""
            brand_id=str(raw_brand_id or "").strip()
            if not brand_id:
                return jsonify({"ok":False,"stage":"brand_lookup","error":"brand_id absent"}),502

            url=(
                api_url+"/menu/v3/brands/"+urllib.parse.quote(brand_id,safe="")
                +"/menus/"+urllib.parse.quote(menu_id,safe="")
            )
            status,response=_api_json(url,token,method="GET")
            ok=200 <= status < 300

            return jsonify({
                "ok":ok,
                "site_id":site_id,
                "brand_id":brand_id,
                "menu_id":menu_id,
                "http_status":status,
                "response":response
            }),200 if ok else 502
        except Exception as exc:
            return jsonify({
                "ok":False,"stage":"scenario17",
                "error":"Scenario 17 Deliveroo impossible",
                "detail":str(exc)
            }),500

    @app.get("/administration/deliveroo-upload")
    def deliveroo_upload_page_phase6():
        return Response("""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Deliveroo Sandbox</title><style>*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#f4f7fb;color:#14213d;margin:0}.w{max-width:760px;margin:32px auto;padding:18px}.b{background:#fff;border:1px solid #e5eaf1;border-radius:18px;padding:24px;box-shadow:0 8px 24px #25466e12}h1{margin-top:0}label{display:block;font-weight:900;margin:16px 0 6px}input,button{width:100%;min-height:48px;border-radius:10px;border:1px solid #ccd5e2;padding:10px;font-size:16px}button{margin-top:20px;background:#111827;color:#fff;font-weight:900;cursor:pointer}.m{color:#667085}.out{white-space:pre-wrap;background:#0b1220;color:#dce6f4;padding:16px;border-radius:12px;margin-top:18px;min-height:90px}</style></head><body><div class="w"><div class="b"><h1>Upload Deliveroo Sandbox</h1><p class="m">Envoie réellement le menu BÉCHÉFAA validé vers le site Sandbox indiqué.</p><label>Site ID Sandbox</label><input id="site" placeholder="Collez le Site ID Deliveroo"><label>Menu ID</label><input id="menu" value="bechefaa-menu-01"><button id="s1">SCENARIO 1 • FETCH BRAND ID</button><button id="send">ENVOYER LE MENU SANDBOX</button><button id="s5">SCENARIO 5 • TEST MENU IDENTIQUE</button><button id="s5diag">DIAGNOSTIC S5 • COMPARER SANS ENVOYER</button><button id="s8">SCENARIO 8 • ENVOYER LES 2 POST INDISPONIBILITÉS</button><button id="s9">SCENARIO 9 • GET + PUT INDISPONIBILITÉS</button><button id="s10">SCENARIO 10 • RÉINITIALISER LE STOCK</button><button id="s11">SCENARIO 11 • ÉTAT AVANT RESET MATINAL</button><button id="s12">SCENARIO 12 • BLOQUER LE RESET MATINAL</button><button id="s12state">DIAGNOSTIC S12 • ÉTAT</button><button id="s12statuses">DIAGNOSTIC S12 • TEST 3 STATUTS</button><button id="s12official">DIAGNOSTIC S12 • BODY OFFICIEL</button><button id="s12expected">DIAGNOSTIC S12 • BODY ATTENDU</button><button id="s12v2">DIAGNOSTIC S12 • POST V2</button><button id="s12diag">DIAGNOSTIC S12 • TRACE POST</button><button id="s13u">SCENARIO 13 • 1/2 UPLOAD 100+ ITEMS</button><button id="s13s">SCENARIO 13 • 2/2 STOCK APRÈS WEBHOOK</button><button id="s14">SCENARIO 14 • GÉNÉRER URL S3</button><button id="s15">SCENARIO 15 • V3 UPLOAD S3 + JOB</button><button id="s16">SCENARIO 16 • STATUT DU JOB V3</button><button id="s17">SCENARIO 17 • GET MENU V3</button><div id="out" class="out">Prêt.</div></div></div><script>const out=document.getElementById('out'),btn=document.getElementById('send'),s1=document.getElementById('s1'),s5=document.getElementById('s5'),s5diag=document.getElementById('s5diag'),s8=document.getElementById('s8'),s9=document.getElementById('s9'),s10=document.getElementById('s10'),s11=document.getElementById('s11'),s12=document.getElementById('s12'),s12state=document.getElementById('s12state'),s12statuses=document.getElementById('s12statuses'),s12official=document.getElementById('s12official'),s12expected=document.getElementById('s12expected'),s12v2=document.getElementById('s12v2'),s12diag=document.getElementById('s12diag'),s13u=document.getElementById('s13u'),s13s=document.getElementById('s13s'),s14=document.getElementById('s14'),s15=document.getElementById('s15'),s16=document.getElementById('s16'),s17=document.getElementById('s17');btn.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site){out.textContent='Site ID requis.';return}btn.disabled=true;out.textContent='Upload en cours…';try{const r=await fetch('/api/deliveroo/menu-upload-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{btn.disabled=false}};s1.onclick=async()=>{const site=document.getElementById('site').value.trim();if(!site){out.textContent='Site ID requis.';return}s1.disabled=true;out.textContent='Scenario 1 : récupération du Brand ID…';try{const r=await fetch('/api/deliveroo/scenario1-fetch-brand-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s1.disabled=false}};s5.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s5.disabled=true;out.textContent='Scenario 5 : vérification du menu déjà enregistré…';try{const r=await fetch('/api/deliveroo/scenario5-identical-menu-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s5.disabled=false}};s5diag.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s5diag.disabled=true;out.textContent='Diagnostic S5 : lecture Deliveroo + comparaison, aucun upload…';try{const r=await fetch('/api/deliveroo/scenario5-diagnostic-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s5diag.disabled=false}};s8.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s8.disabled=true;out.textContent='Scenario 8 : envoi des 2 POST…';try{const r=await fetch('/api/deliveroo/scenario8-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s8.disabled=false}};s9.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s9.disabled=true;out.textContent='Scenario 9 : GET puis PUT…';try{const r=await fetch('/api/deliveroo/scenario9-replace-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s9.disabled=false}};s10.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s10.disabled=true;out.textContent='Scenario 10 : réinitialisation du stock…';try{const r=await fetch('/api/deliveroo/scenario10-reset-unavailabilities-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s10.disabled=false}};s11.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s11.disabled=true;out.textContent='Scenario 11 : état initial avant reset matinal…';try{const r=await fetch('/api/deliveroo/scenario11-morning-reset-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s11.disabled=false}};s12.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12.disabled=true;out.textContent='Scenario 12 : changement après minuit…';try{const r=await fetch('/api/deliveroo/scenario12-ignore-morning-reset-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12.disabled=false}};s12state.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12state.disabled=true;out.textContent='Diagnostic S12 : lecture de l état…';try{const r=await fetch('/api/deliveroo/scenario12-state-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});out.textContent=JSON.stringify(await r.json(),null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12state.disabled=false}};s12statuses.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12statuses.disabled=true;out.textContent='Diagnostic S12 : unavailable → hidden → available…';try{const r=await fetch('/api/deliveroo/scenario12-statuses-diagnostic-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});out.textContent=JSON.stringify(await r.json(),null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12statuses.disabled=false}};s12official.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12official.disabled=true;out.textContent='Diagnostic S12 : envoi du body officiel Deliveroo…';try{const r=await fetch('/api/deliveroo/scenario12-official-body-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});out.textContent=JSON.stringify(await r.json(),null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12official.disabled=false}};s12v2.onclick=async()=>{const site=document.getElementById('site').value.trim();if(!site){out.textContent='Site ID requis.';return}s12v2.disabled=true;out.textContent='Diagnostic S12 : POST v2 officiel…';try{const r=await fetch('/api/deliveroo/scenario12-v2-diagnostic-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site})});out.textContent=JSON.stringify(await r.json(),null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12v2.disabled=false}};s12expected.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12expected.disabled=true;out.textContent='Diagnostic S12 : envoi du body attendu…';try{const r=await fetch('/api/deliveroo/scenario12-expected-body-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});out.textContent=JSON.stringify(await r.json(),null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12expected.disabled=false}};s12diag.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s12diag.disabled=true;out.textContent='Diagnostic S12 : GET avant, POST réel, GET après…';try{const r=await fetch('/api/deliveroo/scenario12-diagnostic-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s12diag.disabled=false}};s13u.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s13u.disabled=true;out.textContent='Scenario 13 : upload 100+ items…';try{const r=await fetch('/api/deliveroo/scenario13-upload-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s13u.disabled=false}};s13s.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s13s.disabled=true;out.textContent='Scenario 13 : vérification webhook puis stock…';try{const r=await fetch('/api/deliveroo/scenario13-stock-after-webhook-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s13s.disabled=false}};s14.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s14.disabled=true;out.textContent='Scenario 14 : génération URL S3…';try{const r=await fetch('/api/deliveroo/scenario14-generate-s3-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s14.disabled=false}};s15.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s15.disabled=true;out.textContent='Scenario 15 : S3 + job V3…';try{const r=await fetch('/api/deliveroo/scenario15-v3-async-upload-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s15.disabled=false}};s16.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s16.disabled=true;out.textContent='Scenario 16 : statut du job V3…';try{const r=await fetch('/api/deliveroo/scenario16-job-status-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s16.disabled=false}};s17.onclick=async()=>{const site=document.getElementById('site').value.trim(),menu=document.getElementById('menu').value.trim();if(!site||!menu){out.textContent='Site ID et Menu ID requis.';return}s17.disabled=true;out.textContent='Scenario 17 : GET Menu V3…';try{const r=await fetch('/api/deliveroo/scenario17-get-menu-v3-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,menu_id:menu})});const j=await r.json();out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent='Erreur : '+e.message}finally{s17.disabled=false}};</script></body></html>""",content_type="text/html; charset=utf-8")
