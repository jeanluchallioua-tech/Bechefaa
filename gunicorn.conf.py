# BÉCHÉFAA — chargement forcé des correctifs au démarrage Gunicorn
# Clever Cloud n'importe pas toujours sitecustomize.py automatiquement.

try:
    import sitecustomize  # noqa: F401
    print("BÉCHÉFAA: correctifs de démarrage chargés via gunicorn.conf.py")
except Exception as exc:
    print("BÉCHÉFAA: erreur chargement correctifs de démarrage:", exc)
