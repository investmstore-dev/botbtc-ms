"""
Gestor de cuentas — multi-broker.
Acepta SOLO dos tipos de cuenta (por ahora):
  - CFT : Crypto Fund Trader  -> broker Bybit (crypto perp USDT)
  - ADN : ADN Broker          -> broker MetaTrader 5 (crypto CFD)

Persiste la config en data/accounts.json (NO se versiona; va en .gitignore).
La pantalla de setup del dashboard escribe aqui via el backend.
"""
import os
import json
import tempfile

import config

ACCOUNTS_FILE = os.path.join(config.DATA_DIR, "accounts.json")

# Tipos de cuenta permitidos -> broker que los maneja
ACCOUNT_TYPES = {
    "CFT": {"broker": "bybit", "label": "Crypto Fund Trader (Bybit)",
            "fields": ["api_key", "api_secret"],
            "default_symbols": ["BTCUSDT", "DOGEUSDT"]},
    "ADN": {"broker": "mt5",   "label": "ADN Broker (MetaTrader 5)",
            "fields": ["login", "password", "server"],
            "default_symbols": ["BTCUSD"]},
}


def default_symbols(acc_type: str) -> list:
    return ACCOUNT_TYPES.get(acc_type.upper(), {}).get("default_symbols", [])


# ── Persistencia ──────────────────────────────────────────────────────────────
def load_accounts() -> dict:
    if not os.path.exists(ACCOUNTS_FILE):
        return {"active": None, "accounts": {}}
    try:
        with open(ACCOUNTS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"active": None, "accounts": {}}


def _save(data: dict):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    d = os.path.dirname(ACCOUNTS_FILE)
    with tempfile.NamedTemporaryFile("w", dir=d, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tmp = tf.name
    os.replace(tmp, ACCOUNTS_FILE)


# ── Validacion ────────────────────────────────────────────────────────────────
def validate_config(cfg: dict) -> tuple[bool, str]:
    """Valida estructura y tipo. NO prueba conexion (eso lo hace test_connection)."""
    acc_type = cfg.get("type", "").upper()
    if acc_type not in ACCOUNT_TYPES:
        return False, (f"Tipo '{acc_type}' no permitido. "
                       f"Solo se aceptan: {', '.join(ACCOUNT_TYPES)}.")
    required = ACCOUNT_TYPES[acc_type]["fields"]
    missing = [f for f in required if not cfg.get(f)]
    if missing:
        return False, f"Faltan campos para {acc_type}: {', '.join(missing)}"
    return True, "OK"


def test_connection(cfg: dict) -> tuple[bool, str]:
    """Construye el broker y verifica que conecta + trae balance."""
    ok, msg = validate_config(cfg)
    if not ok:
        return ok, msg
    try:
        broker = _build_broker(cfg)
        if not broker.connect():
            return False, "No se pudo conectar / autenticar con el broker."
        acc = broker.get_account()
        if not acc:
            return False, "Conecto pero no devolvio balance. Revisar permisos/cuenta."
        return True, f"OK | balance ${acc.get('balance', 0):,.2f}"
    except Exception as e:
        return False, f"Error: {e}"


# ── CRUD ──────────────────────────────────────────────────────────────────────
def add_account(account_id: str, cfg: dict) -> tuple[bool, str]:
    ok, msg = validate_config(cfg)
    if not ok:
        return ok, msg
    data = load_accounts()
    cfg["type"] = cfg["type"].upper()
    cfg["broker"] = ACCOUNT_TYPES[cfg["type"]]["broker"]
    if not cfg.get("symbols"):
        cfg["symbols"] = default_symbols(cfg["type"])
    data["accounts"][account_id] = cfg
    if data.get("active") is None:
        data["active"] = account_id
    _save(data)
    return True, f"Cuenta '{account_id}' guardada."


def set_active(account_id: str) -> tuple[bool, str]:
    data = load_accounts()
    if account_id not in data["accounts"]:
        return False, f"No existe la cuenta '{account_id}'."
    data["active"] = account_id
    _save(data)
    return True, f"Cuenta activa: {account_id}"


def get_active_account() -> dict | None:
    data = load_accounts()
    active = data.get("active")
    if active and active in data["accounts"]:
        acc = {"id": active, **data["accounts"][active]}
        if not acc.get("symbols"):
            acc["symbols"] = default_symbols(acc.get("type", ""))
        return acc
    # Fallback de migracion: usar .env si hay credenciales Bybit y no hay cuentas
    if not data["accounts"]:
        from utils import bybit_connector as bc
        if bc.API_KEY and bc.API_SECRET:
            return {"id": "env_cft", "type": "CFT", "broker": "bybit",
                    "api_key": bc.API_KEY, "api_secret": bc.API_SECRET,
                    "demo": bc.IS_DEMO, "name": "CFT (.env)",
                    "symbols": default_symbols("CFT")}
    return None


# ── Construccion del broker ───────────────────────────────────────────────────
def _build_broker(cfg: dict):
    broker = cfg.get("broker") or ACCOUNT_TYPES.get(cfg.get("type", "").upper(), {}).get("broker")
    if broker == "bybit":
        from utils.brokers.bybit_broker import BybitBroker
        return BybitBroker(cfg["api_key"], cfg["api_secret"], cfg.get("demo", True))
    if broker == "mt5":
        from utils.brokers.mt5_broker import MT5Broker
        return MT5Broker(int(cfg["login"]), cfg["password"], cfg["server"],
                         cfg.get("demo", False))
    raise ValueError(f"Broker desconocido: {broker}")


def get_active_broker():
    """Retorna una instancia Broker conectada de la cuenta activa, o None."""
    cfg = get_active_account()
    if not cfg:
        return None
    broker = _build_broker(cfg)
    broker.connect()
    return broker
