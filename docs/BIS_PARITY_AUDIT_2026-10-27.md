# Audit de parité caisse BIS / caisse de production — 27 octobre 2026

**Périmètre strict :** branche `bis-prod-sync-integration-2026-10-25`, dépôt `jeanluchallioua-tech/Bechefaa`. Document de préparation, **pas une validation de déploiement**. Aucun accès ni action vers la production, la sandbox Deliveroo, les imprimantes ou les commandes réelles n'est autorisé par ce document.

## Conditions préalables

1. Établir la version de référence de la caisse de production et la version exacte de BIS (SHA), puis comparer les comportements, pas seulement la présence de code.
2. Exécuter et consulter les résultats **réels** de `.github/workflows/bis-integration-tests.yml` sur le SHA candidat, dont les tests PostgreSQL concurrents. Un statut absent/inconnu n'est pas un succès.
3. Conserver les blocages Deliveroo **scénarios 12 et 16 : non validés**. Le scénario 2 (doublons) exige un essai contrôlé après accord explicite ; les tests isolés ne remplacent pas la validation sandbox.
4. Ne lancer aucun déploiement, envoi de menu, commande, impression, essai sandbox ou changement de production sans accord explicite.

## Matrice de parité à vérifier avant tout déploiement sandbox

| Domaine | Contrôle de parité BIS / production | Indices automatisés disponibles | Statut |
| --- | --- | --- | --- |
| Emporter : remise manuelle | Saisie **en pourcentage**, recalcul après modification du panier, arrondi, non-cumul avec remise web/marketplace, rendu sur ticket | `test_manual_discount.py`, `test_bis_discount_rules.py`, `test_bis_js_smoke.py` | À valider en interface et sur tickets |
| Panier : **Modifier** | Bouton visible sur tablette, modification d'une ligne et de ses options, total et état sauvegardé corrects, aucune ligne dupliquée | `test_bis_pos_parity_render.py`, `test_pos_pending_edit.py`, `test_pos_save_workflow.py` | À valider en interface |
| Paramètres Marketplace | Uber Eats inchangé ; Deliveroo **+20 %** ; sauvegarde partielle sans modifier l'autre canal ; prix caisse/site inchangés ; options et prix exportés à auditer | `test_bis_marketplace_markup.py`, `test_deliveroo_amount_audit.py` | À contrôler sur aperçu, aucun envoi de menu |
| Tables | Occupation, sélection concurrente, transfert, libération après encaissement complet, annulation | `test_table_occupancy.py` | À valider en interface |
| Livraison | Nom, téléphone, adresse, code postal, ville, étage, instructions, provenance marketplace, champs absents sans valeurs inventées | `test_customer_delivery_roundtrip.py`, `test_delivery_details.py`, `test_bis_deliveroo_bridge_runtime.py` | À valider sur aperçu/historique |
| Tickets et cuisine | Contenu/options/quantités, origine Deliveroo, notifications, absence de double ticket ou impression, découpe et format | `test_receipt_layout.py`, `test_bis_classic_kitchen_idempotency.py`, `test_deliveroo_kitchen_preview.py` | À valider sur aperçu ; impression interdite sans accord |
| Historique | Filtre Deliveroo, canal explicite, commandes uniques, coordonnées disponibles, statut, total, réouverture | `test_bis_js_smoke.py`, `test_bis_integration_guard.py` | À valider en interface |
| Impression | Epson réseau, reconnexion, impression caisse/cuisine, réimpression maîtrisée, aucun double pack | `test_receipt_layout.py`, `test_bis_classic_kitchen_idempotency.py` | À valider ultérieurement avec accord |
| Hors connexion | Panier, commandes multiples en attente, reprise automatique, idempotence de resynchronisation, remise conservée, cuisine après reconnexion | `test_bis_js_smoke.py`, `test_bis_integration_guard.py`, `test_manual_discount.py` | À valider sur tablette, sans production |

## Contrôles Deliveroo bloquants

- **Scénario 2 / doublons :** même identifiant de commande livré simultanément ou plusieurs fois → exactement une commande POS et ses lignes cuisine ; contenu différent sous le même identifiant → conflit explicite, sans écrasement ; rollback complet en cas d'échec d'une ligne.
- **PLU :** rapprochement des articles et modificateurs avec le catalogue approuvé ; identifiants canoniques, absence de collision, refus des produits/options inconnus ou désactivés.
- **Dérive de libellés PLU :** même avec un PLU canonique valide, un réordonnancement du catalogue peut désigner un autre supplément. Le préflight BIS compare les libellés article/option (casse et espaces neutralisés), signale les divergences ou libellés manquants, et n'effectue aucun remappage automatique. Ce contrôle est **consultatif**, distinct du chemin réel d'import et ne constitue pas une validation sandbox.
- **Prix :** comparaison en centimes des montants articles, options, total et éventuels frais/remises ; majoration Deliveroo 20 %, sans toucher au taux Uber Eats existant ; ne pas approuver un écart inexpliqué.
  - **Précision catalogue :** les audits BIS refusent désormais les prix source à fraction de centime (ex. `10.004` ou `1.004`) au lieu de les arrondir avant comparaison. Un prix Deliveroo qui correspondrait après arrondi reste un **écart financier à examiner** ; aucune politique de prix n'est approuvée par ce contrôle isolé.
