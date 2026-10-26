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
