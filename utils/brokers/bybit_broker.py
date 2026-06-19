"""
BybitBroker — implementa la interfaz Broker sobre la API V5 de Bybit.
Usado por las cuentas tipo CFT (Crypto Fund Trader). Crypto perpetuo USDT.
Reutiliza la logica ya probada de utils/bybit_connector.
"""
from utils.brokers.base import Broker
from utils import bybit_connector as bc


class BybitBroker(Broker):
    name = "bybit"

    def __init__(self, api_key: str, api_secret: str, demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_demo = demo

    def connect(self) -> bool:
        bc.configure(self.api_key, self.api_secret, self.is_demo)
        return bool(bc.get_account())

    def get_account(self) -> dict:
        return bc.get_account()

    def get_candles(self, symbol, timeframe, count=400):
        return bc.get_candles(symbol, timeframe, count)

    def get_ticker(self, symbol):
        return bc.get_ticker(symbol)

    def get_instrument_filters(self, symbol):
        return bc.get_instrument_filters(symbol)

    def get_open_positions(self, symbol):
        return bc.get_open_positions(symbol)

    def open_order(self, symbol, order_type, lot, sl, tp, comment="Bot"):
        return bc.open_order(symbol, order_type, lot, sl, tp, comment)

    def modify_sl(self, symbol, position_type, new_sl):
        return bc.modify_sl(symbol, position_type, new_sl)

    def close_position(self, position):
        return bc.close_position(position)

    def get_closed_pnl(self, symbol, limit=1):
        return bc.get_closed_pnl(symbol, limit)

    def has_funding(self) -> bool:
        return True   # Bybit perp si tiene funding rate
