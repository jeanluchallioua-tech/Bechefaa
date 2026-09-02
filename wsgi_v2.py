"""WSGI entrypoint for the isolated Catalogue V2 test environment.

This deliberately leaves the production app.py untouched. Clever Cloud test
must use CC_PYTHON_MODULE=wsgi_v2:app.
"""
from app import app
from catalog_api_v2 import catalog_v2

# Register the V2 API only once on this isolated WSGI entrypoint.
if catalog_v2.name not in app.blueprints:
    app.register_blueprint(catalog_v2)
