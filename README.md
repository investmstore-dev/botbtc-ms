# BOT Mining Store — Multi-par
**Estrategia:** ORB + MACD/RSI + Supertrend H4 + Choppiness Index  
**Pares:** BTCUSDT + DOGEUSDT H1 (modo SINGLE) | **Prop Firm:** Crypto Fund Trader (CFT) $10k

---

## Resultados Backtest portafolio (Jul 2024 – Jun 2026)

Estrategia operando **BTC + DOGE sobre una cuenta compartida**, máximo 1 posición
a la vez (modo SINGLE), reglas de CFT aplicadas al equity combinado:

| Métrica | BTC solo | **BTC + DOGE (SINGLE)** |
|---|---|---|
| Retorno 2 años | +36.6% | **+78.5%** |
| Max Drawdown | -7.8% | **-8.0%** |
| Profit Factor | 1.59 | **1.76** |
| Challenges CFT pasados | 3 | **6** |

DOGE usa la config-D optimizada (DD-guard agresivo) para no violar el -10% de CFT.
Ver `model/backtest_portfolio.py` y `model/optimize_doge.py`.

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
Cuenta Bybit (Demo Trading o Live) conectada a CFT
```

```bash
pip install -r requirements.txt
```

---

## Configuración inicial

### 1. Credenciales en `.env` (raíz del proyecto, NO se sube a git)

```
BYBIT_API_KEY=tu_api_key
BYBIT_API_SECRET=tu_api_secret
BYBIT_DEMO=true                  # false para cuenta live

# Notificaciones Telegram (opcional)
TELEGRAM_BOT_TOKEN=token_de_botfather
TELEGRAM_CHAT_ID=id_del_grupo
```

Para obtener el chat_id de Telegram: envía un mensaje al grupo con el bot y corre
`python -m utils.notifier --get-chat-id`. Prueba con `python -m utils.notifier --test`.

### 2. Iniciar todo (bot + dashboard)

```bash
start_bot.bat     # bot + data server + dashboard, abre el navegador
stop_bot.bat      # detiene todo
tail_log.bat      # ver el log en vivo
```

O manualmente desde la raíz del proyecto:

```bash
python -m logic.bot           # solo el bot
python -m utils.data_server   # servidor de datos del dashboard (puerto 8091)
```

El bot genera logs en `botbtc.log`, actualiza `data/` para el dashboard y
refresca el sentimiento (funding + Fear&Greed) automáticamente cada 8h.

---

## Estructura del proyecto

```
botbtc-ms/
├── config/
│   └── settings.py        # Todos los parámetros (editar aquí)
├── logic/
│   ├── bot.py             # Loop principal, trailing stop, EOD close, guardas CFT
│   └── strategy.py        # Supertrend, Choppiness, señales, sizing
├── utils/
│   ├── bybit_connector.py # API Bybit V5 (cuenta, velas, órdenes, SL/TP)
│   ├── state_manager.py   # Estado JSON para el dashboard (escritura atómica)
│   ├── notifier.py        # Notificaciones Telegram (trades + reporte diario)
│   └── data_server.py     # Servidor CORS puerto 8091 para el dashboard
├── model/
│   ├── backtest_cft_v5b.py  # Backtest de referencia (versión final)
│   ├── backtest_*.py        # Iteraciones históricas (v4, v5, v5c, 2026)
│   ├── challenge_tracker.py # Analiza cuántos días tomó cada challenge
│   ├── download_bybit.py    # Descarga histórico H1 BTCUSDT
│   ├── download_sentiment.py# Descarga funding + Fear&Greed manual
│   └── legacy_mt5/          # Arquitectura MT5 antigua (no se usa)
├── data/                  # Estado en tiempo real (generado por el bot)
├── start_bot.bat / stop_bot.bat / tail_log.bat
└── .env                   # Credenciales (no versionado)
```

---

## Parámetros clave (`config/settings.py`)

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
python model/download_bybit.py

# Descargar sentimiento
python model/download_sentiment.py

# Correr backtest final (v5b)
python model/backtest_cft_v5b.py

# Ver días por challenge
python model/challenge_tracker.py
```
