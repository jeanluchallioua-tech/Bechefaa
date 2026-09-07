# BÉCHÉFAA POS — AUDIT TECHNIQUE AVANT PHASE 3

Base auditée : Phase 2 figée au commit `e8809c939f7d85ae9bcab709f6e7d5de5e1c0d8d` et branche de travail `phase3-orders-tickets-xz`.

## État général

- Le runtime Clever est bien isolé par `wsgi_caisse.py` et démarre `clean_caisse.app` uniquement.
- Aucun import de l'ancien `app.py`, Wix ou V1 dans le point d'entrée actif.
- PostgreSQL est la source des commandes, clients et du catalogue V2.
- Le contrôle serveur des prix Phase 2.6 est actif sur la création des commandes.
- Le contrôle serveur des zones/minimums de livraison Phase 2.7 est actif sur la création des commandes.
- La branche Phase 3 part exactement de la Phase 2 figée ; la seule évolution initiale est la documentation du plan Phase 3.

## Points critiques à corriger avant les fonctions X/Z

### 1. Modification d'une commande existante non protégée par le verrou de prix

`PUT /api/orders/<order_id>` accepte les `unit_price`, `name`, `options` et `options_text` reçus du navigateur. Le garde Phase 2.6 protège seulement `POST /api/orders`.

Risque : un appel direct à l'API peut modifier le prix ou le contenu d'une commande sans revalidation par `catalog_admin_v2`.

Action Phase 3 préalable : réutiliser la validation canonique du catalogue sur les modifications de commandes.

### 2. Commandes terminées encore modifiables

L'historique autorise explicitement la modification d'une commande `Terminée`, puis la repasse en `À préparer`.

Ce comportement était volontaire pour la Phase 1, mais il est incompatible avec une future clôture Z fiable si une commande déjà incluse dans un Z peut ensuite être modifiée.

Action Phase 3 préalable : introduire un état de clôture. Une commande incluse dans un Z doit devenir immuable ; les corrections ultérieures devront être tracées séparément.

### 3. Absence de contrôle d'accès des routes administration/API

Les routes d'administration produits, options, catégories, clients, livraison et modifications de commandes ne possèdent pas de contrôle d'authentification dans le runtime actuel.

Risque : si l'application est accessible publiquement, une personne connaissant les URLs peut lire ou modifier des données d'administration.

Action recommandée : ajouter une authentification et des rôles avant l'ouverture réelle en production.

### 4. Plusieurs modules modifient le HTML avec `after_request` et remplacent `window.fetch`

Le POS est enrichi par plusieurs injections HTML/JavaScript et plusieurs wrappers de `window.fetch`. L'ordre d'enregistrement des modules est donc important.

Risque : conflit ou régression quand les notifications Phase 3 seront ajoutées.

Action Phase 3 : ne pas ajouter une nouvelle chaîne de patchs. Créer un module Phase 3 centralisé pour l'interface commandes/notifications/tickets, puis réduire progressivement les injections superposées.

## Points importants mais non bloquants

### 5. Ticket type incomplet dans le noyau

La fonction centrale `ticket_type()` distingue essentiellement Livraison et Comptoir. Salle/Emporter sont corrigés par le module d'ergonomie. Pour la Phase 3, la source doit devenir une donnée canonique claire : `SALLE`, `EMPORTER`, `LIVRAISON`, `SITE`, `UBER_EATS`, `DELIVEROO`.

### 6. Nom du produit non recalculé côté serveur

Lors de la création, le prix est bien contrôlé par `product_id`, mais le champ `name` reste celui reçu du navigateur.

Action recommandée : lors d'une création/modification, reprendre aussi le nom canonique du produit depuis le catalogue.

### 7. Schéma fiscal absent

Les commandes stockent actuellement surtout `total`. Pour HT/TTC/TVA et X/Z, il faut figer sur chaque commande au moment de la vente :

- taux de TVA,
- total TTC,
- total HT,
- montant de TVA,
- date/heure fiscale,
- état de clôture Z éventuel.

Ne pas recalculer un ancien ticket à partir d'une règle fiscale actuelle.

### 8. Numérotation commandes

La numérotation utilise `MAX(num)+1` sous verrou exclusif de `caisse_orders`. C'est cohérent et protège les doublons, mais bloque brièvement toute la table pendant une création. Pour le volume actuel BÉCHÉFAA, ce n'est pas bloquant.

### 9. Écriture du catalogue JSON

Certaines opérations d'administration verrouillent correctement la ligne catalogue ; d'autres anciennes fonctions Phase 2 réécrivent le JSON complet sans verrou explicite. Avec deux administrateurs simultanés, une modification concurrente pourrait théoriquement écraser une autre modification.

Action recommandée avant multi-utilisateur intensif : uniformiser toutes les écritures catalogue sous transaction + `FOR UPDATE`.

### 10. Recherche code postal

La recherche ville utilise `geo.api.gouv.fr` avec timeout. Une panne de ce service n'empêche pas PostgreSQL de fonctionner et la saisie manuelle reste possible. Aucun blocage structurel identifié.

## Validation des protections déjà en place

- Prix : contrôle serveur du produit et des options avant `POST /api/orders`.
- Livraison : contrôle serveur de la ville active et du minimum de zone avant insertion.
- Données : commandes et clients PostgreSQL.
- Impression : tickets générés depuis les données PostgreSQL de la commande.
- Cuisine : statuts et cases de préparation persistés PostgreSQL.
- Phase 2 : branches de restauration séparées et intactes.

## Ordre recommandé pour démarrer la Phase 3

1. Sécuriser l'intégrité des modifications de commandes et préparer le verrou de clôture Z.
2. Normaliser les sources de commande (Caisse/Site/Uber Eats/Deliveroo).
3. Ajouter notifications couleur + son.
4. Améliorer bloc commande, quantités et options cuisine/tickets.
5. Ajouter HT/TTC/TVA figés par commande.
6. Ajouter X puis Z et verrouillage des commandes clôturées.
7. Audit final Phase 3 + nouveau point de restauration.

Aucune correction de runtime n'est incluse dans ce document. La Phase 2 reste intacte.
