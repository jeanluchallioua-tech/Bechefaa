# Stabilisation du démarrage tablette — préparation du 19 novembre 2026

Statut : correctif préparé et testé localement, non déployé. Jean-Luc demande
explicitement de ne rien déployer avant récupération de la tablette et son feu vert.
La branche `phase4-encaissement` ne doit pas être déplacée pendant cette préparation.

## Constats vérifiés dans le code

- Le worker public `/caisse-sw.js` importe `/offline-sw.js`, auparavant protégé par
  le PIN. Sans session, le navigateur reçoit une redirection et du HTML au lieu du
  script importé. Cela peut faire échouer une installation ou une mise à jour.
- Trois inscriptions utilisaient deux URLs différentes pour le même scope.
- Le chargement de `/pos` n'avait pas de délai réseau explicite et le démarrage `/`
  n'avait pas de secours local, alors que le manifeste lance `/`.
- Une installation pouvait mettre en cache la page PIN sous `/pos`, puis supprimer
  l'ancien cache lors de l'activation même sans nouvelle copie exploitable.
- La session PIN est volontairement conservée 180 jours. Un navigateur possédant
  cette session est redirigé vers la caisse sans nouvelle saisie du PIN.

Ces constats ne prouvent pas pourquoi l'icône précise de la tablette ne répond
plus. Un lanceur Android qui échoue avant de contacter le site nécessite un
contrôle sur l'appareil. Le correctif ne garantit pas de réparer ce cas.

## Correctif proposé

- Scripts de worker accessibles sans PIN, données/API caisse toujours protégées.
- URL d'inscription unique et vérification sans cache HTTP des scripts.
- Repli après 8 secondes pour les GET de démarrage uniquement. Aucun délai ajouté
  aux POST de commande : une écriture incertaine ne doit pas être rejouée.
- Cache du véritable shell POS authentifié, jamais de la page PIN ; ancienne copie
  conservée lorsque la nouvelle est indisponible. Le démarrage `/` utilise ce secours.
- Écran autonome Réessayer si aucune copie utilisable n'est disponible.
- Pas de skipWaiting ni de rechargement forcé. La nouvelle version attend la
  fermeture des pages utilisant l'ancien worker. Une information l'indique en caisse.
- À la déconnexion/au retour du verrouillage en ligne, invalidation des copies HTML
  locales uniquement. Aucun effacement d'IndexedDB, de panier ou de commandes.
- PIN inchangé : pas de réauthentification systématique ajoutée.

## Vérifications automatisées

Depuis la racine du dépôt :
`python -m unittest discover -s tests -p test_tablet_startup.py -v`
Flask et Node sont requis. Cinq tests couvrent les routes de scripts sans session,
les API protégées, le PIN mémorisé et la déconnexion, la syntaxe JavaScript et les
scénarios worker (réseau bloqué, cache ancien, faux shell PIN, stockage indisponible,
installation incomplète, absence d'accès aux commandes locales pendant le démarrage).

## Validation sur Samsung après accord, hors service

1. Avant tout effacement/réinstallation, vérifier que toutes les commandes en attente
   sont synchronisées. Ne pas effacer les données de Samsung Internet.
2. Relever Android, version Samsung Internet et ce que fait l'icône (rien, fenêtre
   brève, écran blanc ou écran figé). Vérifier l'adresse utilisée par le navigateur.
3. Déployer seulement après feu vert explicite. Ouvrir la caisse en ligne, puis
   fermer tous ses onglets et fenêtres pour permettre l'activation du nouveau worker.
4. Tester plusieurs ouvertures de l'icône et un redémarrage de la tablette.
5. Tester une session existante puis une session Secret séparée : PIN attendu dans
   la seconde. Tester la déconnexion sans commande locale en attente.
6. Tester le démarrage hors connexion après chargement en ligne, puis une commande
   test et sa synchronisation unique au retour du réseau.
7. Vérifier historique, notifications et impression cuisine + client avec retour
   Epson. Ne pas déclarer la tablette stabilisée avant ces contrôles matériels.

## Retour arrière

Revenir aux trois fichiers serveur précédents si nécessaire. Le navigateur peut
conserver le worker actif jusqu'à la fermeture des pages ; la simple remise en
ligne d'un ancien commit ne prouve pas que le worker a changé. Ne jamais vider
IndexedDB pour revenir en arrière. Les tables PostgreSQL ne sont pas modifiées.
