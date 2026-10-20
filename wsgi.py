# BÉCHÉFAA WSGI bootstrap
# Garantit l'exécution des migrations/patchs avant le chargement de l'application.
import sitecustomize  # noqa: F401
from app import app
from catalog_api_v2 import catalog_v2

# Refonte isolée : API V2 disponible uniquement sur la branche de test.
if "catalog_v2" not in app.blueprints:
    app.register_blueprint(catalog_v2)
