# BÉCHÉFAA BIS — audit de parité avant déploiement sandbox

Date du contrôle de code : 2026-10-26. Périmètre : `bis-prod-sync-integration-2026-10-25`.
Référence fonctionnelle à contrôler : caisse de production ; branche de comparaison Git : `phase4-encaissement`.

**Statut : NON VALIDÉ POUR DÉPLOIEMENT.** Ce document est une grille de contrôle, pas un procès-verbal de recette. Ne pas déployer ni transmettre de commandes, menus ou impressions sans accord explicite.

## Constat de divergence

La comparaison Git `phase4-encaissement...bis-prod-sync-integration-2026-10-25` indique deux branches **divergentes** (au contrôle : 266 commits propres à BIS, 13 commits présents sur la branche de référence mais absents de BIS). Une CI verte ne prouve donc pas une caisse identique. Avant sandbox, réconcilier les différences fonctionnelles sans fusion aveugle ni modification de la production.

## Matrice de recette obligatoire

| Fonction | Indices dans le code BIS / tests | Validation restante |
| --- | --- | --- |
| Remise manuelle en % sur commandes à emporter | `clean_caisse/manual_discount.py`, `tests/test_bis_discount_rules.py`, `tests/test_bis_js_smoke.py` ; calcul et affichage testés isolément | **À vérifier sur la véritable interface BIS** : bouton visible sur PC/tablette, choix du %, recalcul panier, sauvegarde et reprise ; aucun cumul interdit |
| Bouton **Modifier** dans le panier | `clean_caisse/pos_quantity_phase38.py`, `clean_caisse/pos_options_modal_final.py` ; `tests/test_bis_pos_parity_render.py` contrôle l'injection HTML | **À vérifier sur PC/tablette** : bouton visible et tactile, options préremplies, validation et persistance sans création de doublon |
| Majoration Marketplace | `clean_caisse/marketplace_markup_phase6.py`, `tests/test_bis_marketplace_markup.py` ; défaut Deliveroo 20 %, Uber Eats inchangé | **À vérifier en base BIS** : une ligne Deliveroo déjà enregistrée à 15 % ne devient pas automatiquement 20 % ; vérifier également les prix produits/options du menu généré |
| Tables 1–9 | `clean_caisse/table_core_phase36.py`, `tests/test_table_occupancy.py` | Réservation, occupation jusqu'au règlement, libération et collisions multi-postes |
| Livraison | `tests/test_customer_delivery_roundtrip.py`, `tests/test_delivery_details.py` | Nom, téléphone, adresse, code porte/interphone, étage, instructions dans aperçu et ticket |
| Tickets / impression Epson | `tests/test_receipt_layout.py`, `tests/test_bis_classic_kitchen_idempotency.py`, `clean_caisse/epson_epos_network_phase6.py` | Le POST classique répété pour une commande déjà « À préparer » n'ouvre plus le pack d'impression (test isolé) ; restent à vérifier le chemin d'impression direct, les reprints explicites, le circuit Deliveroo, le retour caisse et les essais physiques |
| Historique et modification commande | `clean_caisse/history_modifier.py`, `tests/test_pos_pending_edit.py` | Modification avant cuisine, réouverture, conservation de l'identité de commande et statut, sans double envoi |
| Hors connexion | `clean_caisse/offline_mode_phase6.py`, `tests/test_bis_js_smoke.py` | Plusieurs commandes hors ligne, reconnexion, reprise automatique unique, historique et alerte sonore |
| Service sur place / emporter / livraison | `clean_caisse/service_mode_ui_phase42.py`, `tests/test_bis_module_registration.py` | Contrôle tactile complet et cohérence des libellés |
| Calendrier et horaires | `clean_caisse/religious_calendar_phase6.py`, `tests/test_religious_hours.py` | Horaires modifiables, fermetures Shabbat/fêtes et impact sur l'acceptation des commandes |

Les contrôles de code et les tests unitaires **ne remplacent pas** la recette sur la BIS effectivement déployée. Les fonctionnalités de remise et de modification ont été signalées comme absentes dans l'interface observée ; les considérer **bloquantes jusqu'à démonstration contraire**.

## Deliveroo — validations distinctes

