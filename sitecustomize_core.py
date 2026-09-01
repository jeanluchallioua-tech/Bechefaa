# BÉCHÉFAA POS — migration sûre des descriptions du catalogue
# Chargé automatiquement par Python au démarrage. Idempotent : ne remplit que
# les champs ingredients vides et ne touche jamais aux prix/options/photos/canaux.

from pathlib import Path
import json
import os
import re
import sqlite3
import unicodedata

BASE = Path(__file__).resolve().parent
DB = Path(os.getenv("BECHEFAA_DB", BASE / "bechefaa.db"))


def norm(value):
    s = unicodedata.normalize("NFD", str(value or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    s = s.replace("’", "'").replace('"', "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# Descriptions reprises du menu public BÉCHÉFAA existant.
DESCRIPTIONS = {
    "Formule Mochy's kebbab": "Pâte sauce tomate faite maison avec 3 kebbab. Disponible sur place ou à emporter.",
    "Formule Falafel": "Sandwich pita falafel servi avec des frites maison et 1 boisson. Disponible sur place ou à emporter.",
    "Formule Enfant": "Tender classique ou tender crispy servi avec des frites maison et 1 boisson Caprisun. Disponible sur place ou à emporter.",
    "Formule Panini thon": "Sandwich panini thon avec cheddar coulant, frites maison et 1 boisson. Disponible sur place ou à emporter.",
    "Houmous Maison": "Houmous servi avec aubergines, salade israélienne, poudre zaatar et huile d'olive.",
    "Houmous Bassar Maison": "Houmous fait maison servi avec bœuf, aubergines, salade israélienne et pita.",
    "Houmous Bassar de Shawarma": "Houmous fait maison servi avec shawarma, aubergines, salade israélienne et pita.",
    "Tender Chicken Maison": "Classic : panure traditionnelle maison. Crispy : panure extra croustillante maison. Cheesy : tradition maison, cœur cheddar.",
    "Oignons rings": "Rondelles d'oignon panées.",
    "Merguez": "Servies avec harissa maison, piment et citron, accompagnées d'une pita.",
    "Kefta": "Servie avec harissa maison, piment et citron, accompagnée d'une pita.",
    "Tornado Potato": "Pomme de terre en brochette, mayonnaise, ketchup et oignons crispy.",
    "Assiette kemia": "Salade israélienne, aubergines, houmous, carottes et thon harissa.",
    "Entrée Falafel maison": "Mini assiette servie avec 5 boulettes falafel et une pita.",
    "Mini wraps au thon": "Accompagné de salade israélienne, choux blanc et choux rouge, relevés d'une pointe de harissa.",
    "Mini wraps crispy tenders": "Tenders croustillants, accompagnés d'oignons confits, salade verte et sauce moutarde au miel.",
    "Salade César": "Salade verte, tomate cerise, oignon rouge, concombre, cœur de palmier, carottes râpées, maïs, avocat, pita et vinaigrette maison.",
    "Salade shawarma": "Salade verte, aubergine, salade israélienne, choux blanc, choux rouge, oignon rouge, pita, vinaigrette maison et tehina.",
    "Salade Falafel maison": "Salade verte, aubergine, salade israélienne, choux blanc, choux rouge, oignon rouge, pita, vinaigrette maison et tehina.",
    "Salade thon": "Salade verte, tomate cerise, oignon rouge, concombre, cœur de palmier, carottes râpées, maïs, avocat, pita et vinaigrette maison.",
    "Mini salade": "Salade verte, carottes, tomates, concombres et maïs.",
    "Classic Burger": "Ketchup, mayonnaise, salade verte, cornichons, tomate, oignons rouges, steak 100 % bœuf 150 g. Frites incluses.",
    "Smash Burger": "Ketchup, moutarde, cornichons, oignons confits, cheddar, steak 100 % pur bœuf 150 g. Frites incluses.",
    "Double smash Burger": "Ketchup, moutarde, cornichons, oignons confits, double cheddar, double steak 100 % pur bœuf 150 g. Frites incluses.",
    "Cheese Burger": "Sauce maison, salade verte, tomate, oignons confits, cheddar, steak 100 % pur bœuf 150 g. Frites incluses.",
    "Bacon Burger": "Sauce barbecue, salade verte, tomate, oignons confits, bacon, steak 100 % pur bœuf 150 g. Frites incluses.",
    "Oriental Burger": "Sauce harissa-mayo, salade israélienne, oignons rouges, steak kefta et œuf à cheval. Frites incluses.",
    "Chicken/Crispy Burger": "Moutarde au miel, salade verte, tomate, oignons confits, poulet pané ou chicken crispy. Frites incluses.",
    "Béchéfaa Burger": "Sauce maison, salade verte, cornichon, tomate, avocat, oignons confits, bacon, cheddar, œuf à cheval et steak 100 % pur bœuf 150 g. Frites incluses.",
    "Fish Burger": "Sauce tartare, salade verte, tomate, oignons rouges, filet de poisson pané et cheddar. Frites incluses.",
    "Menu Kids": "Classic burger, steak 100 % pur bœuf 100 g et Caprisun. Frites incluses.",
    "Assiette entrecôte": "Entrecôte selon arrivage, salade verte, salade israélienne, oignon rouge, sauce harissa-mayo et pita israélienne.",
    "Assiette Merguez": "Merguez, sauce harissa-mayo, salade verte, salade israélienne, oignons confits et pita israélienne.",
    "Assiette Mochy's kebbab": "Salade israélienne, sauce harissa-mayo, salade verte, oignon rouge, kefta façon kebab et pita israélienne.",
    "Assiette Shawarma": "Shawarma, houmous, téhina, aubergine, salade israélienne, choux blanc, choux rouge et pita israélienne.",
    "Assiette Poulet": "Poulet au choix, moutarde au miel, salade verte, tomate, oignons confits et pita israélienne.",
    "Assiette Falafel Maison": "Houmous, téhina, aubergine, salade israélienne, choux blanc, choux rouge et pita israélienne.",
    "Assiette double steak Haché": "Double steak haché, salade israélienne, sauce harissa-mayo, salade verte, oignon rouge, houmous, téhina, aubergine, choux blanc, choux rouge et pita israélienne.",
    "Hot-dog": "Ketchup, moutarde et saucisse. Frites incluses.",
    "Sandwich Falafel maison": "Houmous, tehina, aubergine, salade israélienne, choux blanc et choux rouge. Frites incluses.",
    "Sandwich Poulet au choix grillé / Pané /Crispy": "Moutarde au miel, salade verte, tomate et oignons confits. Frites incluses.",
    "Sandwich Poulet grillé / Pané / Crispy": "Moutarde au miel, salade verte, tomate et oignons confits. Frites incluses.",
    "Sandwich steak haché": "Steak 100 % pur bœuf, salade verte, salade israélienne, oignons rouges et sauce harissa. Frites incluses.",
    "Sandwich Shawarma": "Houmous, tehina, aubergine, salade israélienne, choux blanc et choux rouge. Frites incluses.",
    "Sandwich Mochy's kebbab": "Sauce harissa-mayo, salade verte, salade israélienne, oignon rouge et kefta façon kebab. Frites incluses.",
    "Sandwich Merguez": "Sauce harissa-mayo, salade verte, salade israélienne et oignons confits. Frites incluses.",
    "Sandwich Entrecôte": "Selon arrivage : sauce harissa-mayo, salade verte, salade israélienne et oignon rouge. Frites incluses.",
    "Sandwich Pita pané": "Tehina, houmous, aubergines, salade israélienne, choux blanc et choux rouge. Viande au choix.",
    "Sandwich Fait ton sandwich": "Choix du pain, une viande au choix sauf entrecôte, sauces et ingrédients au choix. Frites incluses.",
    "Sandwich \"Fait ton sandwich\"": "Choix du pain, une viande au choix sauf entrecôte, sauces et ingrédients au choix. Frites incluses.",
    "Supplément Cheddar": "Cheddar parvé.",
    "Supplément plaque de Cheddar": "Cheddar parvé.",
    "Supplément steak": "Steak 150 g 100 % pur bœuf.",
    "Frites Maison": "Frites fraîches de pommes de terre, servies avec mayonnaise et ketchup.",
    "Pate sauce tomate": "Spaghettis sauce tomate maison.",
    "Thé": "Servi en théière, pour 2 verres de thé.",
    "Croc choco": "Pain panini et pâte à tartiner.",
    "Croc Thon": "Pain panini, mayonnaise, salade et thon.",
    "Croc Béchéfaa": "Pain panini, mayonnaise et dinde fumée/rosette.",
    "Fruits frais": "Fruits suivant la saison.",
    "Boule de glace vanille": "Glace artisanale.",
    "Boule de glace praliné": "Glace artisanale.",
}

# Alias connus entre le catalogue caisse et le menu historique.
ALIASES = {
    norm("bechefaa"): norm("Béchéfaa Burger"),
    norm("Bechefaa Burger"): norm("Béchéfaa Burger"),
    norm("Sandwich Poulet grillé / Pané / Crispy"): norm("Sandwich Poulet au choix grillé / Pané /Crispy"),
    norm("Sandwich Poulet grillé / Pané /Crispy"): norm("Sandwich Poulet au choix grillé / Pané /Crispy"),
    norm("Assiette Entrecôte"): norm("Assiette entrecôte"),
    norm("Tornado potato"): norm("Tornado Potato"),
}

BY_NORM = {norm(k): v for k, v in DESCRIPTIONS.items()}


def migrate():
    if not DB.exists():
        return
    try:
        with sqlite3.connect(DB) as c:
            c.row_factory = sqlite3.Row
            exists = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='catalog_admin'").fetchone()
            if not exists:
                return
            row = c.execute("SELECT data_json FROM catalog_admin WHERE id=1").fetchone()
            if not row:
                return
            data = json.loads(row["data_json"] or "{}")
            products = data.get("products") or []
            changed = 0
            matched = 0
            for p in products:
                if str(p.get("ingredients") or "").strip():
                    continue
                key = norm(p.get("name"))
                key = ALIASES.get(key, key)
                desc = BY_NORM.get(key)
                if desc:
                    matched += 1
                    p["ingredients"] = desc
                    changed += 1
            if changed:
                c.execute(
                    "UPDATE catalog_admin SET data_json=?, updated_at=strftime('%s','now')*1000 WHERE id=1",
                    (json.dumps(data, ensure_ascii=False),),
                )
                c.commit()
            print(f"BÉCHÉFAA descriptions: {changed} description(s) ajoutée(s), {matched} correspondance(s).")
    except Exception as exc:
        # Une migration de contenu ne doit jamais empêcher le POS de démarrer.
        print("BÉCHÉFAA descriptions migration ignorée:", exc)


migrate()
