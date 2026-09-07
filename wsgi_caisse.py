"""Point d'entrée WSGI dédié à BÉCHÉFAA-Caisse.

Cette branche démarre exclusivement le nouveau backend clean_caisse.
Aucun import de l'ancien app.py / Wix / V1.
"""
from clean_caisse.app import app
