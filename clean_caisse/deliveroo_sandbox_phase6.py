"""Deliveroo Sandbox connectivity check for BÉCHÉFAA.

Reads credentials from Clever Cloud environment variables and exchanges them for
an OAuth2 client_credentials token. Secrets/tokens are never returned.
"""
import os
import urllib.parse
import urllib.request
import json
from flask import jsonify, request

_last_webhooks = {"orders": None, "menu": None}

def register_deliveroo_sandbox_phase6(app):
    def _capture_webhook(kind):
        payload = request.get_json(silent=True) or {}
        event = str(payload.get("event") or "")
        guid = (request.headers.get("X-Deliveroo-Sequence-Guid") or "").strip()
        payload_type = (request.headers.get("X-Deliveroo-Payload-Type") or "").strip()
        version = (request.headers.get("X-Deliveroo-Webhook-Version") or "").strip()
        _last_webhooks[kind] = {
            "received": True,
            "event": event,
            "sequence_guid": guid,
            "payload_type": payload_type,
            "webhook_version": version,
        }
        app.logger.info(
            "Deliveroo sandbox webhook kind=%s event=%s guid=%s payload_type=%s version=%s",
            kind, event, guid, payload_type, version
        )
        return jsonify({"ok": True}), 200

    @app.post("/api/deliveroo/webhooks/orders")
    def deliveroo_orders_webhook_phase6():
        # Phase 1: acknowledge only. No POS order is created until the Sandbox
        # payload has been observed and HMAC verification has been configured.
        return _capture_webhook("orders")

    @app.post("/api/deliveroo/webhooks/menu")
    def deliveroo_menu_webhook_phase6():
        return _capture_webhook("menu")

    @app.get("/api/deliveroo/webhooks/status-phase6")
    def deliveroo_webhooks_status_phase6():
        return jsonify({
            "ok": True,
            "orders_url": "https://caisse.bechefaa.fr/api/deliveroo/webhooks/orders",
            "menu_url": "https://caisse.bechefaa.fr/api/deliveroo/webhooks/menu",
            "last_orders": _last_webhooks["orders"],
            "last_menu": _last_webhooks["menu"],
        })

    @app.get("/api/deliveroo/status-phase6")
    def deliveroo_status_phase6():
        client_id=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_ID") or "").strip()
        client_secret=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_SECRET") or "").strip()
        auth_url=(os.environ.get("BECHEFAA_DELIVEROO_AUTH_URL") or "https://auth-sandbox.developers.deliveroo.com").rstrip("/")
        api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
        result={
            "ok":False,
            "environment":"sandbox",
            "client_id_present":bool(client_id),
            "client_secret_present":bool(client_secret),
            "auth_url":auth_url,
            "api_url":api_url,
        }
        if not client_id or not client_secret:
            result["error"]="missing_credentials"
            return jsonify(result), 503
        body=urllib.parse.urlencode({
            "client_id":client_id,
            "client_secret":client_secret,
            "grant_type":"client_credentials",
        }).encode("utf-8")
        req=urllib.request.Request(
            auth_url+"/oauth2/token",
            data=body,
            headers={"Content-Type":"application/x-www-form-urlencoded; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=12) as resp:
                data=json.loads(resp.read().decode("utf-8"))
            token=data.get("access_token")
            result.update({
                "ok":bool(token),
                "token_received":bool(token),
                "token_type":data.get("token_type"),
                "expires_in":data.get("expires_in"),
            })
            return jsonify(result), 200 if token else 502
        except Exception as exc:
            code=getattr(exc,"code",None)
            detail=""
            try:
                detail=exc.read().decode("utf-8","replace")[:300]
            except Exception:
                detail=str(exc)[:300]
            result.update({"error":"oauth_failed","status_code":code,"detail":detail})
            return jsonify(result), 502
