from catalog_core import normalize_catalogue, product_unit_price, validate_catalogue


def test_absolute_quantity_price_replaces_base():
    product = {
        "id": "tender",
        "name": "Tender Chicken Maison",
        "category": "Entrées",
        "price": 8,
        "options": [
            {
                "key": "nombre_tender",
                "title": "Nombre de Tender",
                "required": True,
                "max": 1,
                "priceMode": "absolute",
                "choices": [["5 pièces", 8], ["10 pièces", 15]],
            },
            {
                "key": "sauce_extra",
                "title": "Sauce supplémentaire",
                "max": 3,
                "priceMode": "extra",
                "choices": [["Barbecue", 1]],
            },
        ],
    }
    assert product_unit_price(product, {"nombre_tender": [{"name": "5 pièces", "price": 8}]}) == 8
    assert product_unit_price(product, {"nombre_tender": [{"name": "10 pièces", "price": 15}]}) == 15
    assert product_unit_price(product, {
        "nombre_tender": [{"name": "10 pièces", "price": 15}],
        "sauce_extra": [{"name": "Barbecue", "price": 1}],
    }) == 16


def test_category_change_is_data_only():
    data = {
        "categories": [
            {"id": "c1", "name": "Entrées", "active": True},
            {"id": "c2", "name": "Formules MIDI", "active": True},
        ],
        "products": [{"id": "p1", "name": "Tender", "category": "Entrées", "price": 8}],
    }
    clean = normalize_catalogue(data)
    clean["products"][0]["category"] = "Formules MIDI"
    assert validate_catalogue(clean) == []


def test_unknown_category_is_rejected_without_crashing():
    data = {
        "categories": [{"id": "c1", "name": "Entrées", "active": True}],
        "products": [{"id": "p1", "name": "Tender", "category": "Catégorie inexistante", "price": 8}],
    }
    errors = validate_catalogue(data)
    assert errors
    assert "Catégorie inconnue" in errors[0]


def test_absolute_group_must_be_single_choice():
    data = {
        "categories": [{"id": "c1", "name": "Entrées", "active": True}],
        "products": [{
            "id": "p1",
            "name": "Tender",
            "category": "Entrées",
            "price": 8,
            "options": [{
                "key": "nombre",
                "title": "Nombre de Tender",
                "max": 2,
                "priceMode": "absolute",
                "choices": [["5 pièces", 8], ["10 pièces", 15]],
            }],
        }],
    }
    assert any("choix unique" in x for x in validate_catalogue(data))


def test_classic_burger_options_are_preserved():
    data = {
        "categories": [{"id": "burgers", "name": "Burger", "active": True}],
        "products": [{
            "id": "classic-burger",
            "name": "Classic Burger",
            "category": "Burger",
            "price": 12,
            "ingredients": "Ketchup, mayonnaise, salade verte, cornichons, tomate, oignons rouges",
            "options": [
                {
                    "key": "cuisson",
                    "title": "Cuisson",
                    "required": False,
                    "max": 1,
                    "priceMode": "extra",
                    "choices": [["Bleu", 0], ["Saignant", 0], ["À point", 0], ["Bien cuit", 0]],
                },
                {
                    "key": "retirer_garniture",
                    "title": "Retirer garniture",
                    "required": False,
                    "max": 6,
                    "priceMode": "extra",
                    "choices": [["Sans salade verte", 0], ["Sans tomate", 0], ["Sans oignons rouges", 0]],
                },
                {
                    "key": "supplements",
                    "title": "Suppléments",
                    "required": False,
                    "max": 0,
                    "priceMode": "extra",
                    "choices": [["Avocat", 2], ["Cheddar", 2]],
                },
            ],
        }],
    }
    clean = normalize_catalogue(data)
    assert validate_catalogue(clean) == []
    product = clean["products"][0]
    assert product["name"] == "Classic Burger"
    assert [g["key"] for g in product["options"]] == ["cuisson", "retirer_garniture", "supplements"]
    assert product_unit_price(product, {
        "cuisson": [{"name": "À point", "price": 0}],
        "retirer_garniture": [{"name": "Sans tomate", "price": 0}],
        "supplements": [{"name": "Avocat", "price": 2}],
    }) == 14


def test_uber_deliveroo_markup_is_channel_only():
    product = {
        "id": "classic-burger",
        "name": "Classic Burger",
        "category": "Burger",
        "price": 12,
        "options": [{
            "key": "supplements",
            "title": "Suppléments",
            "max": 0,
            "priceMode": "extra",
            "choices": [["Avocat", 2]],
        }],
    }
    selections = {"supplements": [{"name": "Avocat", "price": 2}]}
    assert product_unit_price(product, selections, channel="CAISSE") == 14
    assert product_unit_price(product, selections, channel="UBER EATS") == 16.10
    assert product_unit_price(product, selections, channel="DELIVEROO") == 16.10
