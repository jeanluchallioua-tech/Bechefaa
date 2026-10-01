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
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Response, jsonify, request

TZ = ZoneInfo("Europe/Paris")
HEBCAL_GEONAME_ID = "2988507"  # Paris
DEFAULT_HEBREW_YEAR = 5787
FRENCH_WEEKDAYS = ("lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche")
FRENCH_MONTHS = ("janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre")

def _fr_date(dt):
    local = dt.astimezone(TZ)
    return f"{FRENCH_WEEKDAYS[local.weekday()]} {local.day} {FRENCH_MONTHS[local.month-1]} {local.year}"



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

    def _floor_half_hour(dt):
        local = dt.astimezone(TZ).replace(second=0, microsecond=0)
        minute = 30 if local.minute >= 30 else 0
        return local.replace(minute=minute)

    def _pre_shabbat_closure(start_dt):
        # Règle BÉCHÉFAA :
        # 1) calcul religieux = entrée - 2h30, arrondi à la demi-heure inférieure ;
        # 2) ne jamais dépasser la fermeture habituelle du dernier service avant l'entrée ;
        # 3) dernière commande = 30 min avant la fermeture retenue.
        local_start = start_dt.astimezone(TZ)
        special_close = _floor_half_hour(local_start - timedelta(hours=2, minutes=30))

        cfg = _site_hours_config() or {}
        days = cfg.get("days") or {}
        day_keys = ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
        day_cfg = days.get(day_keys[local_start.weekday()]) or {}
        normal_close = None

        event_minutes = local_start.hour * 60 + local_start.minute
        for pair in (day_cfg.get("slots") or []):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                sh, sm = map(int, str(pair[0]).split(":"))
                eh, em = map(int, str(pair[1]).split(":"))
            except Exception:
                continue
            start_minutes = sh * 60 + sm
            end_minutes = eh * 60 + em
            if start_minutes < event_minutes and end_minutes <= event_minutes:
                candidate = local_start.replace(hour=eh, minute=em, second=0, microsecond=0)
                if normal_close is None or candidate > normal_close:
                    normal_close = candidate

        close_dt = special_close
        if normal_close is not None and normal_close < close_dt:
            close_dt = normal_close

        last_order_dt = close_dt - timedelta(minutes=30)
        return {
            "restaurant_closes": close_dt.strftime("%H:%M"),
            "last_order": last_order_dt.strftime("%H:%M"),
            "cutoff_minutes": 30,
            "holiday_entry": local_start.strftime("%H:%M"),
            "normal_close": normal_close.strftime("%H:%M") if normal_close else None,
            "special_close": special_close.strftime("%H:%M"),
            "rule": "EARLIEST_OF_NORMAL_OR_ENTRY_MINUS_2H30",
        }

    def _service_rule_preview(event_row):
        starts_at = event_row.get("starts_at")
        category = str(event_row.get("category") or "")
        if category != "candles" or not starts_at:
            return None
        preview = _pre_shabbat_closure(starts_at)
        preview["explanation"] = (
            f"Entrée à {preview['holiday_entry']} : fermeture calculée à "
            f"{preview['restaurant_closes']}, dernière commande à {preview['last_order']}."
        )
        return preview

    def _fold_text(value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower()

    def _simplify_holiday_title(title):
        raw = str(title or "").strip()
        low = raw.lower()
        if "pesach" in low or "pessa" in low or "pessah" in low:
            # Hebcal distingue plusieurs jours; pour l'exploitation on garde
            # uniquement les deux blocs de fermeture de Pessa'h.
            if any(token in low for token in ("vii", "viii", "7", "8", "seventh", "eighth")):
                return "Pessa’h 2"
            return "Pessa’h 1"
        return raw

    def _ceil_quarter(dt):
        local = dt.astimezone(TZ).replace(second=0, microsecond=0)
        remainder = local.minute % 15
        if remainder:
            local += timedelta(minutes=15 - remainder)
        return local

    def _shabbat_reopening(exit_dt):
        # Règle BÉCHÉFAA : sortie + 30 min, arrondie au quart d'heure supérieur.
        opening = _ceil_quarter(exit_dt + timedelta(minutes=30))
        ordering = opening + timedelta(minutes=15)
        service_end = opening.replace(hour=23, minute=0, second=0, microsecond=0)
        if service_end <= opening:
            service_end = opening + timedelta(hours=2, minutes=45)
        return {
            "opening_at": opening.isoformat(),
            "opening_date": _fr_date(opening),
            "opening_time": opening.strftime("%H:%M"),
            "ordering_at": ordering.isoformat(),
            "ordering_date": _fr_date(ordering),
            "ordering_time": ordering.strftime("%H:%M"),
            "service_end_at": service_end.isoformat(),
            "service_end_time": service_end.strftime("%H:%M"),
        }

    def _next_order_resume(after_dt):
        cfg = _site_hours_config() or {}
        days = cfg.get("days") or {}
        day_keys = ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
        local = after_dt.astimezone(TZ)
        for offset in range(0, 8):
            candidate_date = local.date() + timedelta(days=offset)
            day_key = day_keys[candidate_date.weekday()]
            day_cfg = days.get(day_key) or {}
            if not day_cfg.get("enabled"):
                continue
            slots = day_cfg.get("slots") or []
            for pair in slots:
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    continue
                try:
                    hh, mm = map(int, str(pair[0]).split(":"))
                    candidate = datetime(
                        candidate_date.year, candidate_date.month, candidate_date.day,
                        hh, mm, tzinfo=TZ
                    )
                except Exception:
                    continue
                if candidate > local:
                    return {
                        "at": candidate.isoformat(),
                        "date": _fr_date(candidate),
                        "time": candidate.strftime("%H:%M"),
                    }
        return None

    def _operational_periods(events):
        """Transforme les événements Hebcal en périodes lisibles pour le restaurant."""
        rows = [dict(x) for x in events]
        rows.sort(key=lambda x: x.get("starts_at") or datetime.max.replace(tzinfo=TZ))

        hidden_titles = (
            "Rosh Chodesh", "Roch H", "Hanukkah", "Chanukah", "Hanoucca", "H̲anoucca",
            "Yom HaAliyah", "Yom Ha’Alyah", "Yom Ha'Aliyah", "Yom ha’Alyah", "Yom ha'Aliyah",
            "Selichot", "Selihot", "Seli'hot", "Selihoth"
        )
        candles = [x for x in rows if str(x.get("category") or "") == "candles" and x.get("starts_at")]
        havdalahs = [x for x in rows if str(x.get("category") or "") == "havdalah" and x.get("starts_at")]
        holidays = [
            x for x in rows
            if str(x.get("category") or "") == "holiday"
            and x.get("starts_at")
            and not any(_fold_text(h) in _fold_text(x.get("title") or "") for h in hidden_titles)
            and not any(token in _fold_text(x.get("title") or "") for token in ("hanoukah","hanukkah","chanukah","hanoucca"))
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
                    title = _simplify_holiday_title(h.get("title"))
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
            if not preview:
                preview = _pre_shabbat_closure(start)
            shabbat_reopen = _shabbat_reopening(end) if not is_holiday else None
            resume = shabbat_reopen or _next_order_resume(end)
            periods.append({
                "type": "holiday" if is_holiday else "shabbat",
                "name": name,
                "entry_at": start.isoformat(),
                "exit_at": end.isoformat(),
                "entry_date": _fr_date(start),
                "entry_time": start.astimezone(TZ).strftime("%H:%M"),
                "exit_date": _fr_date(end),
                "exit_time": end.astimezone(TZ).strftime("%H:%M"),
                "closure_time": preview.get("restaurant_closes") if preview else None,
                "last_order": preview.get("last_order") if preview else None,
                "resume_at": (resume.get("ordering_at") if shabbat_reopen else resume.get("at")) if resume else None,
                "resume_date": (resume.get("ordering_date") if shabbat_reopen else resume.get("date")) if resume else None,
                "resume_time": (resume.get("ordering_time") if shabbat_reopen else resume.get("time")) if resume else None,
                "restaurant_reopen_date": shabbat_reopen.get("opening_date") if shabbat_reopen else None,
                "restaurant_reopen_time": shabbat_reopen.get("opening_time") if shabbat_reopen else None,
                "service_end_time": shabbat_reopen.get("service_end_time") if shabbat_reopen else None,
                "deliveroo_rule": "Fermé chaque Chabbat" if not is_holiday else "Fermeture exceptionnelle",
                "uber_rule": "Fermé chaque Chabbat" if not is_holiday else "Fermeture exceptionnelle",
            })
            if end_index is not None:
                used_havdalah.add(end_index)
            covered_until = end

        today = datetime.now(TZ).date()
        periods = [
            p for p in periods
            if datetime.fromisoformat(p["exit_at"]).astimezone(TZ).date() >= today
        ]
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
<style>*{box-sizing:border-box}body{margin:0;background:#f3f8ff;font-family:Arial;color:#0b1f3a}.top{background:#0038b8;color:#fff;padding:16px 22px;border-bottom:4px solid #fff;box-shadow:0 3px 14px #0038b822}.w{max-width:1500px;margin:28px auto;padding:18px}.box{background:#fff;border:1px solid #d6e5ff;border-radius:16px;padding:22px;margin-bottom:18px;box-shadow:0 6px 22px #0038b812}button,input{min-height:44px;border-radius:9px;border:1px solid #8db5ff;padding:8px}button{background:#0038b8;color:#fff;font-weight:800;cursor:pointer}button:hover{background:#0057d9}.row{padding:9px 0;border-bottom:1px solid #eee}.muted{color:#4c6693}.planning-head,.planning-row{display:grid;grid-template-columns:1.45fr 1fr 1fr;gap:18px;align-items:stretch}.planning-head{font-weight:900;background:#0038b8;color:#fff;border-radius:10px;padding:12px 14px;margin-bottom:8px}.planning-row{padding:0;border-bottom:10px solid #f3f8ff;border-radius:14px;overflow:hidden;box-shadow:0 3px 12px #0038b810}.planning-cell{padding:18px 20px;min-height:130px}.planning-cell:nth-child(1){background:#eaf3ff;border-left:5px solid #0038b8}.planning-cell:nth-child(2){background:#ffffff;border-left:5px solid #6ea8ff}.planning-cell:nth-child(3){background:#edf5ff;border-left:5px solid #00a3ff}.planning-title{font-size:21px;font-weight:900;margin-bottom:8px;color:#0038b8}.type-badge{display:inline-block;margin-bottom:8px;padding:5px 9px;border-radius:999px;color:#fff;font-size:12px;font-weight:900;letter-spacing:.4px}.type-badge.shabbat{background:#0038b8}.type-badge.holiday{background:#d97706}.time-big{font-size:30px;font-weight:900;line-height:1.05;color:#0038b8}.time-sub{margin-top:5px;font-size:14px;font-weight:800;color:#4c6693}.date-line{font-size:15px;line-height:1.45}.badge{display:inline-block;margin-top:8px;margin-right:6px;padding:5px 8px;border-radius:999px;background:#dceaff;color:#0038b8;font-size:12px;font-weight:800}@media(max-width:900px){.planning-head{display:none}.planning-row{grid-template-columns:1fr}.planning-cell{padding:8px 0}.planning-cell:before{display:block;font-weight:900;margin-bottom:4px}.planning-cell:nth-child(1):before{content:'Chabbat / fête'}.planning-cell:nth-child(2):before{content:'Fermeture BÉCHÉFAA'}.planning-cell:nth-child(3):before{content:'Reprise des commandes'}}</style></head>
<body><div class="top"><b>BÉCHÉFAA • Calendrier religieux & fermetures</b></div><div class="w">
<div class="box"><h1>Calendrier hébraïque</h1><p class="muted">Paris • diaspora • import Hebcal. L'import ne ferme jamais automatiquement le restaurant.</p>
<label>Année hébraïque <input id="year" type="number" value="5787"></label>
<button onclick="imp()">Importer / actualiser Hebcal</button> <button onclick="load()">Afficher</button><div id="msg"></div></div>
<div class="box"><h2>Planning des fermetures</h2><p class="muted">Uniquement Chabbat et fêtes entraînant une fermeture.</p><div class="planning-head"><div>Chabbat / fêtes</div><div>Fermeture BÉCHÉFAA</div><div>Reprise des commandes</div></div><div id="periods"></div></div>
<div class="box"><h2>Fermetures validées</h2><div id="closures"></div></div>
</div><script>
const $=id=>document.getElementById(id);
async function load(){let y=$('year').value;let r=await fetch('/api/admin/religious-calendar?hebrew_year='+encodeURIComponent(y),{cache:'no-store'}),d=await r.json();$('periods').innerHTML=(d.periods||[]).map(x=>{let type=x.type==='shabbat'?'CHABBAT':'FÊTE';let typeClass=x.type==='shabbat'?'shabbat':'holiday';let close=(x.closure_time&&x.last_order)?('<div class="time-big">'+x.closure_time+'</div><div class="time-sub">Fermeture BÉCHÉFAA</div><div style="margin-top:14px"><div class="time-big" style="font-size:24px">'+x.last_order+'</div><div class="time-sub">Dernière commande</div></div>'):'Selon horaires enregistrés';let resume=(x.resume_date&&x.resume_time)?((x.restaurant_reopen_time?('<div class="time-big">'+x.restaurant_reopen_time+'</div><div class="time-sub">Réouverture restaurant</div><div style="margin-top:14px">'):'')+'<div class="time-big" style="font-size:24px">'+x.resume_time+'</div><div class="time-sub">Reprise des commandes</div>'+(x.restaurant_reopen_time?'</div>':'')+(x.service_end_time?('<div style="margin-top:14px"><b>Fin service :</b> '+x.service_end_time+'</div>'):'')):'À définir';return '<div class="planning-row"><div class="planning-cell"><span class="type-badge '+typeClass+'">'+type+'</span><div class="planning-title">'+x.name+'</div><div class="date-line"><b>Entrée :</b> '+x.entry_date+' à <b>'+x.entry_time+'</b></div><div class="date-line"><b>Sortie :</b> '+x.exit_date+' à <b>'+x.exit_time+'</b></div><span class="badge">Deliveroo : '+x.deliveroo_rule+'</span></div><div class="planning-cell">'+close+'</div><div class="planning-cell">'+resume+'</div></div>'}).join('')||'Aucune période à afficher.';$('closures').innerHTML=(d.closures||[]).map(x=>'<div class="row"><b>'+x.name+'</b><br>'+x.starts_at+' → '+x.ends_at+'<br><span class="muted">Site '+x.site_enabled+' • Deliveroo '+x.deliveroo_enabled+' • actif '+x.active+'</span></div>').join('')||'Aucune fermeture validée.'}
async function imp(){$('msg').textContent='Import…';let r=await fetch('/api/admin/religious-calendar/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hebrew_year:Number($('year').value)})}),d=await r.json();$('msg').textContent=d.ok?('Importé : '+d.events_imported+' événements'):'Erreur : '+d.error;if(d.ok)load()}load();
</script></body></html>""", content_type="text/html; charset=utf-8")

