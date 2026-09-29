"""Nettoyage sélectif avant mise en service réelle.

Conserve:
- les commandes réelles confirmées #38, #39, #40, #41, #42, #51 et #55;
- toute commande déjà rattachée à une clôture Z;
- toutes les transactions liées aux commandes conservées.

Supprime uniquement les commandes de test non protégées et leurs lignes/transactions.
Ne touche jamais aux réglages, clients, catalogue, notifications, matériel, PIN ou Z.
"""
from flask import jsonify, request

CONFIRMATION = "NETTOYAGE_TESTS_SANS_TOUCHER_CB"
CARD_WORDS = ("CB", "CARTE", "CARD", "VISA", "MASTERCARD")


def _has_column(conn, table, column):
    row = conn.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name=%s AND column_name=%s""",
        (table, column),
    ).fetchone()
    return bool(row)


def _protected_order_ids(conn):
    """Conserve uniquement les commandes réelles identifiées + toute commande déjà clôturée Z.

    Commandes réelles confirmées par l'utilisateur:
    - #38 = 38,50 EUR
    - #39 à #42 = 1,00 EUR
    - #51 et #55 = 0,50 EUR

    Toutes les transactions financières de ces commandes restent conservées.
    """
    real_nums = {38, 39, 40, 41, 42, 51, 55}
    z_exists = _has_column(conn, "caisse_orders", "z_closure_id")
    z_clause = "OR z_closure_id IS NOT NULL" if z_exists else ""
    rows = conn.execute(
        f"""SELECT id
            FROM caisse_orders
            WHERE num = ANY(%s) {z_clause}""",
        (list(real_nums),),
    ).fetchall()
    return {str(r["id"]) for r in rows}


def _preview(conn):
    protected = _protected_order_ids(conn)
    rows = conn.execute(
        """SELECT id,num,total,payment,status,created_at
           FROM caisse_orders ORDER BY created_at,num"""
    ).fetchall()
    keep, delete = [], []
    for r in rows:
        item = {
            "id": str(r["id"]),
            "num": r["num"],
            "total": float(r["total"] or 0),
            "payment": r["payment"],
            "status": r["status"],
            "created_at": r["created_at"],
        }
        (keep if str(r["id"]) in protected else delete).append(item)
    return {
        "keep_count": len(keep),
        "keep_total": round(sum(x["total"] for x in keep), 2),
        "delete_count": len(delete),
        "delete_total": round(sum(x["total"] for x in delete), 2),
        "kept_orders": keep,
        "deleted_candidates": delete,
        "notifications_preserved": True,
        "notification_settings_preserved": True,
        "z_preserved": True,
    }


def register_selective_reset_phase6(app, db):
    @app.get("/api/maintenance/selective-reset-phase6/preview")
    def selective_reset_preview_phase6():
        try:
            with db() as conn:
                return jsonify({"ok": True, **_preview(conn)})
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Aperçu du nettoyage sélectif indisponible",
                "detail": str(exc),
            }), 500

    @app.get("/maintenance/selective-reset")
    def selective_reset_page_phase6():
        from flask import Response
        return Response("""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nettoyage BÉCHÉFAA</title>
<style>body{font-family:Arial;background:#0b0b0b;color:#fff;padding:24px}.box{max-width:760px;margin:auto;background:#171717;border:1px solid #c9a44d;border-radius:16px;padding:22px}button{width:100%;padding:16px;margin-top:18px;font-size:18px;font-weight:800;border:0;border-radius:10px;background:#c9a44d;color:#111}button:disabled{opacity:.45}.ok{background:#183c22;padding:14px;border-radius:10px}.warn{background:#4b2b18;padding:14px;border-radius:10px}.row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #333}</style>
</head><body><div class="box"><h1>Nettoyage sélectif</h1>
<div id="state">Chargement…</div>
<button id="go" disabled>LANCER LE NETTOYAGE</button>
</div>
<script>
const s=document.getElementById('state'),b=document.getElementById('go');
async function preview(){
 const r=await fetch('/api/maintenance/selective-reset-phase6/preview',{cache:'no-store'}),d=await r.json();
 if(!r.ok||!d.ok){s.className='warn';s.textContent='Erreur aperçu';return}
 s.className='ok';
 s.innerHTML='<div class="row"><span>À conserver</span><b>'+d.keep_count+' commandes — '+Number(d.keep_total).toFixed(2)+' €</b></div><div class="row"><span>À supprimer</span><b>'+d.delete_count+' commandes — '+Number(d.delete_total).toFixed(2)+' €</b></div>';
 b.disabled=false;
}
b.onclick=async()=>{
 b.disabled=true;
 const r=await fetch('/api/maintenance/selective-reset-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation:'NETTOYAGE_TESTS_SANS_TOUCHER_CB'})});
 const d=await r.json();
 if(!r.ok||!d.ok){s.className='warn';s.textContent=(d.error||'Échec')+(d.detail?' — '+d.detail:'');b.disabled=false;return}
 s.className='ok';s.innerHTML='<b>Nettoyage terminé.</b><br>'+d.deleted.orders+' commande(s) de test supprimée(s).';
};
preview();
</script></body></html>""", content_type="text/html; charset=utf-8")

    @app.post("/api/maintenance/selective-reset-phase6")
    def selective_reset_execute_phase6():
        payload = request.get_json(silent=True) or {}
        if str(payload.get("confirmation") or "").strip() != CONFIRMATION:
            return jsonify({"ok": False, "error": "Phrase de confirmation incorrecte"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(20260929)")
                    before = _preview(conn)
                    protected = _protected_order_ids(conn)
                    all_rows = conn.execute("SELECT id FROM caisse_orders").fetchall()
                    delete_ids = [str(r["id"]) for r in all_rows if str(r["id"]) not in protected]

                    deleted_tx = deleted_items = deleted_orders = 0
                    if delete_ids:
                        has_tx = conn.execute(
                            """SELECT 1 FROM information_schema.tables
                               WHERE table_schema='public' AND table_name='caisse_payment_transactions'"""
                        ).fetchone()
                        if has_tx:
                            row = conn.execute(
                                "SELECT COUNT(*) AS n FROM caisse_payment_transactions WHERE order_id = ANY(%s)",
                                (delete_ids,),
                            ).fetchone()
                            deleted_tx = int(row["n"] or 0)
                            conn.execute(
                                "DELETE FROM caisse_payment_transactions WHERE order_id = ANY(%s)",
                                (delete_ids,),
                            )

                        row = conn.execute(
                            "SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id = ANY(%s)",
                            (delete_ids,),
                        ).fetchone()
                        deleted_items = int(row["n"] or 0)
                        conn.execute("DELETE FROM caisse_order_items WHERE order_id = ANY(%s)", (delete_ids,))

                        row = conn.execute(
                            "SELECT COUNT(*) AS n FROM caisse_orders WHERE id = ANY(%s)",
                            (delete_ids,),
                        ).fetchone()
                        deleted_orders = int(row["n"] or 0)
                        conn.execute("DELETE FROM caisse_orders WHERE id = ANY(%s)", (delete_ids,))

                    after = _preview(conn)

            return jsonify({
                "ok": True,
                "message": "Nettoyage sélectif terminé",
                "before": before,
                "deleted": {
                    "orders": deleted_orders,
                    "items": deleted_items,
                    "payment_transactions": deleted_tx,
                },
                "after": after,
                "notifications_preserved": True,
            })
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Nettoyage sélectif impossible",
                "detail": str(exc),
            }), 500
