"""Phase 4.4 — comptage espèces de fermeture, test isolé.

Calcule le tiroir théorique à partir du fond initial réellement enregistré et
des paiements espèces réussis du jour. Le montant compté reste une simulation :
rien n'est enregistré et le Z n'est pas modifié.
"""
from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from flask import Response

PARIS = ZoneInfo("Europe/Paris")


def _eur(value):
    return f"{Decimal(str(value or 0)):.2f} €".replace(".", ",")


def register_cash_count_test_phase44(app, db):
    @app.get("/maintenance/phase44/cash-count-test")
    def cash_count_test_phase44():
        now = datetime.now(PARIS)
        day = now.strftime("%Y-%m-%d")
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        try:
            with db() as conn:
                opening = conn.execute(
                    "SELECT opening_amount FROM caisse_cash_float_openings WHERE business_date=%s",
                    (day,),
                ).fetchone()
                if not opening:
                    return Response("Aucun fond de caisse enregistré aujourd'hui.", status=409, mimetype="text/plain")
                row = conn.execute("""
                    SELECT COALESCE(SUM(t.amount),0) AS cash_sales, COUNT(*) AS cash_payments
                    FROM caisse_payment_transactions t
                    WHERE t.transaction_type='PAYMENT'
                      AND t.status='SUCCEEDED'
                      AND UPPER(t.method) IN ('ESPÈCES','ESPECES')
                      AND t.created_at >= %s AND t.created_at <= %s
                """, (start_ms, end_ms)).fetchone()
            opening_amount = Decimal(str(opening["opening_amount"] or 0))
            cash_sales = Decimal(str(row["cash_sales"] or 0))
            theoretical = opening_amount + cash_sales
            html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Comptage fermeture</title><style>
body{{font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c;padding:22px}}.box{{max-width:650px;margin:auto;background:#fff;border-radius:15px;padding:24px}}.note{{background:#eef6ff;border:1px solid #bfdbfe;border-radius:9px;padding:12px;margin:15px 0}}.row{{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:12px 0}}.total{{font-size:20px;font-weight:800}}label{{display:block;font-weight:800;margin:20px 0 7px}}input{{width:100%;box-sizing:border-box;font-size:25px;padding:12px;border:1px solid #cbd5e1;border-radius:9px}}.result{{margin-top:15px;padding:14px;border-radius:9px;background:#f8fafc;font-weight:800}}.muted{{color:#64748b}}
</style></head><body><div class="box"><h1>Comptage de fermeture</h1><p class="muted">{escape(now.strftime("%d/%m/%Y %H:%M"))} · test en lecture seule</p><div class="note">Le montant compté ci-dessous n'est pas enregistré. Aucun Z n'est déclenché.</div><div class="row"><span>Fond initial</span><strong>{_eur(opening_amount)}</strong></div><div class="row"><span>Ventes espèces ({int(row['cash_payments'])})</span><strong>+ {_eur(cash_sales)}</strong></div><div class="row total"><span>Tiroir théorique</span><strong>{_eur(theoretical)}</strong></div><label for="counted">Espèces réellement comptées (€)</label><input id="counted" type="number" min="0" step="0.01" placeholder="0.00"><div id="result" class="result">Saisissez le montant réellement présent dans le tiroir.</div></div><script>
const theoretical={float(theoretical):.2f},input=document.getElementById('counted'),result=document.getElementById('result');input.oninput=()=>{{if(input.value===''){{result.textContent='Saisissez le montant réellement présent dans le tiroir.';return}}const counted=Number(input.value),gap=Math.round((counted-theoretical)*100)/100;let text='Écart : '+(gap>=0?'+ ':'')+gap.toFixed(2)+' €';if(Math.abs(gap)<0.005)text+=' — caisse juste';else if(gap>0)text+=' — excédent';else text+=' — manque';result.textContent=text}};
</script></body></html>'''
            return Response(html, content_type="text/html; charset=utf-8")
        except Exception as exc:
            return Response("Comptage de fermeture indisponible : " + escape(str(exc)), status=500, mimetype="text/plain")
