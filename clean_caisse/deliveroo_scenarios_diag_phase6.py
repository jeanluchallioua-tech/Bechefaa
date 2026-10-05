"""Diagnostic read-only pour les credentials Deliveroo Scenarios API.

Aucune exécution de scénario. Vérifie l'authentification puis sonde les
familles de scénarios exposées par le Developer Portal API.
"""
import json
import os
import urllib.parse
import urllib.request
from urllib.error import HTTPError

from flask import jsonify


def register_deliveroo_scenarios_diag_phase6(app):
    def token():
        client_id=(os.environ.get("BECHEFAA_DELIVEROO_SCENARIOS_CLIENT_ID") or "").strip()
        client_secret=(os.environ.get("BECHEFAA_DELIVEROO_SCENARIOS_CLIENT_SECRET") or "").strip()
        auth_url="https://auth-sandbox.developers.deliveroo.com"
        if not client_id or not client_secret:
            raise RuntimeError("Scenarios API credentials missing")
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
                "User-Agent":"Bechefaa-Deliveroo-Scenarios-Diagnostic/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=15) as resp:
                raw=resp.read().decode("utf-8","replace")
                data=json.loads(raw) if raw else {}
                access=str(data.get("access_token") or "").strip()
                if not access:
                    raise RuntimeError("Scenarios API token missing")
                return access, int(resp.status), int(data.get("expires_in") or 0)
        except HTTPError as exc:
            raw=exc.read().decode("utf-8","replace")
            raise RuntimeError("Scenarios OAuth HTTP %s: %s" % (exc.code, raw[:600]))

    def api_get(url, access):
        req=urllib.request.Request(
            url,
            headers={
                "Authorization":"Bearer "+access,
                "Accept":"application/json",
                "User-Agent":"Bechefaa-Deliveroo-Scenarios-Diagnostic/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req,timeout=20) as resp:
                raw=resp.read().decode("utf-8","replace")
                try:
                    body=json.loads(raw) if raw else {}
                except Exception:
                    body={"raw":raw[:1500]}
                return int(resp.status),body
        except HTTPError as exc:
            raw=exc.read().decode("utf-8","replace")
            try:
                body=json.loads(raw) if raw else {}
            except Exception:
                body={"raw":raw[:1500]}
            return int(exc.code),body

    def summary(body):
        # Preserve enough response data to identify scenario IDs/titles while
        # preventing unexpectedly huge portal payloads.
        if isinstance(body,list):
            return body[:80]
        if isinstance(body,dict):
            out=dict(body)
            for k,v in list(out.items()):
                if isinstance(v,list) and len(v)>80:
                    out[k]=v[:80]
            return out
        return body

    @app.get("/api/deliveroo/scenarios-api-diagnostic-phase6")
    def scenarios_api_diagnostic_phase6():
        try:
            access,oauth_status,expires_in=token()
        except Exception as exc:
            return jsonify({
                "ok":False,
                "stage":"oauth",
                "error":str(exc),
                "credentials_present":bool((os.environ.get("BECHEFAA_DELIVEROO_SCENARIOS_CLIENT_ID") or "").strip())
                    and bool((os.environ.get("BECHEFAA_DELIVEROO_SCENARIOS_CLIENT_SECRET") or "").strip()),
            }),500

        base="https://api-sandbox.developers.deliveroo.com/dev-portal/scenarios"
        probes={}
        # "menu" is intentionally probed even though it is not currently listed
        # in the public enum. pos_orders is the documented control probe.
        for api_name in ("menu","menus","partner_platform","pos_orders"):
            status,body=api_get(base+"?"+urllib.parse.urlencode({"api":api_name}),access)
            probes[api_name]={"http_status":status,"response":summary(body)}

        menu_matches=[]
        def walk(value,path=""):
            if isinstance(value,dict):
                text_blob=" ".join(str(value.get(k) or "") for k in ("id","name","title","description","label"))
                if "menu" in text_blob.lower():
                    menu_matches.append({"path":path or "$","value":value})
                for k,v in value.items():
                    walk(v,(path+"."+str(k)) if path else str(k))
            elif isinstance(value,list):
                for i,v in enumerate(value):
                    walk(v,(path+"["+str(i)+"]"))
        for key,probe in probes.items():
            if probe["http_status"]==200:
                walk(probe["response"],key)

        return jsonify({
            "ok":True,
            "oauth":{"http_status":oauth_status,"token_received":True,"expires_in":expires_in},
            "read_only":True,
            "scenario_run_triggered":False,
            "probes":probes,
            "menu_matches":menu_matches[:40],
            "next":"If a Menu scenario family is exposed, use its IDs to inspect runs 12 and 16. Otherwise the public Scenarios API does not expose Menu scenarios for this credential/contract.",
        })
