# BÉCHÉFAA WSGI bootstrap
# Garantit l'exécution des migrations/patchs avant le chargement de l'application.
import sitecustomize  # noqa: F401
from app import app
