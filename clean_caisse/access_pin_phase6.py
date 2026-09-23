"""Protection d'accès de la caisse BÉCHÉFAA par code PIN.

- L'écran racine demande toujours le PIN (pratique pour le raccourci tablette).
- Les écrans et API internes exigent une session authentifiée.
- Les API publiques du site, Mollie et Edenred restent accessibles.
- Toutes les réponses de la caisse demandent aux moteurs de ne pas indexer.
"""
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque

from flask import Response, jsonify, redirect, request, session


_PUBLIC_PREFIXES = (
    "/api/public/",
    "/api/mollie/",
    "/api/edenred/",
    "/api/edenred-prod/",
)

_PUBLIC_EXACT = {
    "/api/health",
    "/favicon.ico",
    "/robots.txt",
    "/auth/pin",
    "/auth/logout",
    "/caisse-manifest.webmanifest",
    "/caisse-icon.png",
    "/caisse-icon-512.svg",
    "/caisse-sw.js",
}

_FAILS = defaultdict(deque)
_MAX_FAILS = 5
_WINDOW_SECONDS = 300
_LOCK_SECONDS = 60


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _pin_configured():
    pin = str(os.getenv("BECHEFAA_CAISSE_PIN") or "").strip()
    return pin if len(pin) >= 4 else ""


def _login_html(error="", locked=False):
    message = ""
    if error:
        message = f'<div class="error">{error}</div>'
    button_text = "Réessayer dans une minute" if locked else "OUVRIR LA CAISSE"
    disabled = " disabled" if locked else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>BÉCHÉFAA Caisse</title>
<meta name="theme-color" content="#090909">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="BÉCHÉFAA Caisse">
<link rel="manifest" href="/caisse-manifest.webmanifest">
<link rel="icon" type="image/png" href="/caisse-icon.png?v=5">
<link rel="apple-touch-icon" href="/caisse-icon.png">
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;font-family:Arial,sans-serif;background:#090909;color:#fff}}
body{{min-height:100vh;display:grid;place-items:center;padding:24px}}
.card{{width:min(430px,100%);background:#121212;border:1px solid #c9a44d;border-radius:22px;padding:30px 26px;box-shadow:0 22px 70px #0008;text-align:center}}
.logo{{width:82px;height:82px;margin:0 auto 16px;border-radius:22px;border:2px solid #d7b35a;display:grid;place-items:center;font-size:38px;font-weight:900;color:#d7b35a}}
h1{{margin:0;font-size:28px;letter-spacing:.5px}} .gold{{color:#d7b35a}}
p{{color:#bbb;margin:8px 0 22px}}
input{{width:100%;font-size:28px;letter-spacing:10px;text-align:center;padding:14px;border-radius:12px;border:1px solid #555;background:#080808;color:#fff;outline:none}}
input:focus{{border-color:#d7b35a;box-shadow:0 0 0 3px #d7b35a22}}
button{{width:100%;margin-top:14px;padding:15px;border:0;border-radius:12px;background:#d7b35a;color:#111;font-weight:900;font-size:16px;cursor:pointer}}
button:disabled{{opacity:.45;cursor:not-allowed}}
.error{{background:#3b1111;border:1px solid #7e2929;color:#ffd6d6;padding:10px;border-radius:10px;margin-bottom:14px}}
small{{display:block;margin-top:18px;color:#777}}
</style>
</head>
<body>
<main class="card">
  <div class="logo"><img src="/caisse-icon.png?v=5" alt="BÉCHÉFAA Caisse" style="width:100%;height:100%;object-fit:contain;border-radius:20px"></div>
  <h1>BÉCHÉFAA <span class="gold">CAISSE</span></h1>
  <p>Saisissez votre code d'accès.</p>
  {message}
  <form method="post" action="/auth/pin" autocomplete="off">
    <input name="pin" type="password" inputmode="numeric" pattern="[0-9]*" minlength="4" maxlength="12" autofocus aria-label="Code d'accès">
    <button type="submit"{disabled}>{button_text}</button>
  </form>
  <small>Accès réservé au personnel BÉCHÉFAA</small>
</main>
<script>
if ("serviceWorker" in navigator) {{
  window.addEventListener("load", () => {{
    navigator.serviceWorker.register("/caisse-sw.js", {{scope:"/"}}).catch(() => {{}});
  }});
}}
</script>
</body>
</html>"""


def register_access_pin_phase6(app):
    # Secret de session stable sans exposer de secret supplémentaire.
    if not app.secret_key:
        explicit = (
            os.getenv("BECHEFAA_CAISSE_SESSION_SECRET")
            or os.getenv("SECRET_KEY")
            or os.getenv("FLASK_SECRET_KEY")
            or ""
        )
        if explicit:
            app.secret_key = explicit
        else:
            seed = (
                os.getenv("POSTGRESQL_ADDON_URI")
                or os.getenv("DATABASE_URL")
                or "bechefaa-caisse"
            )
            app.secret_key = hashlib.sha256(
                ("bechefaa-caisse-session-v1|" + seed).encode("utf-8")
            ).hexdigest()

    app.config.update(
        SESSION_COOKIE_NAME="bechefaa_caisse_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    @app.after_request
    def _noindex(response):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/robots.txt")
    def _robots():
        return Response("User-agent: *\nDisallow: /\n", content_type="text/plain; charset=utf-8")

    @app.post("/auth/pin")
    def _auth_pin():
        expected = _pin_configured()
        if not expected:
            return Response(
                _login_html("Code d'accès non configuré. Contactez l'administrateur."),
                status=503,
                content_type="text/html; charset=utf-8",
            )

        ip = _client_ip()
        now = time.time()
        failures = _FAILS[ip]
        while failures and now - failures[0] > _WINDOW_SECONDS:
            failures.popleft()

        if len(failures) >= _MAX_FAILS and now - failures[-1] < _LOCK_SECONDS:
            return Response(
                _login_html("Trop de tentatives. Réessayez dans une minute.", locked=True),
                status=429,
                content_type="text/html; charset=utf-8",
            )

        supplied = str(request.form.get("pin") or "").strip()
        if not hmac.compare_digest(supplied, expected):
            failures.append(now)
            return Response(
                _login_html("Code incorrect."),
                status=401,
                content_type="text/html; charset=utf-8",
            )

        failures.clear()
        session.clear()
        session["caisse_auth"] = True
        session.permanent = False
        return redirect("/pos", code=303)

    @app.get("/auth/logout")
    def _auth_logout():
        session.clear()
        return redirect("/", code=303)

    @app.before_request
    def _protect_caisse():
        path = request.path or "/"

        # Le raccourci tablette arrive toujours sur / et demande le PIN,
        # même si une ancienne session navigateur existe encore.
        if path == "/":
            return Response(
                _login_html(),
                content_type="text/html; charset=utf-8",
            )

        if request.method == "OPTIONS":
            return None

        # Appel serveur interne depuis les ponts SITE validés. Ce marqueur est
        # posé uniquement dans le contexte Flask interne, jamais par le navigateur.
        if request.environ.get("bechefaa.internal_dispatch") == "1":
            return None

        if path in _PUBLIC_EXACT or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return None

        if session.get("caisse_auth") is True:
            return None

        if path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Accès caisse verrouillé"}), 401

        return redirect("/", code=303)
