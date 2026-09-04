# Audit source unique commandes / clients — 2026-09-04

Branche : `audit-cleanup-orders-2026-09-04`

## Constat confirmé

Le POS possède encore deux sources concurrentes pour les commandes et les clients :

1. `static/app.js` initialise `orders` depuis `localStorage` (`b_orders043`) et `clients` depuis `localStorage` (`b_clients043`).
2. `static/cloud.js` recharge ensuite `/api/orders` et `/api/clients`, mais conserve encore des écritures locales.
3. La création d'une commande est d'abord visible dans le tableau JavaScript/local puis envoyée au serveur par un hook asynchrone.
4. Les modifications et cases cuisine appellent directement les routes PostgreSQL `/api/orders/<id>/...`.
5. Si une commande existe dans l'état navigateur mais n'est pas encore réellement présente dans la base serveur, une modification peut produire `order not found`.

## Source cible

PostgreSQL doit être l'unique source métier pour :

- commandes ;
- lignes de commande ;
- statuts cuisine ;
- modifications ;
- clients ;
- historique ;
- données utilisées pour les tickets.

Le navigateur peut conserver uniquement de l'état d'interface non métier (préférences, notification déjà vue, panier non validé si nécessaire), mais pas une copie faisant autorité des commandes ou clients.

## Migration prévue

### Étape 1 — lecture
- Ne plus initialiser commandes/clients depuis `localStorage`.
- Initialiser les collections en mémoire à vide.
- Hydrater uniquement depuis `/api/orders` et `/api/clients`.
- Supprimer les écritures locales de commandes/clients lors des refresh serveur.

### Étape 2 — création
- La validation d'une nouvelle commande doit d'abord effectuer le `POST /api/orders`.
- La commande n'est ajoutée à l'affichage qu'après succès serveur ou après relecture de `/api/orders`.
- Éliminer la fenêtre où une commande peut être visible localement mais absente de PostgreSQL.

### Étape 3 — modification
- Toute modification doit relire/identifier une commande provenant de PostgreSQL.
- `PATCH /api/orders/<id>/full` reste l'autorité pour les modifications complètes.
- Après succès, recharger la commande depuis PostgreSQL avant de rafraîchir cuisine/historique/tickets.

### Étape 4 — clients
- Même principe pour les clients : création serveur d'abord, puis refresh `/api/clients`.
- Suppression de `b_clients043` comme source métier.

## Garde-fous

- Aucun changement sur `main` pendant l'audit.
- Aucun changement sur la production stable avant test complet sur la branche.
- Ticket livraison déjà validé : conserver les champs client complets et ne pas régresser cette partie.
