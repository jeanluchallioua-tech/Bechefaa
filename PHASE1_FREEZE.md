# BÉCHÉFAA-Caisse — Phase 1 figée

Date de gel : 2026-09-07
Branche applicative : `bechefaa-caisse-clean`
Point de restauration dédié : `restore-phase1-2026-09-07`

## Périmètre validé Phase 1

- Catalogue lu depuis PostgreSQL `catalog_admin_v2`.
- Caisse tactile avec modes Salle, Emporter et Livraison.
- Ajout rapide au panier pour les produits sans options.
- Sélection des options et suppléments pour les produits concernés.
- Enregistrement des commandes dans `caisse_orders` et `caisse_order_items`.
- Envoi cuisine et écran cuisine avec À préparer / En préparation / Terminée.
- Checklist cuisine persistante en PostgreSQL.
- Historique consultable et modifiable, y compris après une commande Terminée.
- Modification de quantité, retrait de ligne et ajout d'un nouveau plat avec ses options depuis l'historique.
- Clients PostgreSQL : recherche, sélection, création, coordonnées et association à la commande.
- Fenêtre client tactile : fermeture automatique après sélection ou enregistrement.
- Zones de livraison A/B/C administrables avec minimum de commande et villes/codes postaux.
- Ticket client 80 mm et ticket cuisine 80 mm disponibles au moment de la commande et depuis l'historique.
- Date et heure de commande sur les tickets 80 mm.
- Epson TM-m30 : impression navigateur 80 mm ; l'écran cuisine reste le fonctionnement principal et le ticket cuisine le secours manuel.

## Architecture figée

- Entrée WSGI : `wsgi_caisse.py`
- Backend propre : `clean_caisse/`
- PostgreSQL comme stockage des commandes et clients.
- Aucun import de l'ancien `app.py` dans le WSGI propre.
- Aucun flux Wix / V1 / localStorage dans les modules de la nouvelle caisse.

## Corrections apportées pendant l'audit final

1. La troisième colonne Cuisine « Terminée » utilisait une API qui ne renvoyait pas les commandes terminées. Une API de tableau cuisine complète a été ajoutée.
2. L'historique permettait uniquement de modifier les quantités ou retirer une ligne. L'ajout d'un plat avec options a été ajouté.
3. `schema.sql` n'était plus parfaitement synchronisé avec le schéma utilisé par le code. Il a été remis à jour, y compris les zones de livraison.
4. Les tickets 80 mm ne montraient pas encore la date et l'heure de la commande. Elles ont été ajoutées.

## Limites volontairement reportées après Phase 1

- La règle de zone/minimum de livraison existe mais n'est pas encore bloquante dans le flux de commande POS ni reliée au futur site.
- L'impression Epson est actuellement basée sur l'impression navigateur/système ; une impression réseau directe ePOS pourra être ajoutée si nécessaire.
- Les contrôles de prix restent adaptés à un POS interne ; une validation serveur renforcée des prix catalogue pourra être ajoutée lors de l'administration produits.
- Les évolutions de schéma futures devront utiliser une vraie stratégie de migrations au lieu de dépendre uniquement de `CREATE TABLE IF NOT EXISTS`.

## Règle de reprise

Toute Phase 2 doit partir du point figé Phase 1. En cas de régression, revenir au point de restauration `restore-phase1-2026-09-07` avant toute autre correction.
