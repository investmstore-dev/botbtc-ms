"""
Bybit V5 API Connector — BTCUSDT Perpetuo
Soporta Demo Trading (api-demo.bybit.com) y Live (api.bybit.com)
Carga credenciales desde .env
"""
import hashlib
import hmac
import time
import os
import logging
import requests
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Cargar credenciales desde .env ────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

API_KEY    = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")
IS_DEMO    = os.environ.get("BYBIT_DEMO", "true").lower() == "true"

BASE_URL   = "https://api-demo.bybit.com" if IS_DEMO else "https://api.bybit.com"
RECV_WINDOW = "5000"

SYMBOL     = "BTCUSDT"
CATEGORY   = "linear"   # futuros perpetuos USDT


# ── Firma HMAC-SHA256 ─────────────────────────────────────────────────────────

def _sign(params_str: str) -> tuple[str, str]:
    ts = str(int(time.time() * 1000))
    payload = ts + API_KEY + RECV_WINDOW + params_str
    sig = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return ts, sig


def _headers(ts: str, sig: str) -> dict:
    return {
        "X-BAPI-API-KEY":     API_KEY,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-SIGN":        sig,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "Content-Type":       "application/json",
    }


def _get(path: str, params: dict) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    ts, sig = _sign(qs)
    r = requests.get(BASE_URL + path, params=params, headers=_headers(ts, sig), timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit GET {path} error: {data.get('retMsg')} | {data}")
    return data["result"]


def _post(path: str, body: dict) -> dict:
    import json
    body_str = json.dumps(body, separators=(",", ":"))
    ts, sig = _sign(body_str)
    r = requests.post(BASE_URL + path, data=body_str, headers=_headers(ts, sig), timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit POST {path} error: {data.get('retMsg')} | {data}")
    return data["result"]


# ── Cuenta ────────────────────────────────────────────────────────────────────

def get_account() -> dict:
    """Retorna balance y equity de la cuenta Unified."""
    try:
        result = _get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        coin_list = result["list"][0]["coin"]
        usdt = next((c for c in coin_list if c["coin"] == "USDT"), None)
        if usdt:
            balance = float(usdt.get("walletBalance", 0))
            equity  = float(usdt.get("equity", balance))
            unrealized = float(usdt.get("unrealisedPnl", 0))
            return {
                "balance":     round(balance, 2),
                "equity":      round(equity, 2),
                "unrealized":  round(unrealized, 2),
                "login":       API_KEY[:8] + "...",
            }
    except Exception as e:
        logger.error("get_account error: %s", e)
    return {}


# ── Velas H1 ──────────────────────────────────────────────────────────────────

def get_candles(symbol: str, timeframe: str, count: int = 400) -> pd.DataFrame | None:
    """
    Descarga velas desde Bybit.
    timeframe: '60' (H1), '240' (H4), 'D' (diario)
    """
    tf_map = {"H1": "60", "H4": "240", "D": "D", "60": "60", "240": "240"}
    interval = tf_map.get(timeframe, "60")
    try:
        result = _get("/v5/market/kline", {
            "category": CATEGORY,
            "symbol":   symbol,
            "interval": interval,
            "limit":    min(count, 1000),
        })
        rows = result.get("list", [])
        if not rows:
            return None
        # Bybit retorna [startTime, open, high, low, close, volume, turnover]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        df["ts"]    = pd.to_datetime(df["ts"].astype(float), unit="ms", utc=True)
        df.set_index("ts", inplace=True)
        df.index    = df.index.tz_convert(None)  # UTC naive
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df.sort_index(inplace=True)
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.error("get_candles error: %s", e)
        return None


# ── Posiciones abiertas ───────────────────────────────────────────────────────

def get_open_positions(symbol: str) -> list[dict]:
    """Retorna lista de posiciones abiertas para el símbolo."""
    try:
        result = _get("/v5/position/list", {
            "category": CATEGORY,
            "symbol":   symbol,
        })
        positions = []
        for p in result.get("list", []):
            size = float(p.get("size", 0))
            if size == 0:
                continue
            side = p.get("side", "").lower()  # "Buy" o "Sell"
            positions.append({
                "ticket":    p.get("positionIdx", 0),
                "type":      "long" if side == "buy" else "short",
                "size":      size,
                "entry":     float(p.get("avgPrice", 0)),
                "sl":        float(p.get("stopLoss", 0)),
                "tp":        float(p.get("takeProfit", 0)),
                "unrealized": float(p.get("unrealisedPnl", 0)),
                "symbol":    symbol,
            })
        return positions
    except Exception as e:
        logger.error("get_open_positions error: %s", e)
        return []


# ── Abrir orden ───────────────────────────────────────────────────────────────

def open_order(symbol: str, order_type: str, lot: float,
               sl: float, tp: float, comment: str = "BotBTC") -> dict:
    """
    Abre una orden de mercado con SL y TP.
    order_type: 'long' o 'short'
    lot: cantidad en BTC (ej: 0.01)
    """
    side = "Buy" if order_type == "long" else "Sell"
    try:
        result = _post("/v5/order/create", {
            "category":    CATEGORY,
            "symbol":      symbol,
            "side":        side,
            "orderType":   "Market",
            "qty":         str(round(lot, 4)),
            "stopLoss":    str(round(sl, 2)),
            "takeProfit":  str(round(tp, 2)),
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice",
            "timeInForce": "IOC",
            "orderLinkId": f"{comment}_{int(time.time())}",
        })
        order_id = result.get("orderId", "")
        logger.info("Orden abierta: %s %s qty=%.4f sl=%.2f tp=%.2f | id=%s",
                    side, symbol, lot, sl, tp, order_id)
        return {"ticket": order_id, "side": side}
    except Exception as e:
        logger.error("open_order error: %s", e)
        return {"error": str(e)}


# ── Modificar SL (trailing) ───────────────────────────────────────────────────

def modify_sl(symbol: str, position_type: str, new_sl: float) -> bool:
    """
    Actualiza el Stop Loss de la posición abierta via Trading Stop.
    Bybit no usa ticket para posiciones en modo hedge/one-way; se identifica por symbol+side.
    """
    side = "Buy" if position_type == "long" else "Sell"
    try:
        _post("/v5/position/trading-stop", {
            "category":    CATEGORY,
            "symbol":      symbol,
            "side":        side,
            "stopLoss":    str(round(new_sl, 2)),
            "slTriggerBy": "LastPrice",
            "positionIdx": 0,   # one-way mode
        })
        logger.debug("SL actualizado %s: %.2f", side, new_sl)
        return True
    except Exception as e:
        logger.error("modify_sl error: %s", e)
        return False


# ── Cerrar posición ───────────────────────────────────────────────────────────

def close_position(position: dict) -> bool:
    """
    Cierra la posición con una orden de mercado reduceOnly.
    position: dict retornado por get_open_positions()
    """
    symbol   = position.get("symbol", SYMBOL)
    pos_type = position.get("type", "long")
    size     = position.get("size", 0)

    # Para cerrar un long se vende, para cerrar un short se compra
    close_side = "Sell" if pos_type == "long" else "Buy"

    try:
        result = _post("/v5/order/create", {
            "category":   CATEGORY,
            "symbol":     symbol,
            "side":       close_side,
            "orderType":  "Market",
            "qty":        str(round(size, 4)),
            "reduceOnly": True,
            "timeInForce": "IOC",
            "orderLinkId": f"close_{int(time.time())}",
        })
        logger.info("Posicion cerrada: %s %s size=%.4f", close_side, symbol, size)
        return True
    except Exception as e:
        logger.error("close_position error: %s", e)
        return False


# ── Precio actual ─────────────────────────────────────────────────────────────

def get_ticker(symbol: str) -> float:
    """Retorna el último precio de mercado."""
    try:
        result = _get("/v5/market/tickers", {
            "category": CATEGORY,
            "symbol":   symbol,
        })
        return float(result["list"][0]["lastPrice"])
    except Exception as e:
        logger.error("get_ticker error: %s", e)
        return 0.0


# ── Test de conexión ──────────────────────────────────────────────────────────

def test_connection() -> bool:
    """Verifica que la API Key funciona y muestra el estado de la cuenta."""
    print()
    print("=" * 55)
    env_label = "DEMO TRADING" if IS_DEMO else "LIVE"
    print(f"  Bybit Connector — {env_label}")
    print(f"  Base URL: {BASE_URL}")
    print("=" * 55)

    if not API_KEY or not API_SECRET:
        print("  ERROR: BYBIT_API_KEY o BYBIT_API_SECRET no configurados en .env")
        return False

    # Ping publico
    try:
        r = requests.get(BASE_URL + "/v5/market/time", timeout=5)
        ts = r.json().get("result", {}).get("timeSecond", "?")
        print(f"  Servidor Bybit OK | Server time: {ts}")
    except Exception as e:
        print(f"  ERROR al conectar con Bybit: {e}")
        return False

    # Cuenta
    account = get_account()
    if not account:
        print("  ERROR: No se pudo obtener la cuenta. Verificar API Key y permisos.")
        return False

    print(f"  API Key   : {API_KEY[:8]}...")
    print(f"  Balance   : ${account['balance']:,.2f} USDT")
    print(f"  Equity    : ${account['equity']:,.2f} USDT")
    print(f"  Unrealized: ${account['unrealized']:+,.2f} USDT")

    # Precio BTC
    price = get_ticker(SYMBOL)
    print(f"  BTC precio: ${price:,.2f}")

    # Posiciones
    positions = get_open_positions(SYMBOL)
    print(f"  Posiciones abiertas: {len(positions)}")
    for p in positions:
        print(f"    {p['type'].upper()} {p['size']} BTC @ ${p['entry']:,.2f}"
              f"  SL=${p['sl']:,.2f}  TP=${p['tp']:,.2f}"
              f"  PnL=${p['unrealized']:+,.2f}")

    # Velas
    df = get_candles(SYMBOL, "H1", count=5)
    if df is not None:
        print(f"  Velas H1 OK ({len(df)} recibidas)")
        print(f"  Ultima vela: {df.index[-1]}  close=${df['close'].iloc[-1]:,.2f}")
    else:
        print("  ERROR obteniendo velas")
        return False

    print()
    print("  Conexion verificada correctamente.")
    print("=" * 55)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    ok = test_connection()
    exit(0 if ok else 1)
