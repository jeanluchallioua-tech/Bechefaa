"""Phase 4.4 — contrôle serveur isolé de la garde anti-réencaissement.

Aucun JavaScript. GET affiche uniquement la page. POST exécute en interne une
requête PUT de test sur la commande #65 via le client Flask : la vraie garde
before_request doit répondre 409 avant le moteur Phase 4.1.
"""
from flask import Response, request

TEST_ORDER_ID = "caisse-1c123f071e8c4500bc798b6ec5913df3"


def register_payment_guard_test_phase44(app):
    @app.route("/maintenance/phase44/payment-guard-test", methods=["GET", "POST"])
    def payment_guard_test_phase44():
        result = "Test non lancé."
        verdict = ""
        verdict_class = ""

        if request.method == "POST":
            try:
                with app.test_client() as client:
                    response = client.put(
                        f"/api/orders/{TEST_ORDER_ID}/payment-phase41",
                        json={"method": "CB"},
                    )
                    data = response.get_json(silent=True) or {}

                result = f"HTTP {response.status_code}\n{data}"
                if response.status_code == 409 and data.get("ok") is False:
                    verdict = "✓ PROTECTION ACTIVE — nouvel encaissement refusé."
                    verdict_class = "ok"
                else:
                    verdict = "✕ TEST NON CONFORME — ne pas considérer la garde comme validée."
                    verdict_class = "bad"
            except Exception as exc:
                verdict = "✕ TEST IMPOSSIBLE"
                verdict_class = "bad"
                result = str(exc)

        html = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test garde encaissement Phase 4.4</title>
<style>
body{{font-family:Arial,sans-serif;background:#f8fafc;color:#0f172a;padding:24px}}
.box{{max-width:620px;margin:auto;background:#fff;border:1px solid #cbd5e1;border-radius:16px;padding:22px}}
button{{border:0;border-radius:10px;padding:13px 16px;background:#7c3aed;color:#fff;font-weight:900;cursor:pointer}}
pre{{white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:14px;border-radius:10px;min-height:80px}}
.ok{{color:#166534;font-weight:900}}.bad{{color:#b91c1c;font-weight:900}}
</style></head><body><div class="box">
<h2>Contrôle anti-réencaissement — commande #65</h2>
<p>Cette commande est partiellement remboursée. Le résultat attendu est <strong>HTTP 409</strong>. Aucun nouvel encaissement ne doit être créé.</p>
<form method="post"><button type="submit">Tester la protection serveur</button></form>
<p class="{verdict_class}">{verdict}</p><pre>{result}</pre>
</div></body></html>'''
        return Response(html, mimetype="text/html")
