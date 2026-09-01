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
