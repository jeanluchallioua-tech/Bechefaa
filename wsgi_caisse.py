"""Point d'entrée WSGI dédié à BÉCHÉFAA-Caisse.

Cette branche démarre exclusivement le nouveau backend clean_caisse.
Aucun import de l'ancien app.py / Wix / V1.
"""
from clean_caisse.app import app, db, ensure_order_schema, order_payload
from clean_caisse.kitchen_checklist import register_kitchen_checklist
from clean_caisse.history_modifier import register_history_modifier
from clean_caisse.customer_phase1 import register_customer_phase1
from clean_caisse.delivery_zones import register_delivery_zones
from clean_caisse.pos_quick_add import register_pos_quick_add
from clean_caisse.pos_touch_layout import register_pos_touch_layout
from clean_caisse.printing_phase1 import register_printing_phase1
from clean_caisse.history_print_buttons import register_history_print_buttons
from clean_caisse.phase1_audit_guard import register_phase1_audit_guard
from clean_caisse.history_add_product import register_history_add_product
from clean_caisse.printing_timestamp import register_printing_timestamp
from clean_caisse.product_admin_phase2 import register_product_admin_phase2
from clean_caisse.product_options_admin_phase2 import register_product_options_admin_phase2
from clean_caisse.options_diagnostic_phase2 import register_options_diagnostic_phase2
from clean_caisse.option_price_admin_phase23 import register_option_price_admin_phase23
from clean_caisse.option_add_test_phase23 import register_option_add_test_phase23
from clean_caisse.option_rules_test_phase23 import register_option_rules_test_phase23

register_kitchen_checklist(app, db, ensure_order_schema, order_payload)
register_history_modifier(app, db, ensure_order_schema, order_payload)
# Enregistrer l'ergonomie avant le module Client : les after_request Flask
# s'exécutent en ordre inverse, donc la fiche Client existe avant sa transformation en fenêtre.
register_pos_touch_layout(app, db)
register_customer_phase1(app, db, ensure_order_schema)
register_delivery_zones(app, db)
register_pos_quick_add(app)
register_printing_phase1(app, db, ensure_order_schema, order_payload)
register_history_print_buttons(app)
register_phase1_audit_guard(app, db, ensure_order_schema, order_payload)
register_history_add_product(app)
register_printing_timestamp(app, db)
register_product_admin_phase2(app, db)
register_product_options_admin_phase2(app, db)
register_options_diagnostic_phase2(app, db)
register_option_price_admin_phase23(app, db)
register_option_add_test_phase23(app, db)
register_option_rules_test_phase23(app, db)
