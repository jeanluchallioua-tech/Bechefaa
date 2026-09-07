"""Point d'entrée WSGI dédié à BÉCHÉFAA-Caisse.

Cette branche démarre exclusivement le nouveau backend clean_caisse.
Aucun import de l'ancien app.py / Wix / V1.
"""
from clean_caisse.app import app, db, ensure_order_schema, order_payload
from clean_caisse.kitchen_checklist import register_kitchen_checklist
from clean_caisse.history_modifier import register_history_modifier

register_kitchen_checklist(app, db, ensure_order_schema, order_payload)
register_history_modifier(app, db, ensure_order_schema, order_payload)
