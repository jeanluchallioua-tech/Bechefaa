"""Phase 4.4 — traçabilité utilisateurs BÉCHÉFAA.
Couche isolée : ne modifie ni les droits ni le module PIN existant.
"""
import time, uuid
from flask import jsonify, request

COOKIE='bechefaa_security_phase44'

def register_user_audit_phase44(app,db):
 def ensure(conn):
  conn.execute("""CREATE TABLE IF NOT EXISTS caisse_user_audit(
   id TEXT PRIMARY KEY,user_key TEXT NOT NULL DEFAULT '',user_label TEXT NOT NULL DEFAULT '',
   action TEXT NOT NULL,path TEXT NOT NULL,status_code INTEGER NOT NULL,created_at BIGINT NOT NULL)""")
  conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_user_audit_created ON caisse_user_audit(created_at DESC)")
 def user(conn):
  token=request.cookies.get(COOKIE,'')
  if not token:return None
  now=int(time.time()*1000)
  try:return conn.execute("SELECT s.user_key,u.label FROM caisse_security_sessions s JOIN caisse_security_users u ON u.user_key=s.user_key WHERE s.token=%s AND s.expires_at>%s",(token,now)).fetchone()
  except Exception:return None
 def action_for(path):
  if path.endswith('/cancel-phase44'):return 'ANNULATION COMMANDE'
  if path.endswith('/refund-phase44'):return 'REMBOURSEMENT'
  if path=='/api/hardware/config-phase44':return 'MODIFICATION MATÉRIEL'
  if path=='/api/restaurant/settings-phase44':return 'MODIFICATION RESTAURANT'
  if path=='/api/caisse/cash-float-phase44':return 'FOND DE CAISSE'
  if path=='/api/caisse/cash-count-phase44':return 'COMPTAGE CAISSE'
  return ''
 @app.after_request
 def audit_after(response):
  if request.method!='POST':return response
  action=action_for(request.path)
  if not action:return response
  try:
   with db() as conn:
    with conn.transaction():
     ensure(conn); u=user(conn)
     conn.execute("INSERT INTO caisse_user_audit(id,user_key,user_label,action,path,status_code,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",('audit_'+uuid.uuid4().hex,(u['user_key'] if u else ''),(u['label'] if u else 'Non identifié'),action,request.path,response.status_code,int(time.time()*1000)))
  except Exception:pass
  return response
 @app.get('/api/security/audit-phase44')
 def audit_list():
  try:
   with db() as conn:
    with conn.transaction():
     ensure(conn); u=user(conn)
     if not u:return jsonify({'ok':False,'error':'Authentification PIN requise'}),403
     rows=conn.execute("SELECT user_label,action,status_code,created_at FROM caisse_user_audit ORDER BY created_at DESC LIMIT 200").fetchall()
   return jsonify({'ok':True,'user':{'key':u['user_key'],'label':u['label']},'events':[dict(r) for r in rows]})
  except Exception as exc:return jsonify({'ok':False,'error':'Journal indisponible','detail':str(exc)}),500
