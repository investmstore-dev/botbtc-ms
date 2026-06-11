# BOT BTC — Mining Store
**Estrategia:** ORB + MACD/RSI + Supertrend H4 + Choppiness Index  
**Par:** BTCUSD H1 | **Prop Firm:** Crypto Fund Trader (CFT) $10k Challenge

---

## Resultados Backtest (Jul 2024 – Jun 2026)

| Métrica | Resultado |
|---|---|
| Retorno 2 años | +36.6% |
| Max Drawdown | -7.8% |
| Profit Factor | 1.59 |
| Win Rate | 44.3% |
| Short PF | 1.87 |
| Challenges CFT pasados | 3 (en ~35-40 días cada uno en mercado tendencial) |

---

## Cómo funciona

El bot detecta automáticamente el régimen de mercado y ajusta el riesgo:

| Régimen (Choppiness H4) | CHOP | Riesgo |
|---|---|---|
| Tendencia fuerte | < 48 | 1.8% |
| Neutro | 48–57 | 1.0% |
| Lateral / Choppy | > 57 | 0.5% |

**Filtros en cascada:**
1. **Supertrend H4** — define la dirección: GREEN = solo longs, RED = solo shorts
2. **Choppiness Index H4** — define el riesgo (auto-reducción en mercados laterales)
3. **ORB** — entry por breakout del rango 00:00–04:00 UTC
4. **MACD + ADX + EMA** — confirmación de momentum H1
5. **Funding Rate (Bybit)** — sesgo del mercado de futuros
6. **Fear & Greed Index** — sentimiento macro diario

---

## Requisitos

```
Python 3.12+
MetaTrader 5 (para bridge con Bybit via EA)
```

```bash
pip install -r requirements.txt
```

**`requirements.txt`:**
```
pandas
numpy
requests
MetaTrader5
```

---

## Configuración inicial

### 1. Credenciales CFT en `config.py`

```python
MT5_LOGIN    = 123456          # Tu login CFT
MT5_PASSWORD = "tu_password"   # Tu password CFT
MT5_SERVER   = "CryptoFundTrader-Live"
```

### 2. Descargar datos de sentimiento

El bot necesita el Funding Rate de Bybit y el Fear & Greed Index actualizados.

```bash
python download_sentiment.py
```

Esto genera:
- `btcusdt_funding_rate.csv` — funding rate cada 8h
- `fear_greed_index.csv` — índice diario

**Programar actualización automática cada 8 horas** (Windows Task Scheduler):

```
Programa: python
Argumentos: C:\ruta\botbtc-ms\download_sentiment.py
Disparador: Cada 8 horas
```

### 3. Instalar el EA Bridge en MetaTrader 5

Abrir MetaTrader 5 → `File > Open Data Folder > MQL5 > Experts`  
Copiar `BotBTC_Bridge.mq5` ahí y compilar desde el Editor MQL5.  
Arrastrar el EA al gráfico BTCUSD H1 y activar "Allow Algo Trading".

### 4. Iniciar el bot

```bash
python bot.py
```

El bot genera logs en `botbtc.log` y actualiza archivos JSON en `data/` para el dashboard.

---

## Estructura del proyecto

```
botbtc-ms/
├── config.py              # Todos los parámetros (editar aquí)
├── strategy.py            # Lógica: Supertrend, Choppiness, señales, sizing
├── bot.py                 # Loop principal, trailing stop, EOD close, guardas CFT
├── mt5_connector.py       # Bridge Python ↔ MetaTrader 5
├── state_manager.py       # Estado JSON para el dashboard
├── BotBTC_Bridge.mq5      # EA MetaTrader 5 (bridge HTTP)
├── download_sentiment.py  # Descarga Bybit funding + Fear & Greed (correr cada 8h)
├── download_bybit.py      # Descarga histórico H1 BTCUSDT para backtests
├── backtest_cft_v5b.py    # Backtest de referencia (versión final)
├── challenge_tracker.py   # Analiza cuántos días tomó cada challenge
└── data/                  # Estado en tiempo real (generado por el bot)
    ├── state.json
    ├── trades.json
    └── equity.json
```

---

## Parámetros clave (`config.py`)

```python
# Riesgo por régimen de mercado
RISK_TREND   = 0.018   # Choppiness H4 < 48 → 1.8%
RISK_NEUTRAL = 0.010   # Choppiness H4 48-57 → 1.0%
RISK_CHOPPY  = 0.005   # Choppiness H4 > 57 → 0.5%

# Supertrend H4
ST_PERIOD = 10
ST_MULT   = 3.0

# Choppiness Index H4
CHOP_PERIOD     = 14
CHOP_TREND_MAX  = 48
CHOP_CHOPPY_MIN = 57

# ORB
ORB_HOUR_START = 0    # UTC inicio rango
ORB_HOUR_END   = 4    # UTC fin rango / inicio trading
ORB_HOUR_CLOSE = 20   # UTC cierre forzado EOD

# SL / TP
ATR_SL_MULT = 1.2     # SL = 1.2x ATR
TP_RR       = 2.2     # TP = 2.2x SL  →  R:R 1:2.2

# CFT
CFT_MAX_DD_PCT   = 0.10   # -10% drawdown máximo
CFT_DAILY_DD_PCT = 0.05   # -5% pérdida diaria máxima
CFT_TARGET_PCT   = 0.08   # +8% objetivo Phase 1
```

---

## Reglas CFT integradas

El bot controla automáticamente:
- **Max DD -10%**: calcula sobre el peak de equity, cierra posiciones y se detiene si se viola
- **Daily DD -5%**: pausa el trading el resto del día si se alcanza
- **Objetivo +8%**: alerta cuando se alcanza el target de Phase 1
- **EOD close**: cierra posiciones abiertas cada día a las 20:00 UTC (no overnight)

---

## Dashboard

El dashboard en tiempo real está en el repositorio separado:  
[botbtc-dashboard-ms](https://github.com/investmstore-dev/botbtc-dashboard-ms)

Lee los archivos `data/state.json`, `data/trades.json` y `data/equity.json` generados por el bot.

---

## Backtest

```bash
# Descargar datos históricos H1
python download_bybit.py

# Descargar sentimiento
python download_sentiment.py

# Correr backtest final (v5b)
python backtest_cft_v5b.py

# Ver días por challenge
python challenge_tracker.py
```
