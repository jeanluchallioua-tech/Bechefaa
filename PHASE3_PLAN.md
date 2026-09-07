# BÉCHÉFAA POS — PHASE 3

Base de départ figée : Phase 2 commit `e8809c939f7d85ae9bcab709f6e7d5de5e1c0d8d`.

Branche de développement : `phase3-orders-tickets-xz`.

## Objectifs validés

1. Notifications de nouvelles commandes selon le canal
   - Site internet
   - Uber Eats
   - Deliveroo
   - Couleur de texte distincte par canal
   - Notification sonore à l'arrivée d'une nouvelle commande

2. Bloc commande
   - Afficher clairement les quantités de chaque article
   - Conserver le canal/source visible

3. Cuisine et tickets
   - Lister toutes les options choisies pour chaque article
   - Afficher les catégories en rouge et en gras
   - Afficher les coordonnées client en gras
   - Afficher le nombre de pièces en gras

4. Totaux et TVA
   - Afficher HT et TTC sur commande et ticket
   - TVA restauration configurée à 10 % pour cette phase
   - Calculer HT à partir du TTC avec la taxe de 10 %, sans modifier le prix TTC catalogue

5. Clôtures de caisse
   - X de caisse en cours de journée : lecture intermédiaire sans remise à zéro
   - Z de caisse fin de journée : clôture définitive de la journée
   - Tracer date/heure et totaux de chaque édition/clôture
   - Ne jamais altérer l'historique des commandes

## Règle de développement

La Phase 2 reste gelée. Toute évolution Phase 3 doit être faite uniquement sur la branche `phase3-orders-tickets-xz`, par petits modules testés séparément avant intégration.
