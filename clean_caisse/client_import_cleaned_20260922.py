"""Import one-shot des clients nettoyés du 22/09/2026.

Idempotent : un marqueur PostgreSQL empêche tout second import.
Les doublons sont rapprochés par téléphone lorsqu'il existe déjà.
"""
import time
import uuid

IMPORT_KEY = "clients_cleaned_2026_09_22_v1"

CLIENTS = [
  {
    "phone": "0603844975",
    "last_name": "abittan abittan",
    "first_name": "",
    "city": "nogent",
    "address": "2 rue de la libération",
    "door_intercom": "abittan"
  },
  {
    "phone": "0606586632",
    "last_name": "ethan abelac",
    "first_name": "",
    "city": "saint maurice",
    "address": "2 rue Jean gabin",
    "door_intercom": "villa 4"
  },
  {
    "phone": "0148760057",
    "last_name": "abitbol",
    "first_name": "",
    "city": "Fontenay",
    "address": "15 ave Rabelais",
    "door_intercom": ""
  },
  {
    "phone": "0678469533",
    "last_name": "abitbol",
    "first_name": "",
    "city": "rosny",
    "address": "144 rue de la cote des chenes",
    "door_intercom": ""
  },
  {
    "phone": "0782929130",
    "last_name": "abitbol",
    "first_name": "",
    "city": "vincennes",
    "address": "80 rue de france",
    "door_intercom": ""
  },
  {
    "phone": "0645986184",
    "last_name": "abitbol",
    "first_name": "Rudy",
    "city": "rosny",
    "address": "144 rue de la côte des chaine",
    "door_intercom": ""
  },
  {
    "phone": "0695454042",
    "last_name": "Alexandre",
    "first_name": "",
    "city": "perreux",
    "address": "2 rue de l orangerie",
    "door_intercom": ""
  },
  {
    "phone": "0676207197",
    "last_name": "abitbol",
    "first_name": "Joe",
    "city": "Neuilly plaisance",
    "address": "31 rue bourreau gueriniere",
    "door_intercom": ""
  },
  {
    "phone": "0618631493",
    "last_name": "Abittan",
    "first_name": "David",
    "city": "Fontenay",
    "address": "43 rue Gambetta",
    "door_intercom": ""
  },
  {
    "phone": "0665351212",
    "last_name": "aboujid",
    "first_name": "",
    "city": "",
    "address": "4 rue Édouard Beaulieu",
    "door_intercom": ""
  },
  {
    "phone": "0698492011",
    "last_name": "abtan",
    "first_name": "Nathanael",
    "city": "Fontenay sous bois",
    "address": "3 r pierre curie",
    "door_intercom": ""
  },
  {
    "phone": "0698902652",
    "last_name": "abtan",
    "first_name": "Yossi",
    "city": "Fontenay sous bois",
    "address": "3 rue pierre curie",
    "door_intercom": ""
  },
  {
    "phone": "0664276910",
    "last_name": "achache",
    "first_name": "",
    "city": "Nogent sur Marne",
    "address": "32 a de la belle Gabrielle",
    "door_intercom": ""
  },
  {
    "phone": "0762054661",
    "last_name": "adam",
    "first_name": "",
    "city": "",
    "address": "43 rue Edouard Maurice",
    "door_intercom": ""
  },
  {
    "phone": "0663595464",
    "last_name": "berros",
    "first_name": "Adam",
    "city": "Nogent sur Marne",
    "address": "9 rue des Clamarts",
    "door_intercom": "d 11"
  },
  {
    "phone": "0782407507",
    "last_name": "Adawi",
    "first_name": "Merav",
    "city": "Fontenay sous bois",
    "address": "17 rue george Guynemer",
    "door_intercom": "adawi"
  },
  {
    "phone": "0646190616",
    "last_name": "adda",
    "first_name": "",
    "city": "Nogent sur Marne",
    "address": "2 avenue du maréchal fayolle",
    "door_intercom": ""
  },
  {
    "phone": "0142392529",
    "last_name": "ADS artisan",
    "first_name": "",
    "city": "Fontenay sous bois",
    "address": "19 place de la libération",
    "door_intercom": ""
  },
  {
    "phone": "0622410956",
    "last_name": "Aferiat",
    "first_name": "Emile",
    "city": "Nogent sur Marne",
    "address": "4 bis du général Leclerc",
    "door_intercom": "aferiat"
  },
  {
    "phone": "0624532348",
    "last_name": "BSI agence bsi",
    "first_name": "",
    "city": "Fontenay sous bois",
    "address": "183 avenue de la république",
    "door_intercom": ""
  },
  {
    "phone": "0777754717",
    "last_name": "Aknin",
    "first_name": "Eva",
    "city": "Nogent sur Marne",
    "address": "6 rue du jeu de l arc",
    "door_intercom": "aknin"
  },
  {
    "phone": "0682420332",
    "last_name": "Akouka",
    "first_name": "Jérémie",
    "city": "Fontenay sous bois",
    "address": "34 bis rue des rieux",
    "door_intercom": "akouka"
  },
  {
    "phone": "0603061057",
    "last_name": "Alan",
    "first_name": "",
    "city": "Perreux",
    "address": "35 rue Victor recours",
    "door_intercom": ""
  },
  {
    "phone": "0637316375",
    "last_name": "alfon",
    "first_name": "",
    "city": "le Perreux",
    "address": "134 av du 8 mai 1945",
    "door_intercom": ""
  },
  {
    "phone": "0613134558",
    "last_name": "alfon",
    "first_name": "",
    "city": "Fontenay sous bois",
    "address": "23 rue roublot",
    "door_intercom": ""
  },
  {
    "phone": "0699302793",
    "last_name": "alleli",
    "first_name": "Dan",
    "city": "Nogent sur Marne",
    "address": "6 r brillet",
    "door_intercom": "36"
  },
  {
    "phone": "0777305738",
    "last_name": "Hallioua",
    "first_name": "Jean-Luc",
    "city": "les pavillons s bois",
    "address": "99 avenue du président Wilson",
    "door_intercom": ""
  },
  {
    "phone": "0603878018",
    "last_name": "alloj alloj",
    "first_name": "",
    "city": "Montreuil",
    "address": "155 rue de Rosny",
    "door_intercom": ""
  },
  {
    "phone": "0634240908",
    "last_name": "allouche",
    "first_name": "David",
    "city": "Nogent sur Marne",
    "address": "152 bvd de Strasbourg",
    "door_intercom": ""
  },
  {
    "phone": "0645571443",
    "last_name": "Jessica allouche",
    "first_name": "",
    "city": "Nogent sur Marne",
    "address": "117 bvd de Strasbourg",
    "door_intercom": "Lacroix lauga"
  },
  {
    "phone": "0783175669",
    "last_name": "ethan allouche",
    "first_name": "",
    "city": "Nogent sur Marne",
    "address": "24 bvd de la marne",
    "door_intercom": ""
  },
  {
    "phone": "0698194302",
    "last_name": "patricia allouche",
    "first_name": "",
    "city": "Neuilly plaisance",
    "address": "147 ave du maréchal Foch",
    "door_intercom": ""
  },
  {
    "phone": "0634227359",
    "last_name": "allioun",
    "first_name": "",
    "city": "Fontenay sous bois",
    "address": "21 rue roublot",
    "door_intercom": ""
  },
  {
    "phone": "0651460496",
    "last_name": "allioun",
    "first_name": "",
    "city": "Fontenay sois bois",
    "address": "21 rue roublot",
    "door_intercom": ""
  },
  {
    "phone": "0665528077",
    "last_name": "Gabriel allioun",
    "first_name": "",
    "city": "Rosny sous bois",
    "address": "37 ave du président joen Kennedy",
    "door_intercom": ""
  },
  {
    "phone": "065146",
    "last_name": "Raphaël aloun",
    "first_name": "",
    "city": "Fontenay sous bois",
    "address": "21 r roublot",
    "door_intercom": ""
  }
]


