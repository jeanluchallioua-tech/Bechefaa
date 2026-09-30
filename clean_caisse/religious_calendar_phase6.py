"""Calendrier religieux et fermetures exceptionnelles BÉCHÉFAA — Phase 6.

- Import Hebcal par année hébraïque (Paris / diaspora)
- Conservation des événements sources pour contrôle humain
- Fermetures exceptionnelles validées séparément
- Drapeaux prêts pour Site / Deliveroo / Uber Eats

Aucune fermeture n'est activée automatiquement lors d'un import Hebcal.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Response, jsonify, request

TZ = ZoneInfo("Europe/Paris")
HEBCAL_GEONAME_ID = "2988507"  # Paris
DEFAULT_HEBREW_YEAR = 5787


def register_religious_calendar_phase6(app, db):
    def ensure_tables(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_hebrew_calendar_events(
            event_key TEXT PRIMARY KEY,
            hebrew_year INTEGER NOT NULL,
            title TEXT,
            hebrew_title TEXT,
            category TEXT,
            subcat TEXT,
            starts_at TIMESTAMPTZ,
            raw_json JSONB NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_exceptional_closures(
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL DEFAULT 'MANUAL',
            hebrew_year INTEGER,
            site_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            deliveroo_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            uber_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_exceptional_closures_window
            ON caisse_exceptional_closures(active, starts_at, ends_at)""")

    def fetch_hebcal(year):
        params = {
            "v": "1",
            "cfg": "json",
            "year": str(int(year)),
            "yt": "H",
            "i": "off",          # diaspora
            "maj": "on",        # fêtes majeures
            "min": "on",        # fêtes mineures
            "mf": "on",         # jeûnes mineurs
            "mod": "on",        # fêtes modernes
            "nx": "on",         # Roch Hodech
            "c": "on",          # allumage des bougies
            "M": "on",          # havdalah / tombée de la nuit
            "geo": "geoname",
            "geonameid": HEBCAL_GEONAME_ID,
            "lg": "fr",
        }
        url = "https://www.hebcal.com/hebcal?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Bechefaa-Religious-Calendar/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def parse_dt(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if "T" in text:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            # Les fêtes Hebcal peuvent être renvoyées comme simple date YYYY-MM-DD.
            # On les positionne à midi local pour préserver correctement le jour civil.
            return datetime.fromisoformat(text).replace(hour=12, tzinfo=TZ)
        except Exception:
            return None

    def import_year(year):
        data = fetch_hebcal(year)
        items = data.get("items") if isinstance(data, dict) else []
        items = items if isinstance(items, list) else []
        kept = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "")
            if category not in {"holiday", "candles", "havdalah"}:
                continue
            starts_at = parse_dt(item.get("date"))
            key_src = "|".join([
                str(year),
                category,
                str(item.get("title") or ""),
                str(item.get("date") or ""),
                str(idx),
            ])
            # Stable enough across a re-import while avoiding extra dependencies.
            import hashlib
            event_key = hashlib.sha1(key_src.encode("utf-8")).hexdigest()
            kept.append((event_key, item, starts_at))

        with db() as conn:
            with conn.transaction():
                ensure_tables(conn)
                for event_key, item, starts_at in kept:
                    conn.execute("""INSERT INTO caisse_hebrew_calendar_events
                        (event_key,hebrew_year,title,hebrew_title,category,subcat,starts_at,raw_json,imported_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NOW())
                        ON CONFLICT(event_key) DO UPDATE SET
                            title=EXCLUDED.title,
                            hebrew_title=EXCLUDED.hebrew_title,
                            category=EXCLUDED.category,
                            subcat=EXCLUDED.subcat,
                            starts_at=EXCLUDED.starts_at,
                            raw_json=EXCLUDED.raw_json,
                            imported_at=NOW()
                    """, (
                        event_key,
                        int(year),
                        str(item.get("title") or ""),
                        str(item.get("hebrew") or ""),
                        str(item.get("category") or ""),
                        str(item.get("subcat") or ""),
                        starts_at,
                        json.dumps(item, ensure_ascii=False),
                    ))
        return len(kept), data.get("location") if isinstance(data, dict) else None, len(items)

    def _site_hours_config():
        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT config_json FROM caisse_site_order_hours WHERE id=1"
                ).fetchone()
            if not row:
                return None
            raw = row["config_json"]
            return raw if isinstance(raw, dict) else json.loads(raw)
        except Exception:
            return None

    def _service_rule_preview(event_row):
        starts_at = event_row.get("starts_at")
        category = str(event_row.get("category") or "")
        if category != "candles" or not starts_at:
            return None

        local_start = starts_at.astimezone(TZ)
        cfg = _site_hours_config() or {}
        day_keys = ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
        day_key = day_keys[local_start.weekday()]
        day_cfg = (cfg.get("days") or {}).get(day_key) or {}
        slots = day_cfg.get("slots") or []
        cutoff = int(cfg.get("cutoff_minutes", 30) or 30)

        if len(slots) >= 2:
            lunch_end = str(slots[0][1])
            evening_start = str(slots[1][0])
            evening_end = str(slots[1][1])
            try:
                eh, em = map(int, evening_end.split(":"))
                event_minutes = local_start.hour * 60 + local_start.minute
                evening_end_minutes = eh * 60 + em
                if event_minutes <= evening_end_minutes:
                    close_dt = local_start.replace(
                        hour=int(lunch_end[:2]), minute=int(lunch_end[3:5]),
                        second=0, microsecond=0
                    )
                    last_order_dt = close_dt - timedelta(minutes=cutoff)
                    return {
                        "rule": "SUPPRESS_EVENING_SERVICE",
                        "holiday_entry": local_start.strftime("%H:%M"),
                        "usual_evening_service": f"{evening_start}–{evening_end}",
                        "restaurant_closes": close_dt.strftime("%H:%M"),
                        "last_order": last_order_dt.strftime("%H:%M"),
                        "cutoff_minutes": cutoff,
                        "explanation": (
                            f"Entrée de fête à {local_start.strftime('%H:%M')} : "
                            f"service du soir supprimé. Fermeture à {close_dt.strftime('%H:%M')}, "
                            f"dernière commande à {last_order_dt.strftime('%H:%M')}."
                        ),
                    }
            except Exception:
                return None
        return None

    def _operational_periods(events):
        """Transforme les événements Hebcal en périodes lisibles pour le restaurant."""
        rows = [dict(x) for x in events]
        rows.sort(key=lambda x: x.get("starts_at") or datetime.max.replace(tzinfo=TZ))

        hidden_titles = ("Rosh Chodesh", "Roch H", "Hanukkah", "Chanukah", "Hanoucca", "H̲anoucca")
        candles = [x for x in rows if str(x.get("category") or "") == "candles" and x.get("starts_at")]
        havdalahs = [x for x in rows if str(x.get("category") or "") == "havdalah" and x.get("starts_at")]
        holidays = [
            x for x in rows
            if str(x.get("category") or "") == "holiday"
            and x.get("starts_at")
            and not any(h.lower() in str(x.get("title") or "").lower() for h in hidden_titles)
        ]

        periods = []
        used_havdalah = set()
        covered_until = None
        for candle in candles:
            start = candle["starts_at"]
            if covered_until and start <= covered_until:
                continue
            end = None
            end_index = None
            for idx, hv in enumerate(havdalahs):
                if idx in used_havdalah:
                    continue
                if hv["starts_at"] > start:
                    end = hv["starts_at"]
                    end_index = idx
                    break
            if not end:
                continue

            in_window = []
            for h in holidays:
                hs = h["starts_at"]
                # Fête datée pendant la période, ou le jour civil suivant l'entrée.
                if start.date() <= hs.astimezone(TZ).date() <= end.astimezone(TZ).date():
                    title = str(h.get("title") or "").strip()
                    if title and title not in in_window:
                        in_window.append(title)

            # Écarter les libellés de Hol Hamoed / Hoshana Rabba du titre opérationnel.
            significant = [
                t for t in in_window
                if "CH" not in t.upper()
                and "HOSHANA" not in t.upper()
                and "HOCHAN" not in t.upper()
                and "SUKKOT VII" not in t.upper()
                and "SOUKKOT VII" not in t.upper()
            ]
            is_holiday = bool(significant)
            if is_holiday:
                # Les deux jours diaspora consécutifs restent une seule fermeture.
                name = " / ".join(significant)
            else:
                name = "Chabbat"

            preview = _service_rule_preview(candle)
            periods.append({
                "type": "holiday" if is_holiday else "shabbat",
                "name": name,
                "entry_at": start.isoformat(),
                "exit_at": end.isoformat(),
                "entry_date": start.astimezone(TZ).strftime("%d/%m/%Y"),
                "entry_time": start.astimezone(TZ).strftime("%H:%M"),
                "exit_date": end.astimezone(TZ).strftime("%d/%m/%Y"),
                "exit_time": end.astimezone(TZ).strftime("%H:%M"),
                "closure_time": preview.get("restaurant_closes") if preview else None,
                "last_order": preview.get("last_order") if preview else None,
            })
            if end_index is not None:
                used_havdalah.add(end_index)
            covered_until = end

        return periods

    def active_site_closure(now=None):
        now = now or datetime.now(TZ)
        try:
            with db() as conn:
                ensure_tables(conn)
                row = conn.execute("""SELECT id,name,starts_at,ends_at,source,notes
                    FROM caisse_exceptional_closures
                    WHERE active=TRUE AND site_enabled=TRUE
                      AND starts_at <= %s AND ends_at > %s
                    ORDER BY starts_at ASC LIMIT 1
                """, (now, now)).fetchone()
                conn.commit()
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "starts_at": row["starts_at"].isoformat(),
                "ends_at": row["ends_at"].isoformat(),
                "source": row["source"],
                "notes": row["notes"],
            }
        except Exception:
            return None

    # Utilisable par le module d'horaires sans import circulaire.
    app.config["BECHEFAA_ACTIVE_SITE_CLOSURE"] = active_site_closure

    @app.get("/api/public/exceptional-closure")
    def public_exceptional_closure():
        closure = active_site_closure()
        return jsonify({"ok": True, "closed": bool(closure), "closure": closure})

    @app.get("/api/admin/religious-calendar")
    def religious_calendar_get():
        year = int(request.args.get("hebrew_year") or DEFAULT_HEBREW_YEAR)
        with db() as conn:
            with conn.transaction():
                ensure_tables(conn)
                events = conn.execute("""SELECT event_key,hebrew_year,title,hebrew_title,category,subcat,starts_at
                    FROM caisse_hebrew_calendar_events
                    WHERE hebrew_year=%s
                    ORDER BY starts_at NULLS LAST, title
                """, (year,)).fetchall()
                closures = conn.execute("""SELECT id,name,starts_at,ends_at,source,hebrew_year,
                    site_enabled,deliveroo_enabled,uber_enabled,active,notes
                    FROM caisse_exceptional_closures
                    WHERE hebrew_year=%s OR hebrew_year IS NULL
                    ORDER BY starts_at
                """, (year,)).fetchall()
        return jsonify({
            "ok": True,
            "timezone": "Europe/Paris",
            "location": "Paris, France",
            "hebrew_year": year,
            "periods": _operational_periods(events),
            "events": [{
                **dict(x),
                "starts_at": x["starts_at"].isoformat() if x.get("starts_at") else None,
                "service_rule_preview": _service_rule_preview(dict(x)),
            } for x in events],
            "closures": [{
                **dict(x),
                "starts_at": x["starts_at"].isoformat(),
                "ends_at": x["ends_at"].isoformat(),
            } for x in closures],
        })

    @app.post("/api/admin/religious-calendar/import")
    def religious_calendar_import():
        body = request.get_json(silent=True) or {}
        year = int(body.get("hebrew_year") or DEFAULT_HEBREW_YEAR)
        try:
            count, location, received = import_year(year)
            return jsonify({
                "ok": True,
                "hebrew_year": year,
                "events_received": received,
                "events_imported": count,
                "location": location,
                "message": "Événements Hebcal importés sans activer de fermeture automatiquement.",
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

    @app.post("/api/admin/exceptional-closures")
    def exceptional_closure_create():
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "").strip()
        try:
            starts_at = datetime.fromisoformat(str(body.get("starts_at") or "").replace("Z", "+00:00"))
            ends_at = datetime.fromisoformat(str(body.get("ends_at") or "").replace("Z", "+00:00"))
        except Exception:
            return jsonify({"ok": False, "error": "Dates de fermeture invalides."}), 400
        if not name or ends_at <= starts_at:
            return jsonify({"ok": False, "error": "Nom ou plage de fermeture invalide."}), 400

        with db() as conn:
            with conn.transaction():
                ensure_tables(conn)
                row = conn.execute("""INSERT INTO caisse_exceptional_closures
                    (name,starts_at,ends_at,source,hebrew_year,site_enabled,
                     deliveroo_enabled,uber_enabled,active,notes)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    name, starts_at, ends_at,
                    str(body.get("source") or "MANUAL"),
                    body.get("hebrew_year"),
                    bool(body.get("site_enabled", True)),
                    bool(body.get("deliveroo_enabled", True)),
                    bool(body.get("uber_enabled", True)),
                    bool(body.get("active", True)),
                    str(body.get("notes") or ""),
                )).fetchone()
        return jsonify({"ok": True, "id": row["id"]})

    @app.get("/administration/calendrier-religieux")
    def religious_calendar_page():
        return Response("""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Calendrier religieux</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#111827}.top{background:#111827;color:#fff;padding:16px 22px}.w{max-width:1100px;margin:28px auto;padding:18px}.box{background:#fff;border-radius:16px;padding:22px;margin-bottom:18px;box-shadow:0 5px 20px #0001}button,input{min-height:44px;border-radius:9px;border:1px solid #ccd2da;padding:8px}button{background:#111827;color:#fff;font-weight:800;cursor:pointer}.row{padding:9px 0;border-bottom:1px solid #eee}.muted{color:#667085}</style></head>
<body><div class="top"><b>BÉCHÉFAA • Calendrier religieux & fermetures</b></div><div class="w">
<div class="box"><h1>Calendrier hébraïque</h1><p class="muted">Paris • diaspora • import Hebcal. L'import ne ferme jamais automatiquement le restaurant.</p>
<label>Année hébraïque <input id="year" type="number" value="5787"></label>
<button onclick="imp()">Importer / actualiser Hebcal</button> <button onclick="load()">Afficher</button><div id="msg"></div></div>
<div class="box"><h2>Planning des fermetures</h2><p class="muted">Affichage simplifié : uniquement Chabbat et fêtes entraînant une fermeture. Roch Hodech et Hanoucca sont masqués.</p><div id="periods"></div></div>
<div class="box"><h2>Fermetures validées</h2><div id="closures"></div></div>
</div><script>
const $=id=>document.getElementById(id);
async function load(){let y=$('year').value;let r=await fetch('/api/admin/religious-calendar?hebrew_year='+encodeURIComponent(y),{cache:'no-store'}),d=await r.json();$('periods').innerHTML=(d.periods||[]).map(x=>{let close=(x.closure_time&&x.last_order)?('<div><b>Fermeture BÉCHÉFAA :</b> '+x.closure_time+' &nbsp; • &nbsp; <b>Dernière commande :</b> '+x.last_order+'</div>'):'';return '<div class="row"><div style="font-size:18px;font-weight:900">'+x.name+'</div><div><b>Entrée :</b> '+x.entry_date+' à '+x.entry_time+' &nbsp; • &nbsp; <b>Sortie :</b> '+x.exit_date+' à '+x.exit_time+'</div>'+close+'</div>'}).join('')||'Aucune période à afficher.';$('closures').innerHTML=(d.closures||[]).map(x=>'<div class="row"><b>'+x.name+'</b><br>'+x.starts_at+' → '+x.ends_at+'<br><span class="muted">Site '+x.site_enabled+' • Deliveroo '+x.deliveroo_enabled+' • actif '+x.active+'</span></div>').join('')||'Aucune fermeture validée.'}
async function imp(){$('msg').textContent='Import…';let r=await fetch('/api/admin/religious-calendar/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hebrew_year:Number($('year').value)})}),d=await r.json();$('msg').textContent=d.ok?('Importé : '+d.events_imported+' événements'):'Erreur : '+d.error;if(d.ok)load()}load();
</script></body></html>""", content_type="text/html; charset=utf-8")

