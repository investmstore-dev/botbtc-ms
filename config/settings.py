# BOT Mining Store -- Configuracion
# Estrategia: ORB + MACD/RSI + Supertrend H4 + Choppiness Index | H1
# Cuenta: Crypto Fund Trader Challenge $10k
# Version: v6 multi-par (BTC v5b + DOGE config-D) | modo SINGLE
#
# Backtest portafolio 2y (BTC+DOGE, 1 posicion a la vez):
#   +78.5% | DD -8.0% | PF 1.76 | 6 challenges

import os

# ── Instancia (para correr varios bots en el mismo PC) ────────────────────────
# MS_DATA_DIR    : carpeta de datos propia (default "data")
# MS_PORT_OFFSET : desplazamiento de puertos (default 0)
# MS_LOG_FILE    : archivo de log propio (default "botbtc.log")
INSTANCE       = os.environ.get("MS_INSTANCE", "")
PORT_OFFSET    = int(os.environ.get("MS_PORT_OFFSET", "0"))
PORT_DASHBOARD = 8090 + PORT_OFFSET
PORT_DATA      = 8091 + PORT_OFFSET
PORT_CONTROL   = 8092 + PORT_OFFSET
LOG_FILE       = os.environ.get("MS_LOG_FILE", "botbtc.log")

TIMEFRAME = "H1"

# ── Pares operados (simbolos Bybit linear USDT-perpetuo) ──────────────────────
# El orden define la prioridad cuando ambos dan senal en modo SINGLE.
SYMBOLS   = ["BTCUSDT", "DOGEUSDT"]
RISK_MODE = "single"   # 'single' = max 1 posicion a la vez entre TODOS los pares

# ── Riesgo y filtros POR PAR ──────────────────────────────────────────────────
# BTCUSDT  -> v5b original
# DOGEUSDT -> config-D optimizada (DD-guard agresivo para no violar el -10% CFT)
SYMBOL_CONFIGS = {
    "BTCUSDT": {
        "risk_trend":   0.018,  # CHOP H4 < 48
        "risk_neutral": 0.010,  # CHOP H4 48-57
        "risk_choppy":  0.005,  # CHOP H4 > 57
        "dd_lo": 0.04, "dd_lo_risk": 0.008,   # si DD>=4% -> max 0.8%
        "dd_hi": 0.06, "dd_hi_risk": 0.005,   # si DD>=6% -> max 0.5%
        "adx_min": 22, "adx_choppy": 28,
    },
    "DOGEUSDT": {
        "risk_trend":   0.014,
        "risk_neutral": 0.008,
        "risk_choppy":  0.004,
        "dd_lo": 0.03, "dd_lo_risk": 0.006,   # freno mas temprano (3%)
        "dd_hi": 0.05, "dd_hi_risk": 0.003,   # y mas duro (5%)
        "adx_min": 22, "adx_choppy": 28,
    },
    # AVAXUSDT (Bybit/CFT): config-D, ver model/scan_pairs.py
    "AVAXUSDT": {
        "risk_trend":   0.014, "risk_neutral": 0.008, "risk_choppy": 0.004,
        "dd_lo": 0.03, "dd_lo_risk": 0.006, "dd_hi": 0.05, "dd_hi_risk": 0.003,
        "adx_min": 22, "adx_choppy": 28,
    },
    # BTCUSD (ADN/MT5): BTC-only SIN sentimiento -> DD-guard agresivo + riesgo
    # reducido (sin diversificacion, hay que proteger mas la cuenta).
    "BTCUSD": {
        "risk_trend":   0.012, "risk_neutral": 0.007, "risk_choppy": 0.004,
        "dd_lo": 0.03, "dd_lo_risk": 0.006, "dd_hi": 0.05, "dd_hi_risk": 0.003,
        "adx_min": 22, "adx_choppy": 28,
    },
}

# Config por defecto si un simbolo no esta en SYMBOL_CONFIGS
DEFAULT_SYMBOL_CONFIG = {
    "risk_trend": 0.012, "risk_neutral": 0.007, "risk_choppy": 0.004,
    "dd_lo": 0.03, "dd_lo_risk": 0.006, "dd_hi": 0.05, "dd_hi_risk": 0.003,
    "adx_min": 22, "adx_choppy": 28,
}


def symbol_config(symbol: str) -> dict:
    return SYMBOL_CONFIGS.get(symbol, DEFAULT_SYMBOL_CONFIG)


# Defaults (fallback si un par no esta en SYMBOL_CONFIGS)
ADX_MIN        = 22
ADX_CHOPPY_MIN = 28

# ── Supertrend H4 ─────────────────────────────────────────────────────────────
ST_PERIOD = 10
ST_MULT   = 3.0
# dir=+1 (GREEN) -> solo LONGS permitidos | dir=-1 (RED) -> solo SHORTS

# ── Choppiness Index H4 ───────────────────────────────────────────────────────
CHOP_PERIOD     = 14
CHOP_TREND_MAX  = 48   # por debajo: mercado en tendencia
CHOP_CHOPPY_MIN = 57   # por encima: mercado choppy/lateral

# ── Indicadores H1 ────────────────────────────────────────────────────────────
EMA_FAST    = 20
EMA_SLOW    = 50
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9
RSI_PERIOD  = 14
ATR_PERIOD  = 14
ADX_PERIOD  = 14

# ── Filtros de entrada ────────────────────────────────────────────────────────
RSI_LONG_MIN   = 35
RSI_LONG_MAX   = 75
RSI_SHORT_MIN  = 25
RSI_SHORT_MAX  = 65

# ── Filtros de sentimiento externo ────────────────────────────────────────────
FUND_LONG_MIN   = -0.0003
FUND_SHORT_MAX  =  0.00005
FUND_SHORT_MIN  = -0.0004
FG_LONG_MIN    = 35
FG_SHORT_MIN   = 10
FG_SHORT_MAX   = 70

# ── Opening Range Breakout (ORB) ──────────────────────────────────────────────
ORB_HOUR_START    = 0
ORB_HOUR_END      = 4
ORB_HOUR_CLOSE    = 20
ORB_MIN_RANGE_PCT = 0.003

# ── Gestion de posicion ───────────────────────────────────────────────────────
ATR_SL_MULT    = 1.2
ATR_TRAIL_MULT = 1.0
TP_RR          = 2.2
ATR_VOL_MULT   = 1.8
MAX_POSITIONS  = 1     # modo SINGLE

# ── Crypto Fund Trader rules ──────────────────────────────────────────────────
CFT_TARGET_PCT   = 0.08
CFT_PHASE2_PCT   = 0.05
CFT_MAX_DD_PCT   = 0.10
CFT_DAILY_DD_PCT = 0.05

# ── Archivos de estado para el dashboard (carpeta por instancia) ─────────────
DATA_DIR    = os.environ.get("MS_DATA_DIR", "data")
STATE_FILE  = os.path.join(DATA_DIR, "state.json")
TRADES_FILE = os.path.join(DATA_DIR, "trades.json")
EQUITY_FILE = os.path.join(DATA_DIR, "equity.json")

# ── Datos de sentimiento (por instancia, dentro de DATA_DIR) ─────────────────
# Funding rate es POR PAR; Fear & Greed es macro. Se guardan en la carpeta de la
# instancia para que varias instancias no se pisen los archivos.
def funding_csv(symbol: str) -> str:
    return os.path.join(DATA_DIR, f"funding_{symbol}.csv")

FG_CSV = os.path.join(DATA_DIR, "fear_greed_index.csv")
