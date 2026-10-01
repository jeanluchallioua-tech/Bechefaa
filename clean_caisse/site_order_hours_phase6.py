"""Phase 6 — horaires de prise de commande SITE BÉCHÉFAA."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Response, jsonify, request

TZ=ZoneInfo("Europe/Paris")
DAYS=("monday","tuesday","wednesday","thursday","friday","saturday","sunday")
LABELS={"monday":"Lundi","tuesday":"Mardi","wednesday":"Mercredi","thursday":"Jeudi","friday":"Vendredi","saturday":"Samedi","sunday":"Dimanche"}
DEFAULT_CONFIG={"timezone":"Europe/Paris","cutoff_minutes":30,"days":{
"monday":{"enabled":True,"slots":[["11:30","15:30"],["18:30","22:30"]]},
"tuesday":{"enabled":True,"slots":[["11:30","15:30"],["18:30","22:30"]]},
"wednesday":{"enabled":True,"slots":[["11:30","15:30"],["18:30","22:30"]]},
"thursday":{"enabled":True,"slots":[["11:30","15:30"],["18:30","22:30"]]},
"friday":{"enabled":True,"slots":[["11:30","15:30"]]},
"saturday":{"enabled":False,"slots":[]},
"sunday":{"enabled":True,"slots":[["11:30","16:00"],["18:30","22:30"]]}}}
ORDER_PATHS={"/api/public/orders","/api/public/orders/mollie-phase6","/api/public/orders/edenred-uat-phase6","/api/public/orders/edenred-prod-phase6"}

def _mins(hm):
    h,m=map(int,hm.split(":")); return h*60+m

def _norm(src):
    src=src or {}; cutoff=int(src.get("cutoff_minutes",30))
    if not 0<=cutoff<=180: raise ValueError("Délai invalide.")
    out={"timezone":"Europe/Paris","cutoff_minutes":cutoff,"days":{}}
    sd=src.get("days") or {}
    for day in DAYS:
        raw=sd.get(day) or {}; enabled=bool(raw.get("enabled",False)); slots=[]
        for pair in (raw.get("slots") or [])[:2]:
            if len(pair)<2: continue
            a,b=str(pair[0]),str(pair[1])
            if len(a)!=5 or len(b)!=5 or _mins(b)<=_mins(a): raise ValueError(f"{LABELS[day]} : plage invalide.")
            slots.append([a,b])
        if enabled and not slots: raise ValueError(f"{LABELS[day]} : ajoutez une plage.")
        out["days"][day]={"enabled":enabled,"slots":slots if enabled else []}
    return out

def register_site_order_hours_phase6(app,db):
    def ensure(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_site_order_hours(
        id SMALLINT PRIMARY KEY DEFAULT 1 CHECK(id=1),config_json JSONB NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.execute("INSERT INTO caisse_site_order_hours(id,config_json) VALUES(1,%s::jsonb) ON CONFLICT(id) DO NOTHING",(json.dumps(DEFAULT_CONFIG,ensure_ascii=False),))
    def read():
        with db() as conn:
            with conn.transaction():
                ensure(conn); r=conn.execute("SELECT config_json FROM caisse_site_order_hours WHERE id=1").fetchone()
                return r["config_json"] if isinstance(r["config_json"],dict) else json.loads(r["config_json"])
    def state(cfg=None, now=None):
        cfg=cfg or read()
        now=(now or datetime.now(TZ)).astimezone(TZ)
        day=DAYS[now.weekday()]
        cur=now.hour*60+now.minute
        d=cfg["days"].get(day,{"enabled":False,"slots":[]})
        cutoff=int(cfg.get("cutoff_minutes",30))

        # 1) Base hebdomadaire : horaires habituels du restaurant.
        open_now=False
        next_close=None
        if d.get("enabled"):
            for a,b in d.get("slots",[]):
                start_min,end_min=_mins(a),_mins(b)-cutoff
                if start_min<=cur<end_min:
                    open_now=True
                    next_close=b
                    break

        next_open_day=None
        next_open_time=None
        next_open_label=None
        if not open_now:
            for offset in range(0,8):
                idx=(now.weekday()+offset)%7
                candidate_day=DAYS[idx]
                candidate=cfg["days"].get(candidate_day,{"enabled":False,"slots":[]})
                if not candidate.get("enabled"):
                    continue
                starts=sorted([a for a,b in candidate.get("slots",[])],key=_mins)
                for a in starts:
                    if offset==0 and _mins(a)<=cur:
                        continue
                    next_open_day=candidate_day
                    next_open_time=a
                    if offset==0:
                        next_open_label="Aujourd’hui à "+a
                    elif offset==1:
                        next_open_label="Demain à "+a
                    else:
                        next_open_label=LABELS[candidate_day]+" à "+a
                    break
                if next_open_time:
                    break

        # 2) Calendrier fêtes & Chabbat : exception datée prioritaire.
        calendar_fn=app.config.get("BECHEFAA_SITE_ORDER_CALENDAR_OVERRIDE")
        calendar_override=calendar_fn(now) if callable(calendar_fn) else None
        if calendar_override:
            mode=calendar_override.get("mode")
            if mode=="closed":
                open_now=False
                next_close=None
                if calendar_override.get("resume_time"):
                    next_open_time=calendar_override.get("resume_time")
                    resume_date=calendar_override.get("resume_date")
                    next_open_label=(resume_date+" à "+next_open_time) if resume_date else next_open_time
            elif mode=="open":
                open_now=True
                next_close=calendar_override.get("service_end_time")
                next_open_day=None
                next_open_time=None
                next_open_label=None

        # 3) Fermeture exceptionnelle manuelle : priorité absolue.
        closure_fn=app.config.get("BECHEFAA_ACTIVE_SITE_CLOSURE")
        closure=closure_fn(now) if callable(closure_fn) else None
        if closure:
            open_now=False
            next_close=None

        return {
            "open":open_now,
            "exceptional_closure":closure,
            "calendar_override":calendar_override,
            "day":day,
            "day_label":LABELS[day],
            "now":now.strftime("%H:%M"),
            "cutoff_minutes":cutoff,
            "closing_time":next_close,
            "next_open_day":next_open_day,
            "next_open_time":next_open_time,
            "next_open_label":next_open_label,
        }
    @app.get("/api/public/order-hours")
    def public_hours():
        cfg=read(); return jsonify({"ok":True,"config":cfg,"state":state(cfg)})
    @app.get("/api/admin/order-hours")
    def admin_hours_get():
        cfg=read(); return jsonify({"ok":True,"config":cfg,"state":state(cfg)})
    @app.post("/api/admin/order-hours/simulate")
    def admin_hours_simulate():
        body=request.get_json(silent=True) or {}
        raw=str(body.get("datetime") or "").strip()
        if not raw:
            return jsonify({"ok":False,"error":"Date/heure manquante."}),400
        try:
            sim=datetime.fromisoformat(raw.replace("Z","+00:00"))
            if sim.tzinfo is None:
                sim=sim.replace(tzinfo=TZ)
            sim=sim.astimezone(TZ)
        except Exception:
            return jsonify({"ok":False,"error":"Date/heure invalide."}),400
        cfg=read()
        return jsonify({"ok":True,"simulated_at":sim.isoformat(),"state":state(cfg,sim)})

    @app.post("/api/admin/order-hours")
    def admin_hours_post():
        try: cfg=_norm((request.get_json(silent=True) or {}).get("config") or request.get_json(silent=True) or {})
        except Exception as exc: return jsonify({"ok":False,"error":str(exc)}),400
        with db() as conn:
            with conn.transaction():
                ensure(conn); conn.execute("UPDATE caisse_site_order_hours SET config_json=%s::jsonb,updated_at=NOW() WHERE id=1",(json.dumps(cfg,ensure_ascii=False),))
        return jsonify({"ok":True,"config":cfg,"state":state(cfg)})
    @app.before_request
    def guard_site_hours():
        if request.method!="POST" or request.path not in ORDER_PATHS: return None
        st=state()
        if st["open"]: return None
        return jsonify({"ok":False,"error":"Les commandes en ligne sont actuellement fermées.","code":"SITE_ORDERING_CLOSED","state":st}),409
    @app.get("/administration/horaires-commandes")
    def order_hours_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Horaires habituels</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#111827}.top{background:#111827;color:white;padding:15px 22px;display:flex;gap:12px;align-items:center}.top a{margin-left:auto;color:white;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:800}.wrap{max-width:980px;margin:28px auto;padding:18px}.box{background:white;border-radius:16px;padding:22px;box-shadow:0 5px 20px #0001;margin-bottom:18px}.sim{border:2px solid #d7deea}.sim-grid{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.sim-result{margin-top:14px;padding:14px;border-radius:10px;background:#f6f8fb;font-weight:800}.sim-result.open{background:#ecfdf3;color:#166534}.sim-result.closed{background:#fff1f2;color:#9f1239}.day{display:grid;grid-template-columns:120px 90px 1fr 1fr;gap:10px;align-items:center;padding:12px 0;border-bottom:1px solid #eee}.slot{display:flex;gap:6px;align-items:center}input[type=time],input[type=number],input[type=datetime-local]{min-height:42px;border:1px solid #ccd2da;border-radius:8px;padding:7px}.save{margin-top:18px;width:100%;min-height:48px;border:0;border-radius:10px;background:#111827;color:white;font-weight:900}.muted{color:#667085}.status{margin-top:12px;font-weight:800}@media(max-width:760px){.day{grid-template-columns:1fr}.slot{flex-wrap:wrap}}</style></head><body><header class="top"><b>BÉCHÉFAA • Horaires habituels</b><a href="/administration">Administration</a></header><main class="wrap"><div class="box"><h1>Horaires habituels du restaurant</h1><p class="muted">Définissez les horaires normaux de service. Le calendrier Fêtes & Chabbat peut les raccourcir ou créer une ouverture exceptionnelle. Le site bloque les commandes selon le délai ci-dessous.</p><label><b>Arrêt des commandes avant fermeture :</b> <input id="cutoff" type="number" min="0" max="180" value="30"> minutes</label><div id="days"></div><button class="save" onclick="save()">Enregistrer</button><div id="msg" class="status"></div></div><div class="box sim"><h2>Simulateur horaires</h2><p class="muted">Choisissez une date et une heure fictives. Le simulateur ne modifie aucun horaire réel.</p><div class="sim-grid"><label><b>Date et heure</b><br><input id="simdt" type="datetime-local"></label><button onclick="simulate()">Tester</button></div><div id="simres" class="sim-result">Aucun test lancé.</div></div></main><script>
const names={monday:'Lundi',tuesday:'Mardi',wednesday:'Mercredi',thursday:'Jeudi',friday:'Vendredi',saturday:'Samedi',sunday:'Dimanche'},order=Object.keys(names),$=x=>document.getElementById(x);let cfg=null;
function draw(){days.innerHTML=order.map(d=>{let x=cfg.days[d]||{enabled:false,slots:[]},s=[...(x.slots||[])];while(s.length<2)s.push(['','']);return '<div class="day" data-day="'+d+'"><b>'+names[d]+'</b><label><input class="en" type="checkbox" '+(x.enabled?'checked':'')+'> Ouvert</label><div class="slot"><input class="a1" type="time" value="'+s[0][0]+'"> à <input class="b1" type="time" value="'+s[0][1]+'"></div><div class="slot"><input class="a2" type="time" value="'+s[1][0]+'"> à <input class="b2" type="time" value="'+s[1][1]+'"></div></div>'}).join('');cutoff.value=cfg.cutoff_minutes}
async function load(){let r=await fetch('/api/admin/order-hours',{cache:'no-store'}),d=await r.json();cfg=d.config;draw()}
async function save(){let daysCfg={};document.querySelectorAll('.day').forEach(row=>{let slots=[];for(let i=1;i<=2;i++){let a=row.querySelector('.a'+i).value,b=row.querySelector('.b'+i).value;if(a&&b)slots.push([a,b])}daysCfg[row.dataset.day]={enabled:row.querySelector('.en').checked,slots}});let body={config:{cutoff_minutes:Number(cutoff.value||30),days:daysCfg}};msg.textContent='Enregistrement…';let r=await fetch('/api/admin/order-hours',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();msg.textContent=d.ok?'Horaires enregistrés.':('Erreur : '+d.error);if(d.ok){cfg=d.config;draw()}}
async function simulate(){let v=$('simdt').value,res=$('simres');if(!v){res.className='sim-result closed';res.textContent='Choisissez une date et une heure.';return}res.className='sim-result';res.textContent='Test en cours…';let r=await fetch('/api/admin/order-hours/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({datetime:v})}),d=await r.json();if(!d.ok){res.className='sim-result closed';res.textContent='Erreur : '+d.error;return}let s=d.state||{},o=s.calendar_override||{},status=s.open?'OUVERT AUX COMMANDES':'FERMÉ AUX COMMANDES';let details=[];details.push(s.day_label+' '+v.replace('T',' '));if(o&&o.source==='RELIGIOUS_CALENDAR'){details.push('Règle calendrier : '+(o.name||o.type||'Fêtes & Chabbat'));if(o.last_order)details.push('Dernière commande : '+o.last_order);if(o.restaurant_closes)details.push('Fermeture restaurant : '+o.restaurant_closes);if(o.resume_time)details.push('Reprise commandes : '+o.resume_time);if(o.service_end_time)details.push('Fin service : '+o.service_end_time)}else{details.push('Règle : horaires habituels')}if(s.exceptional_closure)details.push('Fermeture manuelle active : '+s.exceptional_closure.name);res.className='sim-result '+(s.open?'open':'closed');res.innerHTML='<div style="font-size:20px">'+status+'</div><div style="margin-top:6px">'+details.join(' • ')+'</div>'}
let n=new Date(),pad=x=>String(x).padStart(2,'0');$('simdt').value=n.getFullYear()+'-'+pad(n.getMonth()+1)+'-'+pad(n.getDate())+'T'+pad(n.getHours())+':'+pad(n.getMinutes());load();
</script></body></html>''',content_type="text/html; charset=utf-8")
