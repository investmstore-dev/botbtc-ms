"""
MT5Broker — implementa la interfaz Broker sobre MetaTrader 5 (ADN Broker).
Crypto CFD (sin funding rate). Requiere el paquete 'MetaTrader5' y el terminal
MT5 instalado y abierto en el mismo PC (solo Windows).

NOTA: este conector se valida en el PC destino (necesita terminal MT5 + cuenta ADN).
Los nombres de simbolos dependen de ADN (ej. 'BTCUSD'); se configuran por cuenta.
"""
import logging
import pandas as pd

from utils.brokers.base import Broker

logger = logging.getLogger(__name__)

# Import perezoso: MetaTrader5 solo existe en Windows con el paquete instalado.
try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except Exception:
    mt5 = None
    _MT5_AVAILABLE = False


class MT5Broker(Broker):
    name = "mt5"

    _TF = {"H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4", "D": "TIMEFRAME_D1",
           "60": "TIMEFRAME_H1", "240": "TIMEFRAME_H4"}

    def __init__(self, login: int, password: str, server: str, demo: bool = False,
                 path: str | None = None):
        self.login = login
        self.password = password
        self.server = server
        self.is_demo = demo
        self.path = path   # ruta a terminal64.exe (necesaria si hay varios terminales)

    @staticmethod
    def _find_terminal(server: str) -> str | None:
        """Busca un terminal64.exe instalado. Prioriza uno cuyo nombre sugiera ADN."""
        import glob
        candidates = []
        for base in (r"C:\Program Files", r"C:\Program Files (x86)"):
            candidates += glob.glob(base + r"\*\terminal64.exe")
        if not candidates:
            return None
        # preferir uno que mencione ADN; si no, el "MetaTrader 5" generico
        for c in candidates:
            if "adn" in c.lower():
                return c
        for c in candidates:
            if c.lower().rstrip("\\").endswith(r"metatrader 5\terminal64.exe"):
                return c
        return candidates[0]

    # ── Conexion ──────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        if not _MT5_AVAILABLE:
            logger.error("Paquete MetaTrader5 no disponible (instalar en Windows).")
            return False
        path = self.path or self._find_terminal(self.server)
        kwargs = {"login": self.login, "password": self.password,
                  "server": self.server, "timeout": 15000}
        if path:
            kwargs["path"] = path
        if not mt5.initialize(**kwargs):
            logger.error("MT5 initialize fallo (path=%s): %s", path, mt5.last_error())
            return False
        return mt5.account_info() is not None

    def get_account(self) -> dict:
        if not _MT5_AVAILABLE:
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "balance":    round(info.balance, 2),
            "equity":     round(info.equity, 2),
            "unrealized": round(info.profit, 2),
            "login":      str(info.login),
        }

    def _server_utc_offset_sec(self, symbol) -> int:
        """Offset (segundos) entre la hora del servidor MT5 y UTC real, redondeado
        a la hora. Muchos brokers (ADN = UTC+3) reportan velas en hora del servidor."""
        import time as _t
        tick = mt5.symbol_info_tick(symbol)
        if not tick or not tick.time:
            return 0
        return round((tick.time - _t.time()) / 3600) * 3600

    # ── Datos de mercado ──────────────────────────────────────────────────────
    def get_candles(self, symbol, timeframe, count=400):
        if not _MT5_AVAILABLE:
            return None
        tf = getattr(mt5, self._TF.get(timeframe, "TIMEFRAME_H1"))
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.error("MT5 sin velas para %s: %s", symbol, mt5.last_error())
            return None
        df = pd.DataFrame(rates)
        df["ts"] = pd.to_datetime(df["time"], unit="s")
        # Convertir de hora del servidor MT5 a UTC real (alinea ORB/horarios con Bybit)
        off = self._server_utc_offset_sec(symbol)
        if off:
            df["ts"] = df["ts"] - pd.Timedelta(seconds=off)
        df.set_index("ts", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    def get_ticker(self, symbol):
        if not _MT5_AVAILABLE:
            return 0.0
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            return 0.0
        return float(t.bid or t.last or 0.0)

    def get_instrument_filters(self, symbol):
        if not _MT5_AVAILABLE:
            return {"qty_step": 0.01, "min_qty": 0.01, "tick_size": 0.01}
        s = mt5.symbol_info(symbol)
        if s is None:
            return {"qty_step": 0.01, "min_qty": 0.01, "tick_size": 0.01}
        return {
            "qty_step":  float(s.volume_step),
            "min_qty":   float(s.volume_min),
            "tick_size": float(s.trade_tick_size or s.point),
        }

    # ── Posiciones / ordenes ──────────────────────────────────────────────────
    def get_open_positions(self, symbol):
        if not _MT5_AVAILABLE:
            return []
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return []
        out = []
        for p in positions:
            out.append({
                "ticket":     p.ticket,
                "type":       "long" if p.type == mt5.POSITION_TYPE_BUY else "short",
                "size":       float(p.volume),
                "entry":      float(p.price_open),
                "sl":         float(p.sl),
                "tp":         float(p.tp),
                "unrealized": float(p.profit),
                "symbol":     symbol,
            })
        return out

    def _round(self, symbol, value, kind):
        f = self.get_instrument_filters(symbol)
        step = f["qty_step"] if kind == "qty" else f["tick_size"]
        if step <= 0:
            return value
        return round(round(value / step) * step, 8)

    def open_order(self, symbol, order_type, lot, sl, tp, comment="Bot"):
        if not _MT5_AVAILABLE:
            return {"error": "MT5 no disponible"}
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"error": f"Simbolo {symbol} no encontrado en MT5"}
        if not info.visible:
            mt5.symbol_select(symbol, True)
        side = mt5.ORDER_TYPE_BUY if order_type == "long" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if order_type == "long" else tick.bid
        req = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       self._round(symbol, lot, "qty"),
            "type":         side,
            "price":        price,
            "sl":           self._round(symbol, sl, "price"),
            "tp":           self._round(symbol, tp, "price"),
            "deviation":    20,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time":    mt5.ORDER_TIME_GTC,
            "comment":      comment[:31],
        }
        r = mt5.order_send(req)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            return {"error": f"order_send: {getattr(r, 'retcode', '?')} {mt5.last_error()}"}
        return {"ticket": r.order, "side": order_type}

    def modify_sl(self, symbol, position_type, new_sl):
        if not _MT5_AVAILABLE:
            return False
        for p in (mt5.positions_get(symbol=symbol) or []):
            ptype = "long" if p.type == mt5.POSITION_TYPE_BUY else "short"
            if ptype != position_type:
                continue
            req = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   symbol,
                "position": p.ticket,
                "sl":       self._round(symbol, new_sl, "price"),
                "tp":       float(p.tp),
            }
            r = mt5.order_send(req)
            return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE
        return False

    def close_position(self, position):
        if not _MT5_AVAILABLE:
            return False
        symbol = position.get("symbol")
        ticket = position.get("ticket")
        size   = position.get("size", 0)
        is_long = position.get("type") == "long"
        tick = mt5.symbol_info_tick(symbol)
        req = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(size),
            "type":         mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
            "position":     ticket,
            "price":        tick.bid if is_long else tick.ask,
            "deviation":    20,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time":    mt5.ORDER_TIME_GTC,
            "comment":      "close",
        }
        r = mt5.order_send(req)
        return r is not None and r.retcode == mt5.TRADE_RETCODE_DONE

    def get_closed_pnl(self, symbol, limit=1):
        if not _MT5_AVAILABLE:
            return []
        from datetime import datetime, timedelta
        deals = mt5.history_deals_get(datetime.now() - timedelta(days=2), datetime.now())
        if not deals:
            return []
        outs = [d for d in deals if d.symbol == symbol and d.entry == mt5.DEAL_ENTRY_OUT]
        outs = sorted(outs, key=lambda d: d.time, reverse=True)[:limit]
        return [{
            "type":      "long" if d.type == mt5.DEAL_TYPE_SELL else "short",
            "qty":       float(d.volume),
            "entry":     0.0,
            "exit":      float(d.price),
            "pnl":       float(d.profit),
            "order_id":  d.order,
            "closed_at": int(d.time) * 1000,
        } for d in outs]

    def has_funding(self) -> bool:
        return False   # CFD: sin funding rate
