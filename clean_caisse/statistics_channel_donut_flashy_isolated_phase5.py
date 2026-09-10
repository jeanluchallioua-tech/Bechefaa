"""Phase 5 — activation isolée du camembert des canaux de vente.

Le point d'entrée WSGI appelle déjà cette fonction. On délègue désormais
uniquement au module d'injection tardive validé, afin que le remplacement
s'effectue après la construction complète du DOM côté navigateur.
Aucune écriture métier, aucun paiement, aucun Z.
"""

from clean_caisse.statistics_channel_donut_late_isolated_phase5 import (
    register_statistics_channel_donut_late_isolated_phase5,
)


def register_statistics_channel_donut_flashy_isolated_phase5(app):
    register_statistics_channel_donut_late_isolated_phase5(app)
