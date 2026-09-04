# BÉCHÉFAA-Caisse — socle propre

Cette application est une reconstruction indépendante de l'ancienne caisse.

## Principes non négociables

- PostgreSQL est la seule source métier persistante.
- `catalog_admin_v2` est conservé en lecture pour le catalogue central existant.
- Les nouvelles données de caisse utilisent uniquement des tables `caisse_*`.
- Aucun `localStorage` pour commandes ou clients.
- Aucun `WIX_GROUP_IDS`, `EXACT`, catalogue embarqué, ancien `app.js` ou patch Python de démarrage.
- Aucun accès aux anciennes tables `orders` / `clients` pendant la reconstruction.
- Wix, Uber Eats, Deliveroo et le site seront des canaux, jamais des sources d'autorité du catalogue.

## Première phase

1. Vérifier la connexion PostgreSQL.
2. Lire `catalog_admin_v2` en lecture seule.
3. Créer les tables isolées `caisse_clients`, `caisse_orders`, `caisse_order_items`.
4. Construire ensuite la nouvelle interface caisse et cuisine autour de ces API.

Le fichier `schema.sql` contient uniquement les nouvelles tables. Il n'est pas exécuté automatiquement au démarrage.