- **Order API / test 2 : bloqué**. Vérifier l'idempotence avec répétition du même `order.new`, événements avec GUID différents mais même ID commande, arrivées concurrentes, remake parent/enfant, affichage et envoi cuisine unique. Le module `deliveroo_order_idempotency_phase6.py` calcule une clé déterministe mais précise lui-même que l'unicité doit être garantie transactionnellement en base. Les tests purs ne suffisent pas à valider le circuit complet.
- **Menu API / scénario 12 : bloqué**. Réponse HTTP 200 à un POST d'indisponibilité ≠ reconnaissance de l'appel par le validateur Deliveroo.
- **Menu API / scénario 16 : bloqué**. Obtenir le diagnostic précis de validation avant de déclarer le scénario terminé.
- **PLU, prix, instructions** : audits read-only présents dans `clean_caisse/deliveroo_*_phase6.py` ; ne pas convertir un audit réussi en autorisation implicite de dispatch cuisine.

**Correctif BIS du 26/10/2026 :** le double POST `/send-kitchen-classic/<order_id>` ne doit plus réimprimer le pack cuisine/client après la première transition vers « À préparer ». Le verrou `FOR UPDATE` est conservé. Cela protège le chemin classique de la caisse mais **ne démontre pas** l'idempotence transactionnelle de l'import Deliveroo, ni l'absence de doublons dans le scénario 2. Un nouvel envoi volontaire doit utiliser le mécanisme de réimpression dédié.

**Contrôle BIS complémentaire du 26/10/2026 (pont `order.new`) :** la fonction réelle `_bridge_order_new` refuse désormais les identifiants Deliveroo/PLU non canoniques, les quantités booléennes, fractionnaires ou textuelles, les montants non entiers ou hors EUR, et les options malformées **avant tout accès à la base**. Le format `options_json` des tickets est conservé. `tests/test_bis_deliveroo_bridge_runtime.py` exécute cette fonction avec une fausse base en mémoire : première création, replay identique, identifiants différents et refus des entrées invalides. Ces tests **ne reproduisent pas une concurrence PostgreSQL réelle** et ne prouvent ni le rapprochement PLU/prix ni le traitement complet du remake parent/enfant. **Le test 2 reste bloqué.**

**Contrôle BIS complémentaire du 26/10/2026 (notes et quantités Deliveroo) :** le pont opt-in refuse maintenant les événements autres que `order.new`, les collections d'options malformées et les instructions client non vides tant que leur transcription sur les tickets cuisine n'est pas approuvée. Cette protection est volontairement **bloquante** pour les commandes comportant des notes : elle évite leur perte silencieuse, mais ne constitue pas une prise en charge fonctionnelle des instructions. Les quantités d'options supérieures à 1 sont conservées dans `options_json` et `options_text` ; le format des options de quantité 1 reste inchangé. Les tests de ces comportements utilisent une base simulée et ne démontrent ni la parité de la tablette, ni la compatibilité d'impression Epson réelle. **Le test 2 et les scénarios 12/16 restent bloqués.**

**Contrôle BIS complémentaire du 26/10/2026 (rejeu du GUID webhook) :** le stockage de l'événement Deliveroo est désormais immuable pour un même `X-Deliveroo-Sequence-Guid` : un rejeu strictement identique conserve la première preuve, tandis qu'un même GUID accompagné d'un contenu JSON différent est refusé avant le pont POS. `tests/test_bis_deliveroo_event_replay.py` couvre ces chemins sur une fausse base SQL. Ce contrôle est distinct de l'unicité de commande par ID Deliveroo et **ne valide pas** la concurrence PostgreSQL réelle, le test 2, ni les scénarios Menu API 12/16. Aucun déploiement n'est autorisé par ce seul test.

