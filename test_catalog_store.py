import os
import tempfile

from catalog_core import normalize_catalogue
from catalog_store import CatalogStore


def sample_catalogue():
    return normalize_catalogue({
        "categories": [
            {"id": "entrees", "name": "Entrées", "active": True, "order": 1},
            {"id": "midi", "name": "Formules MIDI", "active": True, "order": 2},
        ],
        "products": [{
            "id": "tender",
            "name": "Tender Chicken Maison",
            "category": "Entrées",
            "price": 8,
            "active": True,
            "channels": {"caisse": True, "site": True, "ubereats": True, "deliveroo": True},
            "options": [{
                "key": "nombre_tender",
                "title": "Nombre de Tender",
                "required": True,
                "max": 1,
                "priceMode": "absolute",
                "choices": [["5 pièces", 8], ["10 pièces", 15]],
            }],
        }],
        "optionLists": {
            "nombre_tender": [["5 pièces", 8], ["10 pièces", 15]],
        },
        "optionListDefs": {
            "nombre_tender": {"title": "Nombre de Tender", "max": 1, "required": True, "priceMode": "absolute"},
        },
    })


def test_sqlite_v2_roundtrip_keeps_options_and_category():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "catalog.db")
        store = CatalogStore(postgres_url="", sqlite_path=path)
        data = sample_catalogue()
        store.save(data)
        loaded, updated_at, schema_version = store.load()
        assert updated_at > 0
        assert schema_version == 1
        assert loaded["products"][0]["category"] == "Entrées"
        assert loaded["products"][0]["options"][0]["priceMode"] == "absolute"
        assert loaded["optionLists"]["nombre_tender"][1][1] == 15


def test_category_move_is_persistence_only_not_code_mutation():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "catalog.db")
        store = CatalogStore(postgres_url="", sqlite_path=path)
        data = sample_catalogue()
        data["products"][0]["category"] = "Formules MIDI"
        store.save(data)
        loaded, _, _ = store.load()
        assert loaded["products"][0]["category"] == "Formules MIDI"
        assert loaded["products"][0]["name"] == "Tender Chicken Maison"


def test_v2_table_does_not_overwrite_legacy_table():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "catalog.db")
        store = CatalogStore(postgres_url="", sqlite_path=path)
        store.save(sample_catalogue())
        import sqlite3
        conn = sqlite3.connect(path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "catalog_admin_v2" in tables
        assert "catalog_admin" not in tables
