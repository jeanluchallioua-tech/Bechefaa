"""Phase 4.4 — configuration matérielle générique BÉCHÉFAA.

Ce module ne pilote aucun périphérique directement depuis Clever Cloud.
Il stocke la configuration du poste de caisse afin qu'une passerelle locale
puisse ensuite exécuter les ordres d'impression / ouverture de tiroir.

Configuration BÉCHÉFAA de référence : Epson TM-m30 USB.
Le cœur reste générique : USB, réseau ou impression système ; tiroir via
imprimante ESC/POS, passerelle locale ou désactivé.
"""
from flask import jsonify, request

PRINTER_MODES = {"USB", "NETWORK", "SYSTEM"}
DRAWER_MODES = {"DISABLED", "PRINTER_ESCPOS", "LOCAL_BRIDGE"}


def register_hardware_config_phase44(app, db):
    def ensure_schema(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_hardware_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        defaults = {
            "printer_mode": "USB",
            "printer_brand": "EPSON",
            "printer_model": "TM-m30",
            "printer_name": "",
            "printer_host": "",
            "drawer_mode": "DISABLED",
            "drawer_open_on_cash": "1",
            "drawer_manual_pin_required": "1",
        }
        for key, value in defaults.items():
            conn.execute("""INSERT INTO caisse_hardware_config(config_key,config_value)
                            VALUES (%s,%s) ON CONFLICT (config_key) DO NOTHING""", (key, value))

    def read_config(conn):
        ensure_schema(conn)
        rows = conn.execute("SELECT config_key,config_value FROM caisse_hardware_config").fetchall()
        cfg = {r["config_key"]: r["config_value"] for r in rows}
        return {
            "printer": {
                "mode": cfg.get("printer_mode", "USB"),
                "brand": cfg.get("printer_brand", "EPSON"),
                "model": cfg.get("printer_model", "TM-m30"),
                "name": cfg.get("printer_name", ""),
                "host": cfg.get("printer_host", ""),
            },
            "drawer": {
                "mode": cfg.get("drawer_mode", "DISABLED"),
                "open_on_cash": cfg.get("drawer_open_on_cash", "1") == "1",
                "manual_pin_required": cfg.get("drawer_manual_pin_required", "1") == "1",
            },
            "capabilities": {
                "printer_modes": sorted(PRINTER_MODES),
                "drawer_modes": sorted(DRAWER_MODES),
                "local_bridge_required_for_usb": True,
            },
        }

    @app.get("/api/hardware/config-phase44")
    def hardware_config_get_phase44():
        try:
            with db() as conn:
                with conn.transaction():
                    data = read_config(conn)
            return jsonify({"ok": True, **data})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Configuration matériel indisponible", "detail": str(exc)}), 500

    @app.post("/api/hardware/config-phase44")
    def hardware_config_post_phase44():
        payload = request.get_json(silent=True) or {}
        printer = payload.get("printer") or {}
        drawer = payload.get("drawer") or {}
        printer_mode = str(printer.get("mode") or "USB").upper()
        drawer_mode = str(drawer.get("mode") or "DISABLED").upper()
        if printer_mode not in PRINTER_MODES:
            return jsonify({"ok": False, "error": "Mode imprimante invalide"}), 400
        if drawer_mode not in DRAWER_MODES:
            return jsonify({"ok": False, "error": "Mode tiroir invalide"}), 400
        values = {
            "printer_mode": printer_mode,
            "printer_brand": str(printer.get("brand") or "").strip()[:80],
            "printer_model": str(printer.get("model") or "").strip()[:80],
            "printer_name": str(printer.get("name") or "").strip()[:160],
            "printer_host": str(printer.get("host") or "").strip()[:160],
            "drawer_mode": drawer_mode,
            "drawer_open_on_cash": "1" if drawer.get("open_on_cash", True) else "0",
            "drawer_manual_pin_required": "1" if drawer.get("manual_pin_required", True) else "0",
        }
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_schema(conn)
                    for key, value in values.items():
                        conn.execute("""INSERT INTO caisse_hardware_config(config_key,config_value,updated_at)
                                        VALUES (%s,%s,NOW())
                                        ON CONFLICT (config_key) DO UPDATE
                                        SET config_value=EXCLUDED.config_value,updated_at=NOW()""", (key, value))
                    data = read_config(conn)
            return jsonify({"ok": True, **data})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Enregistrement matériel impossible", "detail": str(exc)}), 500

    @app.get("/api/hardware/capabilities-phase44")
    def hardware_capabilities_phase44():
        return jsonify({
            "ok": True,
            "printer_modes": sorted(PRINTER_MODES),
            "drawer_modes": sorted(DRAWER_MODES),
            "reference_printer": {"brand": "EPSON", "model": "TM-m30", "connection": "USB"},
            "rules": {
                "cash_payment_requests_drawer_open": True,
                "non_cash_payment_requests_drawer_open": False,
                "cloud_never_accesses_local_usb_directly": True,
            },
        })