**Contrôle BIS complémentaire du 26/10/2026 (rejeu de l'ID commande Deliveroo) :** le pont POS enregistre maintenant une empreinte SHA-256 du contenu normalisé (lignes, quantités, PLU, prix, options et total) dans la même transaction que la création de la commande. Un second `order.new` portant le même ID Deliveroo mais des articles, prix ou options différents est refusé ; un rejeu strictement identique reste sans nouvel enregistrement. Les anciennes lignes dépourvues d'empreinte sont refusées pour examen, sans modification rétroactive. `tests/test_bis_deliveroo_bridge_runtime.py` couvre les conflits de prix, d'options et les anciennes lignes sur fausse base. **La concurrence PostgreSQL réelle, les remakes, les règles financières/PLU et l'impression ne sont pas validés ; le test 2 reste bloqué.**

**Contrôle BIS complémentaire du 26/10/2026 (preuves financières du pont Deliveroo) :** le pont opt-in contrôle désormais les champs `order.total_price` et `item.unit_price` lorsqu'ils sont fournis : monnaie EUR, centimes entiers non négatifs, sans booléens. Si le total de commande déclaré diffère de la somme des lignes, l'import est refusé **avant accès à la base** pour examen des frais, remises et règles d'options ; aucune hypothèse comptable n'est appliquée. Ces montants déclarés entrent également dans l'empreinte transactionnelle pour empêcher qu'un rejeu du même ID masque un changement de prix. Les événements historiques ne contenant pas ces champs restent analysables, mais l'ajout de ces champs lors d'un rejeu est traité comme un conflit conservateur. Tests isolés dans `tests/test_bis_deliveroo_bridge_runtime.py`. **Cela ne valide pas les politiques financières Deliveroo, la concurrence PostgreSQL, le test 2 ni les scénarios 12/16.**

**Contrôle BIS complémentaire du 26/10/2026 (allocation des centimes par quantité) :** le pont opt-in refuse maintenant une ligne Deliveroo dont le total en centimes n'est pas divisible par la quantité (ex. 10,00 € pour 3 unités). La caisse ne stockant qu'un prix unitaire pour cette ligne, accepter 3,333… € aurait créé un risque d'arrondi lors du recalcul ou de l'impression. Le refus intervient avant l'accès à la base et nécessite une politique de ventilation/remise explicitement approuvée. Les tests isolés couvrent les montants non divisibles et les montants divisibles ; ils ne constituent pas une validation PostgreSQL réelle ni une preuve de conformité financière complète. **Le test 2 et les scénarios 12/16 restent bloqués.**

## Critères de sortie avant sandbox

1. CI de la **dernière révision** de BIS terminée en succès ; examiner les étapes individuellement.
2. Comparatif production/BIS sur PC **et** tablette avec captures ou procès-verbal pour toutes les lignes ci-dessus.
3. Vérification des valeurs **effectivement stockées** pour les majorations (Deliveroo 20 %, Uber Eats inchangé).
4. Preuve de non-duplication transactionnelle et de non-double impression/envoi cuisine, avec scénarios de replay et concurrence.
5. Autorisation explicite du propriétaire avant tout déploiement sandbox.

Aucune modification de `phase4-encaissement`, `deliveroo-order-bridge-sandbox` ou des applications déployées n'est autorisée dans ce chantier.

**Contrôle BIS complémentaire du 26/10/2026 (prix des suppléments Deliveroo) :** lorsqu'un modificateur contient `unit_price`, le pont opt-in valide le montant en centimes EUR non négatifs et l'inclut dans l'empreinte de rejeu de la commande, sans modifier `options_json` ni les tickets. Un rejeu du même ID avec un prix de supplément changé ou ajouté est refusé ; les anciens événements sans prix de supplément conservent leur empreinte initiale. Trois tests isolés utilisent une fausse base SQL. **Ce contrôle n'approuve pas la politique de prix des suppléments et ne valide pas le test 2, la concurrence PostgreSQL, ni les scénarios 12/16.**

**Contrôle BIS complémentaire du 26/10/2026 (cohérence prix unitaire/ligne sans supplément) :** lorsque Deliveroo fournit un prix unitaire et que la ligne ne contient aucun modificateur, le pont opt-in refuse avant tout accès à la base un total de ligne différent de `quantité × prix unitaire`. Une remise ou un frais éventuel doit faire l'objet d'une politique financière explicite, et non d'une correction silencieuse. Deux nouveaux tests isolés couvrent le refus et le rejeu conforme. Cela ne valide pas les lignes avec suppléments, les prix du catalogue, la concurrence PostgreSQL réelle, le test 2 ou les scénarios 12/16. Aucun déploiement n'est autorisé.


## Écart critique constaté — commandes du site, bandeau et impression (26/10/2026)

Le test réel au restaurant confirme qu'un paiement Mollie peut aboutir et que la commande arrive à la caisse, tandis que le navigateur client affiche encore « Vérification indisponible ». **Ce problème de retour de paiement n'est pas résolu** : aucune modification du site de production ou de sa passerelle de paiement n'est autorisée dans cette branche.

Le contrôle du code BIS a révélé deux régressions potentielles par rapport au fonctionnement demandé : le bandeau SITE disparaissait automatiquement après 8 secondes et un timer pouvait lancer l'impression Epson sans clic. **Correctif limité à BIS non déployée :** le bandeau persiste dans une file locale jusqu'à un clic ; ce clic réserve puis lance au maximum un pack cuisine/client par ID sur ce navigateur. Les commandes successives restent en file, même après rechargement. Un échec d'impression ambigu n'est jamais relancé automatiquement. Le bip est toujours appelé dès la détection de nouvelles commandes, mais son audibilité dépend du déverrouillage audio du navigateur et des réglages.

Le test Node isolé dans `tests/test_bis_js_smoke.py` vérifie l'absence d'impression au polling, la persistance des deux commandes après rechargement, le lancement après chaque clic et l'absence de double lancement sur ce navigateur. **Aucun ticket n'a été réellement imprimé.** La parité PC/tablette, l'Epson, le volume/bip réel, la concurrence entre plusieurs terminaux et le retour Mollie restent à valider avant sandbox. Le mécanisme local ne constitue pas une garantie de non-duplication d'impression multi-appareils.


## Complément de recette : échec transactionnel et retour utilisateur (26/10/2026)

- Un test isolé supplémentaire (`tests/test_bis_deliveroo_bridge_runtime.py`) simule une erreur SQL lors de l'insertion du **deuxième article** d'une commande Deliveroo. Le faux gestionnaire transactionnel annule la commande et le premier article ; un rejeu complet peut ensuite créer **une seule** commande avec ses deux articles, puis un nouveau rejeu est classé comme doublon. Ce test vérifie la délimitation de transaction du pont, **pas** les garanties de PostgreSQL réel ni l'envoi cuisine/impression.
- Comparaison Git actualisée au 26/10 : `phase4-encaissement...bis-prod-sync-integration-2026-10-25` reste **divergente** : **305 commits en avance et 13 en retard** au moment du contrôle, avant le présent ajout de test. Ces chiffres ne sont pas des preuves de parité fonctionnelle.
- Retour du restaurant : l'absence de bip observée lors du test de commande site provenait du **volume baissé de la tablette**. Ne pas modifier la logique audio sans reproduction d'un défaut avec volume et paramètres vérifiés.
- Le comportement à préserver est : **bip dès réception** ; **bandeau visible jusqu'au clic** ; **impression cuisine/client uniquement au clic**. Ce flux doit être testé sur tablette réelle, avec deux commandes rapprochées et retour depuis Epson.
- **Bloquants maintenus** : erreur de vérification du retour Mollie côté site malgré paiement encaissé ; recette BIS PC/tablette et Epson ; test Deliveroo 2 sous concurrence PostgreSQL ; scénarios Deliveroo 12 et 16. Aucun de ces points n'est réputé validé par les tests isolés.


## Vérification isolée PostgreSQL réelle — 27/10/2026

- **CI validée sur PostgreSQL 16 jetable dans GitHub Actions**, sans application BIS déployée, sans webhook, commande externe, ticket ni imprimante : [run 40421482377](https://github.com/jeanluchallioua-tech/Bechefaa/actions/runs/40421482377) (**SUCCESS**, étape PostgreSQL **SUCCESS**).
- Le test exécute la véritable fonction `_bridge_order_new` avec **deux connexions PostgreSQL concurrentes**. Trois cas sont couverts : (1) même ID et même panier : **une création + un doublon**, une seule ligne de commande et un seul article ; (2) même ID avec prix contradictoires : **une création + un conflit**, sans écrasement ; (3) deux IDs différents : **deux commandes et deux numéros POS distincts**. La base est créée et détruite avec le service CI.
- Cette preuve lève la limite antérieure des **simulations uniquement en mémoire pour ces trois cas précis**. Elle **ne valide pas le test Deliveroo 2 de bout en bout** : webhook réel, GUID distincts, remakes, reconnaissance par Deliveroo, circuit cuisine et impression Epson restent à contrôler. Scénarios 12 et 16 toujours bloqués.
- Comparaison Git consultée le 27/10 : BIS **311 commits en avance, 13 en retard** sur `phase4-encaissement`. Les 13 commits propres à la référence comprennent notamment les évolutions de remise en %, édition du panier, tables, livraison et horaires. Les tests isolés ne remplacent pas la recette fonctionnelle sur PC/tablette. **Ne pas fusionner automatiquement les branches.**


## Audit ciblé des 13 commits de production absents de BIS — 27/10/2026

Comparaison Git en lecture seule : `bis-prod-sync-integration-2026-10-25...phase4-encaissement` ; **13 commits présents uniquement dans la branche de référence**. Ces écarts imposent une recette fonctionnelle : le nombre de commits ne suffit pas à établir si les changements ont été reproduits autrement dans BIS. **Ne pas fusionner aveuglément.**

| Commit production absent | Fonction à comparer en priorité | Preuve exigée avant sandbox |
| --- | --- | --- |
| `144125c4` | Nom/prénom obligatoires, téléphone facultatif en caisse à emporter | Création et validation d'un client sur PC/tablette |
| `a230bde4` | Paramètres publics des avis Google | Aucun effet de bord sur la caisse ou l'API du site |
| `cdb2f772` | Modification des options dans le panier ; accès livraison sur tickets | Modifier sans doubler la ligne ; ticket complet |
| `e2e45128` | Accès livraison depuis les fiches clients | Persistance et ticket après reprise client |
| `c68f571d` | Tables occupées jusqu'au paiement ; catégorie conservée en modification | Cycle table 1–9, encaissement, retour catégorie |
| `4b404361` | Étage/instructions client ; taille des tickets cuisine | Champs enregistrés et lisibles sur ticket |
| `b40758e2` | Libellés Code / Interph. permanents | Valeurs visibles dans la fiche et le reçu |
| `24179464` | Accès livraison dans l'aperçu de commande | Vérification visuelle sur PC/tablette |
| `a399fdbf` | Détails livraison dans l'historique actif | Réouverture d'une commande sans perte de champs |
| `2a2f5a84` | Horaires modifiables du calendrier hébraïque | Enregistrement et effet sur ouverture/fermeture |
| `e0289223`, `ce96fe6d`, `db13f102` | Remise manuelle **discrète en pourcentage** pour emporter | Visibilité tactile, calcul, persistance, impression |

**Vérifications transverses supplémentaires** : paramétrage Marketplace Deliveroo effectivement enregistré à **20 %** (une valeur préexistante à 15 % peut persister), majoration Uber Eats inchangée ; commandes site avec **bip à réception**, bandeau persistant et **impression seulement au clic** ; historique, hors connexion, reconnexion et Epson. Les tests unitaires ne prouvent pas ces interactions matérielles.

**Test PostgreSQL ajouté le 27/10** (`tests/test_bis_deliveroo_bridge_runtime.py`) : contrainte SQL temporaire qui force l'échec d'insertion du **deuxième article** ; vérifie le rollback complet puis un import réussi et son rejeu sans doublon. Il ne contacte que la base PostgreSQL jetable de CI, pas Deliveroo ni une caisse déployée. **Résultat CI à contrôler sur le commit concerné** avant toute revendication de succès.

**Blocages inchangés** : test Deliveroo 2 non validé de bout en bout (webhook, cuisine et Epson), scénarios Deliveroo 12 et 16 bloqués, retour Mollie du site en erreur malgré paiement réel. Aucun déploiement autorisé.


## Contrôle complémentaire — notes Deliveroo imbriquées (27/10/2026)

Le diagnostic en lecture seule parcourt désormais les objets et listes de `body.order` au-delà des seuls niveaux commande/article/modificateur. Il relève les champs de consignes de livraison, d'allergies et les variantes de noms de champs en camelCase, **sans interpréter ni imprimer leur contenu**. Une exploration incomplète (profondeur ou nombre d'objets excessif) entraîne le refus conservateur de l'import opt-in avant toute requête SQL. Des tests vérifient les consignes imbriquées, les valeurs structurées et les événements trop profonds.

**Ce n'est pas une validation des consignes clients** : le schéma réel des webhooks et la transcription exacte sur tickets cuisine doivent être confirmés avant d'autoriser leur import. Aucun scénario Deliveroo 2, 12 ou 16 n'est déclaré validé par ce changement. Le rapprochement complet des PLU/prix et la recette PC/tablette/Epson restent obligatoires.

Comparaison Git consultée le 27/10 : BIS **320 commits en avance et 13 en retard** sur `phase4-encaissement` (constat ponctuel, sans preuve de parité). Les paramètres Marketplace doivent être vérifiés en base BIS : **Deliveroo 20 %**, **Uber Eats au taux déjà existant**, sans écrasement automatique d'anciennes valeurs.


## Garde-fou supplémentaire — statut accepté Deliveroo (27/10/2026)

Le détecteur utilisé avant l'éventuel `sync_status` n'assimile plus une chaîne libre « accepted » (note client, description, texte de journal) à une acceptation de commande. Seuls les champs explicites `status`, `order_status` et `state` d'un événement `order.status_update` peuvent déclencher la détection ; le parcours est limité en profondeur et refuse prudemment les événements trop imbriqués. Les tests isolés couvrent le statut imbriqué conforme, les notes trompeuses, les événements `order.new` et la profondeur excessive.

L'audit des GUID couvre aussi deux événements distincts pour **un même ID commande** : deux preuves d'événements doivent être conservées ; la création d'une seule commande POS est contrôlée séparément par les tests de rejeu et de concurrence PostgreSQL. **Ces tests n'envoient aucun `sync_status` et ne valident ni le test Deliveroo 2 de bout en bout, ni les scénarios 12/16.** Vérifier les résultats de la CI de la dernière révision avant toute conclusion.

**Parité caisse avant sandbox : toujours NON VALIDÉE.** Refaire les essais PC et tablette : remise manuelle en % pour emporter, Modifier du panier, majoration Deliveroo effectivement stockée à 20 % et Uber Eats inchangé, tables, livraison, tickets, historique, Epson et hors connexion. Aucune impression, commande ou synchronisation externe n'est autorisée sans accord.


## Contrôle ciblé — statut Deliveroo et parité avant sandbox (27/10/2026)

- Le statut `accepted` n'est plus recherché dans toutes les métadonnées de l'événement : seuls les champs de statut de `body` ou `body.order`, et leurs journaux explicites `status_log`/`status_history`, sont considérés. Un `status: accepted` dans `customer`, `items` ou `metadata` ne suffit plus à autoriser le diagnostic `sync_status`. Les tests de non-régression sont isolés : ils n'émettent aucune requête vers Deliveroo.
- GitHub Actions sur le commit `bb1ace59` : [run 40450528546](https://github.com/jeanluchallioua-tech/Bechefaa/actions/runs/40450528546), **SUCCESS** (incluant les contrôles PostgreSQL 16, le rejeu GUID, les prix et les tests caisse).
- Divergence Git consultée avant ce complément documentaire : **327 commits BIS en avance et 13 en retard** sur `phase4-encaissement`. Il s'agit d'un indicateur de divergence, **pas** d'une preuve de parité fonctionnelle.
- **Recette bloquante avant sandbox** : PC et tablette pour remise manuelle en % à emporter, bouton Modifier du panier, paramètres Marketplace (Deliveroo stocké à 20 %, Uber Eats conservé), tables, livraison, tickets et aperçu, historique, clic d'impression Epson, bip au volume normal et hors connexion/reconnexion. Le code ne permet pas de conclure à leur fonctionnement matériel.
- **Non validés** : test Deliveroo 2 de bout en bout, circuit cuisine et impression réels, rapprochement exhaustif PLU/prix et instructions clients, scénarios Deliveroo 12 et 16. Retour Mollie du site toujours à traiter séparément. Aucun déploiement ni action externe autorisé.
