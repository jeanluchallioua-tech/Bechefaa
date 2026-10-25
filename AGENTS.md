# Instructions BÉCHÉFAA

## Tickets client et cuisine : présentation verrouillée

Le 9 octobre 2026, le propriétaire a confirmé et verrouillé la présentation
des deux tickets au commit b457796c9462f186862a8e3c410516060c464dbe.

Ne pas modifier le format, les tailles de police, les espacements, les titres,
l'alignement des prix ou la présentation des options sans nouvelle demande
explicite du propriétaire. Les réparations des commandes, notifications et
connexions d'impression doivent conserver ce rendu.

Référence : clean_caisse/receipt_photo_layout.py, largeur 576 points.
Le ticket client conserve 42 colonnes, une hauteur de texte de 28 points et
un interligne de 32 points. À la demande explicite du propriétaire du
24 octobre 2026, le ticket cuisine utilise désormais une police agrandie :
34 colonnes, hauteur de texte de 34 points et interligne de 40 points.
Le ticket client de livraison affiche les coordonnées, le code porte/interphone,
l'étage et les consignes disponibles dans la commande et la fiche client.
Chaque sélection d'option reste sur sa propre ligne, sans titre de groupe.
Les prix des articles sont alignés à droite sur le ticket client.
L'aperçu et l'impression Epson utilisent le même rendu.

Cette règle concerne les tickets papier et leurs aperçus. L'écran cuisine
conserve sa présentation déjà validée.



À la demande du propriétaire du 25 octobre 2026, le ticket client affiche
le sous-total et la remise manuelle (pourcentage et montant déduit) lorsqu’une remise caisse est appliquée.
Cette ligne conserve les dimensions et polices existantes.
