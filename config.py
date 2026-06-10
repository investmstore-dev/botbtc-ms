# BOT Mining Store BTC -- Configuracion
# Estrategia: ORB + MACD/RSI | BTCUSD H1
# Cuenta: Crypto Fund Trader Challenge $10k

MT5_LOGIN    = 0              # Reemplazar con login real CFT
MT5_PASSWORD = ""             # Reemplazar con password real CFT
MT5_SERVER   = "CryptoFundTrader-Live"

SYMBOL     = "BTCUSD"
TIMEFRAME  = "H1"
RISK_PCT   = 0.015            # 1.5% del capital por operacion (optimizado v6)

# Indicadores
EMA_FAST   = 20
EMA_SLOW   = 50
EMA_TREND  = 200
MACD_FAST  = 12
MACD_SLOW  = 26
MACD_SIGNAL= 9
RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14

# Filtros de entrada
ADX_MIN        = 25            # v6: solo tendencias fuertes
RSI_LONG_MIN   = 38
RSI_LONG_MAX   = 72
RSI_SHORT_MIN  = 28
RSI_SHORT_MAX  = 62

# Opening Range Breakout (ORB)
# Rango definido por las primeras 4 velas H1 del dia UTC (00:00 - 04:00)
# Breakout operado desde la vela 04:00 UTC en adelante
ORB_CANDLES    = 4            # velas H1 para definir el rango
ORB_HOUR_START = 0            # hora UTC inicio del rango
ORB_HOUR_END   = 4            # hora UTC fin del rango (breakout a partir de aqui)
ORB_HOUR_CLOSE = 20           # hora UTC cierre forzado de posiciones (no overnight)

# Gestion de posicion
ATR_SL_MULT    = 1.5          # Stop loss = 1.5x ATR
ATR_TRAIL_MULT = 1.0          # Trailing stop = 1x ATR desde EMA20
TP_RR          = 2.0          # Take Profit = 2x el SL (R:R 1:2) — optimizado v6
ORB_MIN_RANGE_PCT = 0.003     # Rango ORB minimo 0.3% del precio para evitar dias choppy
EMA_MACRO      = 500          # EMA500 = ~20 dias en H1 (filtro de tendencia macro)
MAX_POSITIONS  = 1

# Crypto Fund Trader rules
CFT_TARGET_PCT   = 0.08       # +8% objetivo fase 1
CFT_PHASE2_PCT   = 0.05       # +5% objetivo fase 2
CFT_MAX_DD_PCT   = 0.10       # -10% drawdown maximo (equity)
CFT_DAILY_DD_PCT = 0.05       # -5% perdida diaria maxima

# Archivos de estado para el dashboard
DATA_DIR       = "data"
STATE_FILE     = "data/state.json"
TRADES_FILE    = "data/trades.json"
EQUITY_FILE    = "data/equity.json"
