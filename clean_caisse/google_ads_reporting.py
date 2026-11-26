"""Read-only Google Ads v26 reporting; secrets supplied via environment."""
import json
import os
import re
from urllib.request import Request, urlopen
from urllib.parse import urlencode

REQUIRED = ("GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_CAMPAIGN_ID",
            "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
            "GOOGLE_ADS_PURCHASE_ACTION_ID")

def _post(url, data, headers):
    with urlopen(Request(url, data=data, headers=headers, method="POST"), timeout=8) as response:
        return json.load(response)

def summarize(cost, purchases, value):
    return {"Dépenses": cost, "Conversions attribuées": purchases,
            "Valeur des conversions": value,
            "Coût par acquisition": cost / purchases if purchases else None,
            "Panier moyen attribué": value / purchases if purchases else None,
            "ROAS": value / cost if cost else None}

def report():
    cfg = {key: os.environ.get(key, "").strip() for key in REQUIRED}
    if not all(cfg.values()):
        return "Configuration OAuth et campagne incomplète", None
    customer = cfg["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
    campaign = cfg["GOOGLE_ADS_CAMPAIGN_ID"]
    action = cfg["GOOGLE_ADS_PURCHASE_ACTION_ID"]
    manager = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "").strip()
    if not re.fullmatch(r"[0-9]{10}", customer) or not re.fullmatch(r"[0-9]+", campaign) or not re.fullmatch(r"[0-9]+", action) or (manager and not re.fullmatch(r"[0-9]{10}", manager)):
        return "Identifiants Google Ads invalides", None
    try:
        token = _post("https://oauth2.googleapis.com/token", urlencode({
            "client_id": cfg["GOOGLE_ADS_CLIENT_ID"], "client_secret": cfg["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": cfg["GOOGLE_ADS_REFRESH_TOKEN"], "grant_type": "refresh_token"
        }).encode(), {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        if manager:
            headers["login-customer-id"] = manager
        endpoint = "https://googleads.googleapis.com/v26/customers/" + customer + "/googleAds:searchStream"
        def query(q):
            batches = _post(endpoint, json.dumps({"query": q}).encode(), headers)
            return [row for batch in batches for row in batch.get("results", [])]
        customers = query("SELECT customer.currency_code FROM customer LIMIT 1")
        if not customers or customers[0]["customer"]["currencyCode"] != "EUR":
            return "Devise du compte non confirmée en EUR", None
        campaigns = query("SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.status != 'REMOVED'")
        available = [str(row["campaign"]["id"]) for row in campaigns]
        if campaign not in available:
            if len(available) == 1:
                campaign = available[0]
            else:
                return "Campagne non identifiée — sélectionner un ID de campagne valide", None
        actions = query("SELECT conversion_action.id, conversion_action.category, conversion_action.status, conversion_action.resource_name FROM conversion_action")
        matches = [row["conversionAction"] for row in actions if str(row["conversionAction"]["id"]) == action and row["conversionAction"].get("category") == "PURCHASE" and row["conversionAction"].get("status") != "REMOVED"]
        if len(matches) != 1:
            return "Action de conversion Achat non confirmée — vérifier son identifiant", None
        resource = matches[0]["resourceName"]
        if not re.fullmatch(r"customers/[0-9]+/conversionActions/[0-9]+", resource):
            return "Référence de conversion invalide", None
        where = " WHERE campaign.id = " + campaign + " AND segments.date DURING LAST_14_DAYS"
        costs = query("SELECT campaign.id, metrics.cost_micros FROM campaign" + where)
        rows = query("SELECT campaign.id, segments.conversion_action, metrics.conversions, metrics.conversions_value FROM campaign" + where +
                     " AND segments.conversion_action = '" + resource + "'")
        cost = sum(int(row.get("metrics", {}).get("costMicros", 0)) for row in costs) / 1000000
        count = sum(float(row.get("metrics", {}).get("conversions", 0)) for row in rows)
        value = sum(float(row.get("metrics", {}).get("conversionsValue", 0)) for row in rows)
        if not costs:
            return "Aucune donnée de campagne disponible sur la période", None
        return "Connectée — 14 derniers jours complets", summarize(cost, count, value)
    except Exception:
        return "Lecture Google Ads impossible — vérifier les autorisations et identifiants", None