def import_cleaned_clients_once(db, ensure_order_schema):
    with db() as conn:
        ensure_order_schema(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bechefaa_data_imports (
                import_key TEXT PRIMARY KEY,
                imported_at BIGINT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()

        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (22092026,))
            done = conn.execute(
                "SELECT import_key FROM bechefaa_data_imports WHERE import_key=%s",
                (IMPORT_KEY,),
            ).fetchone()
            if done:
                return {"ok": True, "skipped": True, "count": 0}

            now = int(time.time() * 1000)
            count = 0
            for c in CLIENTS:
                phone = str(c.get("phone") or "").strip()
                first_name = str(c.get("first_name") or "").strip()
                last_name = str(c.get("last_name") or "").strip()
                address = str(c.get("address") or "").strip()
                city = str(c.get("city") or "").strip()
                door_intercom = str(c.get("door_intercom") or "").strip()
                display_name = " ".join(x for x in (first_name, last_name) if x).strip() or phone or "Client"

                existing = None
                if phone:
                    existing = conn.execute(
                        "SELECT id FROM caisse_clients WHERE phone=%s ORDER BY updated_at DESC LIMIT 1",
                        (phone,),
                    ).fetchone()

                if existing:
                    conn.execute(
                        """UPDATE caisse_clients
                           SET first_name=%s,last_name=%s,display_name=%s,
                               address=%s,city=%s,door_intercom=%s,updated_at=%s
                           WHERE id=%s""",
                        (
                            first_name, last_name, display_name,
                            address, city, door_intercom, now, existing["id"],
                        ),
                    )
                else:
                    client_id = "client-" + uuid.uuid4().hex
                    conn.execute(
                        """INSERT INTO caisse_clients
                           (id,first_name,last_name,display_name,phone,email,address,
                            postal_code,city,door_intercom,notes,created_at,updated_at)
                           VALUES (%s,%s,%s,%s,%s,'',%s,'',%s,%s,'',%s,%s)""",
                        (
                            client_id, first_name, last_name, display_name, phone,
                            address, city, door_intercom, now, now,
                        ),
                    )
                count += 1

            conn.execute(
                "INSERT INTO bechefaa_data_imports(import_key,imported_at,row_count) VALUES (%s,%s,%s)",
                (IMPORT_KEY, now, count),
            )

    return {"ok": True, "skipped": False, "count": count}
