# BOT Mining Store BTC -- Configuracion
# Estrategia: ORB + MACD/RSI + Supertrend H4 + Choppiness Index | BTCUSD H1
# Cuenta: Crypto Fund Trader Challenge $10k
# Version: v5b (backtest 2y: +36.6%, DD=-7.8%, PF=1.59, Short PF=1.87)

MT5_LOGIN    = 0              # Reemplazar con login real CFT
MT5_PASSWORD = ""             # Reemplazar con password real CFT
MT5_SERVER   = "CryptoFundTrader-Live"

SYMBOL     = "BTCUSD"
TIMEFRAME  = "H1"

# ── Riesgo dinamico por regimen de mercado (Choppiness Index H4) ─────────────
# El bot detecta automaticamente el regimen y ajusta el riesgo
RISK_TREND   = 0.018   # CHOP H4 < 48 -> tendencia fuerte -> 1.8%
RISK_NEUTRAL = 0.010   # CHOP H4 48-57 -> mercado neutro -> 1.0%
RISK_CHOPPY  = 0.005   # CHOP H4 > 57 -> mercado lateral -> 0.5%

# Reduccion adicional si hay drawdown acumulado
RISK_DD4_MAX = 0.008   # si DD >= 4%: max 0.8%
RISK_DD6_MAX = 0.005   # si DD >= 6%: max 0.5%

# ── Supertrend H4 ─────────────────────────────────────────────────────────────
ST_PERIOD = 10
ST_MULT   = 3.0
# dir=+1 (GREEN) -> solo LONGS permitidos
# dir=-1 (RED)   -> solo SHORTS permitidos

# ── Choppiness Index H4 ───────────────────────────────────────────────────────
CHOP_PERIOD     = 14
CHOP_TREND_MAX  = 48   # por debajo: mercado en tendencia (riesgo alto)
CHOP_CHOPPY_MIN = 57   # por encima: mercado choppy/lateral (riesgo bajo)

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
ADX_MIN        = 22            # fuerza de tendencia minima
ADX_CHOPPY_MIN = 28            # en regimen choppy, exigir ADX mas alto

RSI_LONG_MIN   = 35
RSI_LONG_MAX   = 75
RSI_SHORT_MIN  = 25
RSI_SHORT_MAX  = 65

# ── Filtros de sentimiento externo ────────────────────────────────────────────
# Bybit Funding Rate (cada 8h) — sesgo del mercado de futuros
FUND_LONG_MIN   = -0.0003     # no entrar long si funding muy negativo (squeeze)
FUND_SHORT_MAX  =  0.00005    # solo short cuando funding <= 0 (mercado bearish)
FUND_SHORT_MIN  = -0.0004     # no short si funding muy negativo

# Fear & Greed Index (diario) — sentimiento macro
FG_LONG_MIN    = 35            # no long si miedo extremo
FG_SHORT_MIN   = 10            # no short en capitulacion pura
FG_SHORT_MAX   = 70            # no short si euforia extrema

# ── Opening Range Breakout (ORB) ──────────────────────────────────────────────
ORB_HOUR_START    = 0          # inicio del rango UTC
ORB_HOUR_END      = 4          # fin del rango / inicio del trading
ORB_HOUR_CLOSE    = 20         # cierre forzado EOD (no overnight)
ORB_MIN_RANGE_PCT = 0.003      # rango minimo 0.3% del precio

# ── Gestion de posicion ───────────────────────────────────────────────────────
ATR_SL_MULT    = 1.2           # Stop loss = 1.2x ATR
ATR_TRAIL_MULT = 1.0           # Trailing stop = EMA20 +/- 1x ATR
TP_RR          = 2.2           # Take Profit = 2.2x SL (R:R 1:2.2)
ATR_VOL_MULT   = 1.8           # Skip si ATR > 1.8x ATR_avg20 (volatilidad extrema)
MAX_POSITIONS  = 1

# ── Crypto Fund Trader rules ──────────────────────────────────────────────────
CFT_TARGET_PCT   = 0.08        # +8% objetivo fase 1
CFT_PHASE2_PCT   = 0.05        # +5% objetivo fase 2
CFT_MAX_DD_PCT   = 0.10        # -10% drawdown maximo sobre peak equity
CFT_DAILY_DD_PCT = 0.05        # -5% perdida diaria maxima

# ── Archivos de estado para el dashboard ─────────────────────────────────────
DATA_DIR    = "data"
STATE_FILE  = "data/state.json"
TRADES_FILE = "data/trades.json"
EQUITY_FILE = "data/equity.json"

# ── Datos de sentimiento (actualizados cada 8h por scheduler) ─────────────────
FUNDING_CSV = "btcusdt_funding_rate.csv"
FG_CSV      = "fear_greed_index.csv"
