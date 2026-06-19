"""
Interfaz comun de broker. Toda integracion (Bybit, MT5/ADN) la implementa,
para que el bot opere igual sin importar el broker subyacente.
"""
from abc import ABC, abstractmethod
import pandas as pd


class Broker(ABC):
    name: str = "base"
    is_demo: bool = True

    # ── Conexion ──────────────────────────────────────────────────────────────
    @abstractmethod
    def connect(self) -> bool:
        """Inicializa la conexion. Retorna True si fue exitosa."""

    @abstractmethod
    def get_account(self) -> dict:
        """{balance, equity, unrealized, login} o {} si falla."""

    # ── Datos de mercado ──────────────────────────────────────────────────────
    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int = 400) -> "pd.DataFrame | None":
        """Velas OHLCV con indice datetime UTC-naive."""

    @abstractmethod
    def get_ticker(self, symbol: str) -> float:
        """Ultimo precio."""

    @abstractmethod
    def get_instrument_filters(self, symbol: str) -> dict:
        """{qty_step, min_qty, tick_size} para redondear cantidad y precio."""

    # ── Posiciones / ordenes ──────────────────────────────────────────────────
    @abstractmethod
    def get_open_positions(self, symbol: str) -> list:
        """Lista de posiciones abiertas del simbolo."""

    @abstractmethod
    def open_order(self, symbol: str, order_type: str, lot: float,
                   sl: float, tp: float, comment: str = "Bot") -> dict:
        """Abre orden de mercado con SL y TP. order_type: 'long'|'short'."""

    @abstractmethod
    def modify_sl(self, symbol: str, position_type: str, new_sl: float) -> bool:
        """Actualiza el stop loss de la posicion (trailing)."""

    @abstractmethod
    def close_position(self, position: dict) -> bool:
        """Cierra la posicion dada."""

    @abstractmethod
    def get_closed_pnl(self, symbol: str, limit: int = 1) -> list:
        """Ultimas posiciones cerradas con PnL realizado."""

    # ── Capacidades ───────────────────────────────────────────────────────────
    def has_funding(self) -> bool:
        """True si el broker provee funding rate (crypto perp). MT5/CFD = False."""
        return False
