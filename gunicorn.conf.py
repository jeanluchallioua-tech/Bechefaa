# BÉCHÉFAA — chargement forcé des correctifs au démarrage Gunicorn
# Clever Cloud n'importe pas toujours sitecustomize.py automatiquement.

try:
    import sitecustomize  # noqa: F401
    print("BÉCHÉFAA: correctifs catalogue central chargés via gunicorn.conf.py")
except Exception as exc:
    print("BÉCHÉFAA: erreur chargement sitecustomize:", exc)

try:
    import startup_patch  # noqa: F401
    print("BÉCHÉFAA: correctif V0.5.43 options/photos chargé via gunicorn.conf.py")
except Exception as exc:
    print("BÉCHÉFAA: erreur chargement startup_patch:", exc)
