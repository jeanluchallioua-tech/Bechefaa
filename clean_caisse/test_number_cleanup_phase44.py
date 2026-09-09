"""Phase 4.4 — outil ponctuel de nettoyage de numérotation des commandes de test.

Cet outil n'est destiné qu'aux données de développement avant mise en production.
Il compacte les numéros visibles à partir d'un seuil, conserve les commandes annulées
pour audit avec leur numéro d'origine dans une colonne dédiée, et ne touche pas aux
numéros de tickets comptables.
"""
from flask import Response, jsonify, request


def register_test_number_cleanup_phase44(app, db, ensure_order_schema):
    def ensure_cleanup_schema(conn):
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS original_operational_num BIGINT NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE")

    @app.get("/maintenance/phase44/numbering")
    def test_number_cleanup_page_phase44():
        start = request.args.get("start", "63")
        try:
            start_num = int(start)
        except Exception:
            start_num = 63
        try:
            with db() as conn:
                ensure_cleanup_schema(conn)
                conn.commit()
                rows = conn.execute("""
                    SELECT num,status,COALESCE(cancellation_hidden,FALSE) AS hidden
                    FROM caisse_orders
                    WHERE ABS(num) >= %s
                    ORDER BY created_at,num
                """, (start_num,)).fetchall()
            visible = [str(r["num"]) for r in rows if not r["hidden"]]
            hidden = [str(r["num"]) for r in rows if r["hidden"]]
            body = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Nettoyage numérotation test</title><style>body{{font-family:Arial;background:#f4f5f7;padding:30px;color:#17191c}}.card{{max-width:680px;margin:auto;background:#fff;padding:24px;border-radius:14px}}button{{width:100%;padding:14px;border:0;border-radius:10px;background:#b42318;color:#fff;font-weight:900;font-size:16px}}code{{background:#f1f3f5;padding:3px 6px;border-radius:5px}}</style></head><body><div class="card"><h1>Nettoyage numérotation TEST</h1><p>Départ : <code>#{start_num}</code></p><p>Commandes visibles : <b>{', '.join(visible) or 'aucune'}</b></p><p>Commandes annulées conservées techniquement : <b>{', '.join(hidden) or 'aucune'}</b></p><p><b>Cette opération est réservée aux données de développement.</b> Les tickets comptables ne seront pas modifiés.</p><form method="post"><input type="hidden" name="start" value="{start_num}"><button type="submit">NORMALISER LA NUMÉROTATION TEST</button></form></div></body></html>'''
            return Response(body, content_type="text/html; charset=utf-8")
        except Exception as exc:
            return Response("Maintenance indisponible : " + str(exc), status=500)

    @app.post("/maintenance/phase44/numbering")
    def test_number_cleanup_apply_phase44():
        try:
            start_num = int(request.form.get("start") or 63)
        except Exception:
            return jsonify({"ok": False, "error": "Numéro de départ invalide"}), 400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_cleanup_schema(conn)
                    conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                    rows = conn.execute("""
                        SELECT id,num,created_at,COALESCE(cancellation_hidden,FALSE) AS hidden
                        FROM caisse_orders
                        WHERE num >= %s OR (num < 0 AND original_operational_num >= %s)
                        ORDER BY created_at,num
                        FOR UPDATE
                    """, (start_num, start_num)).fetchall()

                    visible = [r for r in rows if not r["hidden"]]
                    hidden = [r for r in rows if r["hidden"]]

                    # Écarte d'abord toute la plage pour respecter la contrainte UNIQUE(num).
                    for r in visible + hidden:
                        original = int(r["num"])
                        if original < 0 and r.get("original_operational_num"):
                            original = int(r["original_operational_num"])
                        conn.execute("""
                            UPDATE caisse_orders
                            SET original_operational_num=COALESCE(original_operational_num,%s),
                                num=%s
                            WHERE id=%s
                        """, (original, -(2000000 + abs(original)), r["id"]))

                    next_num = start_num
                    changes = []
                    for r in visible:
                        old = int(r["num"])
                        conn.execute("UPDATE caisse_orders SET num=%s WHERE id=%s", (next_num, r["id"]))
                        changes.append({"id": r["id"], "from": old, "to": next_num})
                        next_num += 1

                    # Les annulées restent hors de la plage opérationnelle positive.
                    for r in hidden:
                        original = int(r["num"])
                        conn.execute("UPDATE caisse_orders SET num=%s WHERE id=%s", (-(1000000 + abs(original)), r["id"]))

            return Response(
                '<!doctype html><html lang="fr"><meta charset="utf-8"><body style="font-family:Arial;padding:30px"><h1>Numérotation test normalisée</h1><p>Les commandes visibles ont été compactées. Les commandes annulées restent conservées techniquement hors de la séquence opérationnelle.</p><p><a href="/historique">Retour à l’historique</a></p></body></html>',
                content_type="text/html; charset=utf-8",
            )
        except Exception as exc:
            return Response("Nettoyage impossible : " + str(exc), status=500)