- **Instructions clients :** conserver notes et instructions en cuisine ou bloquer explicitement l'import en cas de schéma non validé ; aucune instruction ne doit être supprimée silencieusement.
  - Le balayage consultatif inclut aussi `allergies`, `food_allergies`, `dietary_requirements`, `dietary_restrictions`, `item_notes`, `modifier_notes` et `kitchen_notes` (variantes de casse/séparateurs). Toute valeur non vide ou structurée est bloquée **avant SQL** par le pont opt-in tant que le mapping cuisine n'est pas approuvé. Ces noms sont des précautions, **pas** une validation du contrat webhook Deliveroo.
- **Instructions au niveau `body` :** l'inventaire consultatif balaie désormais aussi les champs frères de `body.order` (par exemple `body.delivery.instructions` ou `body.customer_notes`). Le pont opt-in doit refuser leurs valeurs non vides avant SQL ; ce contrôle défensif ne valide pas le schéma Deliveroo et n'autorise aucune impression.
- **Instructions à la racine du webhook :** le balayage inspecte également les champs de premier niveau hors `body` (ex. `delivery_instructions`, `customer.food_allergies`). Le pont opt-in refuse toute consigne non vide avant SQL ; les chemins et non les valeurs sont exposés dans le préflight. Ce contrôle reste défensif et ne constitue pas une validation du schéma Deliveroo.
- **Coordonnées :** le webhook observé contient des chemins `delivery.customer_name`, `delivery.contact_number`, `delivery.city`, `delivery.postcode`, `delivery.location`. La **présence d'un champ ne prouve pas que sa valeur est remplie** ; `delivery.location` n'est pas automatiquement une adresse postale.
- **Scénarios 12 et 16 :** **toujours bloqués, non validés**.

## Contrôle de circuit Deliveroo et référence d'historique

- La caisse de production utilise **`/historique-modification`** comme historique de référence. La BIS possède également un écran **`/historique`** : la présence d'un historique BIS ne prouve **pas** la parité avec l'écran de production. Comparer explicitement filtres, coordonnées, statuts, affichage et réimpression avant toute mise en sandbox.
- Le pont opt-in BIS stocke le canal dans `sales_channel=DELIVEROO` et le mode opérationnel dans `source`. Les écrans cuisine/historique doivent donc reconnaître **`sales_channel`**, pas uniquement `source=DELIVEROO`. Tests isolés ajoutés pour la suppression de l'original après remake et le maintien du mode « Emporter » pour `fulfillment_type=customer`.
- Le mode Customer Collect `customer` est enregistré en `source=EMPORTER`, tandis que `deliveroo` et `restaurant` restent `LIVRAISON` dans le pont BIS isolé. Un changement de mode sous le même identifiant externe doit provoquer un conflit d'idempotence. Les modes inconnus nécessitent une revue, sans import automatique.
- Les contrôles automatiques portent sur le code et les doubles de test ; ils ne prouvent **ni l'absence réelle de double impression**, ni la parité de l'écran `/historique-modification`, ni le scénario 2 en sandbox. **Aucun déploiement autorisé.**

## Écart technique identifié — rapprochement catalogue avant import

L'analyse statique de `_bridge_order_new` dans `clean_caisse/deliveroo_sandbox_phase6.py` montre que le pont opt-in vérifie les identifiants et les montants déclarés, mais **ne consulte pas le catalogue approuvé** avant ses écritures POS. Les PLU de modificateurs `opt:` sont contrôlés sur leur forme et leur parent, **pas sur l'existence réelle du choix** ; les anciens PLU sans préfixe nécessitent aussi un rapprochement. Les fonctions de réconciliation et d'audit des prix sont actuellement distinctes de ce chemin d'import. Il faut donc obtenir une validation explicite des PLU produits/options et des prix (+20 % Deliveroo) **sur le chemin effectif d'import** avant tout GO. Un test CI isolé réussi ne suffit pas.

Le balayage des instructions clients dispose désormais d'une limite couvrant également les champs et entrées de listes scalaires : si la limite est atteinte, l'import opt-in est bloqué **avant SQL**. Les tests correspondants ne déclenchent aucune commande réelle.

## Décision de sortie

**NO-GO par défaut** tant que la parité fonctionnelle n'est pas constatée, que les résultats CI du SHA candidat ne sont pas vérifiés, et que les scénarios Deliveroo bloquants ne sont pas explicitement traités. Le document ne modifie aucun état applicatif.
