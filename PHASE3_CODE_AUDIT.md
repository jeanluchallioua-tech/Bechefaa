# BÉCHÉFAA — Audit code Phase 3

Date : 2026-09-08
Branche auditée : `phase3-orders-tickets-xz`

## Périmètre vérifié

Le point d'entrée `wsgi_caisse.py` charge exclusivement `clean_caisse` pour le runtime de la caisse. Aucun import de l'ancien `app.py`, de Wix ou du runtime V1 n'est utilisé par ce point d'entrée.

Contrôles effectués sur les chaînes critiques Phase 3 : création/modification de commande, prix serveur, snapshot fiscal HT/TVA/TTC, quantités, Cuisine, Historique, tickets, tables Salle, notifications, X, Z, verrouillage après Z et remise à zéro logique de Cuisine.

## Anomalies trouvées et corrigées pendant l'audit

### 1. Verrouillage des commandes clôturées

Le garde Z recherchait uniquement des identifiants numériques dans les URL alors que les commandes utilisent des identifiants texte du type `caisse-<uuid>`. Une commande déjà associée à un Z pouvait donc ne pas être reconnue par ce garde lors de certaines mutations.

Correction : extraction d'identifiant compatible avec les IDs texte, sans conversion en entier. Les routes `/api/orders/<id>` et `/api/kitchen/orders/<id>/...` sont couvertes.

Commit correctif : `c43cecfd1f897f6f68f1e3b8dc23194c17c40bbd`.

### 2. Fuseau horaire X / Z / verrouillage de journée

Le serveur utilisait son fuseau local via `astimezone()`. Sur un hébergement cloud, ce fuseau ne doit pas définir la journée comptable du restaurant.

Correction : utilisation explicite de `Europe/Paris` pour X, Z, archive Z et contrôle de journée clôturée.

Commits : `219f676306e299ed3bd9de253486c1b9b235d979` et `375121ec3e3e43969e29a762210363bb8b3f7e7e`.

### 3. Cuisine sur une base neuve avant le premier Z

Le filtre Cuisine post-Z consultait `caisse_z_closures`. Sur une base fraîche où aucun écran Z n'avait encore créé cette table, la lecture Cuisine pouvait échouer.

Correction : création idempotente du schéma Z avant la lecture du tableau Cuisine.

Commit : `ec88f33314806e5c79001e3bbb051b19f0dcfbe3`.

## État fonctionnel validé

- PostgreSQL reste la source de vérité.
- Quantité `qty` enregistrée et propagée Caisse → Cuisine → tickets.
- Prix contrôlés côté serveur.
- Snapshot HT / TVA 10 % / TTC conservé avec fallback historique.
- Salle avec 9 tables, table visible Cuisine / Historique / tickets.
- Commandes terminées conservées dans l'Historique.
- X en lecture seule.
- Z unique par journée métier.
- Z réel testé : 33 commandes, 1 070,94 € HT, 107,06 € TVA, 1 178,00 € TTC.
- Après Z, Cuisine vide sans suppression des commandes historiques.
- Archives Z conservées et imprimables.
- Bouton de clôture masqué lorsque la journée est déjà clôturée.
- Nouvelle commande après Z bloquée côté serveur par code `DAY_Z_CLOSED`.
- Commandes associées à un Z verrouillées côté serveur par code `ORDER_Z_LOCKED`.

## Points de dette technique non bloquants

Le runtime comporte encore plusieurs `after_request` d'injection HTML et plusieurs `ALTER TABLE ... IF NOT EXISTS` déclenchés à la demande. Cela fonctionne et permet de préserver la stabilité des phases déjà validées, mais ce n'est pas l'architecture cible à long terme. Lors d'une future phase de consolidation, ces transformations devront être regroupées et les évolutions de schéma déplacées vers des migrations explicites.

Certains modules hérités de Phase 2 portent encore des noms `test` ou `diagnostic` tout en étant enregistrés dans `wsgi_caisse.py`. Ils ne font pas partie du flux fiscal Phase 3, mais devront être renommés ou isolés lors d'un nettoyage ultérieur pour réduire l'ambiguïté.

## Conclusion

Aucune erreur structurelle bloquante supplémentaire n'a été relevée sur le périmètre Phase 3 après les trois corrections ci-dessus. Le socle est apte à être figé sous réserve du contrôle runtime final après redéploiement des commits d'audit.

## Phase 4 — exigence comptable ajoutée

Prévoir un rapport mensuel PDF destiné au comptable avec :

- chiffre d'affaires mensuel HT / TVA / TTC ;
- ventilation Sur place / À emporter / Livraison ;
- récapitulatif des Z journaliers ;
- courbe du chiffre d'affaires quotidien basée sur les Z ;
- ventilation des moyens de paiement lorsque l'encaissement Phase 4 sera en place ;
- téléchargement / impression du PDF ;
- envoi par e-mail au comptable depuis BÉCHÉFAA ;
- adresse du comptable paramétrable dans Administration.
