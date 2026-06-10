"""
Conector MT5 via archivos JSON para BTCUSD.
El EA BotBTC_Bridge.mq5 corre en MT5 y hace el puente.
"""
import json
import os
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MT5_COMMON = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "Common" / "Files"

CMD_FILE   = MT5_COMMON / "botbtc_command.json"
STATE_FILE = MT5_COMMON / "botbtc_state.json"
DONE_FILE  = MT5_COMMON / "botbtc_done.json"

_cmd_id = 0


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def connect() -> bool:
    logger.info("Verificando conexion con EA Bridge en: %s", MT5_COMMON)
    if not MT5_COMMON.exists():
        logger.error("Carpeta MT5 Common no encontrada: %s", MT5_COMMON)
        return False

    ok = _send_command({"action": "ping"}, timeout=5)
    if ok:
        logger.info("EA Bridge respondio — conexion OK")
        return True

    state = _read_json(STATE_FILE)
    if state.get("status") in ("running", "init"):
        logger.info("EA Bridge activo (status: %s)", state.get("status"))
        return True

    logger.warning("EA Bridge no responde. Asegurate de tener BotBTC_Bridge corriendo en MT5.")
    return False


def disconnect():
    logger.info("Conector desconectado")


def get_account() -> dict:
    state = _read_json(STATE_FILE)
    if not state:
        return {}
    return {
        "login":       state.get("login"),
        "balance":     state.get("balance", 0),
        "equity":      state.get("equity", 0),
        "margin":      state.get("margin", 0),
        "free_margin": state.get("free_margin", 0),
        "profit":      state.get("profit", 0),
        "currency":    state.get("currency", "USD"),
        "server":      state.get("server", ""),
    }


def get_candles(symbol: str, timeframe: str, count: int = 300):
    """Obtiene velas H1 de BTCUSD via yfinance."""
    import pandas as pd
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance no instalado. Ejecuta: pip install yfinance")
        return pd.DataFrame()

    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period="60d", interval="1h")
    if df.empty:
        return pd.DataFrame()

    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]]
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    return df.tail(count)


def get_open_positions(symbol: str) -> list:
    state = _read_json(STATE_FILE)
    positions = state.get("positions", [])
    return [p for p in positions if p.get("symbol") == symbol]


def open_order(symbol: str, order_type: str, lot: float,
               sl: float, tp: float, comment: str = "BotBTC") -> dict:
    action = "open_long" if order_type == "long" else "open_short"
    cmd = {
        "action": action,
        "symbol": symbol,
        "volume": lot,
        "sl":     round(sl, 2),
        "tp":     round(tp, 2),
    }
    result = _send_command(cmd, timeout=10)
    if result and result.get("result") == "ok":
        logger.info("Orden abierta: %s %s lot=%.3f sl=%.2f tp=%.2f",
                    order_type, symbol, lot, sl, tp)
        return {"ticket": result.get("retcode"), "lot": lot, "type": order_type}
    logger.error("Error abriendo orden: %s", result)
    return {"error": str(result)}


def modify_sl(ticket: int, new_sl: float) -> bool:
    cmd = {"action": "modify_sl", "ticket": ticket, "sl": round(new_sl, 2)}
    result = _send_command(cmd, timeout=5)
    return result.get("result") == "ok" if result else False


def close_position(position: dict) -> bool:
    cmd = {"action": "close", "ticket": position.get("ticket")}
    result = _send_command(cmd, timeout=10)
    return result.get("result") == "ok" if result else False


def _send_command(cmd: dict, timeout: int = 10) -> dict:
    global _cmd_id
    _cmd_id += 1
    cmd["id"] = _cmd_id

    _write_json(CMD_FILE, cmd)

    deadline = time.time() + timeout
    while time.time() < deadline:
        done = _read_json(DONE_FILE)
        if done.get("id") == _cmd_id:
            return done
        time.sleep(0.2)

    logger.warning("Timeout esperando respuesta del EA para comando id=%d", _cmd_id)
    return {}
