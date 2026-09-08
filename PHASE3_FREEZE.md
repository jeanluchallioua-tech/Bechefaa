# BÉCHÉFAA — PHASE 3 FIGÉE

Date : 2026-09-08
Branche de développement : `phase3-orders-tickets-xz`

## Périmètre figé

La Phase 3 couvre le cycle de commande et de clôture de caisse :

- création et modification sécurisées des commandes ;
- validation serveur des produits, options et prix ;
- quantités tactiles et persistance PostgreSQL ;
- snapshot fiscal HT / TVA 10 % / TTC ;
- Cuisine : À préparer / En préparation / Terminée ;
- notifications sonores ;
- modes Salle / À emporter / Livraison ;
- 9 tables Salle ;
- Historique et réimpression des tickets ;
- ticket client et ticket cuisine ;
- X de caisse en lecture seule ;
- Z définitif, unique par journée ;
- verrouillage des commandes après Z ;
- blocage des nouvelles commandes après Z ;
- remise à zéro logique de Cuisine après Z sans suppression PostgreSQL ;
- archives Z consultables et imprimables ;
- fuseau métier explicite `Europe/Paris`.

## Z réel de validation

Le 08/09/2026, un Z réel a été effectué avec succès :

- 33 commandes ;
- Total HT : 1 070,94 € ;
- TVA 10 % : 107,06 € ;
- Total TTC : 1 178,00 €.

Après clôture :

- Cuisine vide : validé ;
- Historique conservé : validé ;
- bouton de nouvelle clôture masqué : validé ;
- archive Z conservée : validé.

## Audit de fin de phase

Voir `PHASE3_CODE_AUDIT.md`.

L'audit final a corrigé :

1. le verrou Z pour les IDs texte `caisse-<uuid>` ;
2. le fuseau X/Z/verrouillage sur `Europe/Paris` ;
3. l'initialisation du schéma Z avant la première lecture Cuisine sur une base neuve.

## Règle de conservation

Cette version est une référence stable. Les développements de Phase 4 doivent partir d'une nouvelle branche et ne doivent pas modifier les branches de sauvegarde Phase 3.

## Phase 4 — élément comptable déjà retenu

Le rapport comptable mensuel devra produire un PDF avec CA HT/TVA/TTC ventilé Sur place / À emporter / Livraison, récapitulatif des Z journaliers, courbe du CA quotidien basée sur les Z, moyens de paiement, téléchargement/impression et envoi par e-mail au comptable.
