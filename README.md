# BÉCHÉFAA POS V0.5 — Cloud Deploy Ready

Cette version transforme la base V0.4.5 en application web multi-postes.

## URLs
- `/caisse` : poste principal
- `/salle` : tablette de prise de commande
- `/cuisine` : écran/tablette cuisine

## Synchronisation
Les commandes sont enregistrées dans une base SQLite commune côté serveur.
Les écrans interrogent le serveur toutes les 1,5 seconde :
- une commande saisie en salle arrive sur la caisse et la cuisine ;
- un changement de statut apparaît sur les autres appareils ;
- les cases cuisine « article préparé » sont enregistrées côté serveur.

## Déploiement Render
1. Mettre ce dossier dans un dépôt GitHub.
2. Créer un Web Service Render à partir du dépôt.
3. Render peut utiliser `render.yaml`, ou :
   - Build Command : `pip install -r requirements.txt`
   - Start Command : `gunicorn app:app`
4. Après déploiement, ouvrir :
   - `https://VOTRE-ADRESSE.onrender.com/caisse`
   - `https://VOTRE-ADRESSE.onrender.com/salle`
   - `https://VOTRE-ADRESSE.onrender.com/cuisine`

## Important avant production
SQLite sans disque persistant peut être perdu lors d'un redéploiement/redémarrage sur certains hébergements.
Pour une vraie exploitation quotidienne, la prochaine étape doit utiliser PostgreSQL ou un disque persistant,
avec authentification, sauvegardes, journal d'encaissement et gestion des conflits hors connexion.

Cette V0.5 est une version de test cloud multi-appareils.
