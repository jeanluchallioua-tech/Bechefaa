"""Read-only site receipts; independent of advertising consent."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from .google_ads_reporting import date_filter

PARIS = ZoneInfo("Europe/Paris")

def period_bounds(period, start=None, end=None, today=None):
    date_filter(period, start, end)
    today = today or datetime.now(PARIS).date()
    if period == "CUSTOM":
        return date.fromisoformat(start), date.fromisoformat(end)
    if period == "TODAY":
        return today, today
    n = {"YESTERDAY": 1, "LAST_7_DAYS": 7, "LAST_14_DAYS": 14, "LAST_30_DAYS": 30}[period]
    return today-timedelta(days=n), today-timedelta(days=1)

def site_sales(db, period, start=None, end=None):
    first, last = period_bounds(period, start, end)
    a = int(datetime.combine(first, time.min, PARIS).timestamp()*1000)
    b = int(datetime.combine(last+timedelta(days=1), time.min, PARIS).timestamp()*1000)
    with db() as conn:
        rows = conn.execute("""
            SELECT (to_timestamp(t.created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date AS day,
                   t.order_id,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.transaction_type='PAYMENT'),0) AS paid,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.transaction_type='REFUND'),0) AS refunded
            FROM caisse_payment_transactions t
            JOIN caisse_orders o ON o.id=t.order_id
            WHERE UPPER(TRIM(COALESCE(o.sales_channel,'')))='SITE'
              AND t.status='SUCCEEDED'
              AND UPPER(COALESCE(t.provider,'')) NOT LIKE '%%TEST%%'
              AND UPPER(COALESCE(t.method,'')) NOT LIKE '%%TEST%%'
              AND t.created_at >= %s AND t.created_at < %s
            GROUP BY 1,2
            ORDER BY 1
        """, (a,b)).fetchall()
    daily = {(first+timedelta(days=i)).isoformat():0.0 for i in range((last-first).days+1)}
    paid = refunded = 0.0
    orders = set()
    for row in rows:
        p, r = float(row["paid"]), float(row["refunded"])
        paid += p
        refunded += r
        if p > 0:
            orders.add(row["order_id"])
        daily[str(row["day"])] += p-r
    return {"count":len(orders), "paid":paid, "refunds":refunded, "net":paid-refunded,
            "average":paid/len(orders) if orders else None,
            "days":[{"date":day,"net":value} for day,value in daily.items()]}
