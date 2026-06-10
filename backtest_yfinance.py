"""
Backtest Ene 2026 - Jun 2026 -- datos reales yfinance (BTC-USD)
Estrategia: ORB + MACD/RSI | BTCUSD H1
Cuenta objetivo: Crypto Fund Trader $10k

Ejecutar: python backtest_yfinance.py
No requiere MT5 ni CSV — descarga datos directamente de Yahoo Finance.
"""
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    print("Instala yfinance: pip install yfinance")
    exit(1)

# ── Parametros ─────────────────────────────────────────────────────────────
INITIAL_CAPITAL  = 10_000
RISK_PCT         = 0.015       # v6: 1.5% — BTC bear 2026 necesita mas amplitud

EMA_FAST         = 20
EMA_SLOW         = 50
EMA_TREND        = 200
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
RSI_PERIOD       = 14
ATR_PERIOD       = 14
ADX_PERIOD       = 14

ADX_MIN          = 25           # v3: tendencias mas fuertes
RSI_LONG_MIN     = 38
RSI_LONG_MAX     = 72
RSI_SHORT_MIN    = 28
RSI_SHORT_MAX    = 62

ORB_MIN_RANGE_PCT = 0.003       # v3: ORB debe ser al menos 0.3% del precio
ATR_SL_MULT      = 1.5
TP_RR            = 2.0          # v3: balance entre v1 y v2
ATR_TRAIL_MULT   = 1.0

ORB_HOUR_START   = 0
ORB_HOUR_END     = 4
ORB_HOUR_CLOSE   = 20

CFT_MAX_DD       = 0.10
CFT_DAILY_DD     = 0.05
CFT_TARGET       = 0.08

# ── Descarga de datos ───────────────────────────────────────────────────────
print("Descargando datos BTC-USD H1 desde Yahoo Finance...")
print("(Warmup Jun 2025 + test Ene-Jun 2026)")

# yfinance limita 730 dias en intervalo 1h — descargamos en dos tramos
ticker = yf.Ticker("BTC-USD")

df_warm = ticker.history(start="2025-06-01", end="2025-12-31", interval="1h")
df_test = ticker.history(start="2026-01-01", end="2026-06-11", interval="1h")

if df_warm.empty or df_test.empty:
    print()
    print("Yahoo Finance no tiene datos H1 para 2026 aun (limite de 730 dias).")
    print("Opciones:")
    print("  1. Exportar CSV desde MT5 con ExportH1Data_BTC.mq5 y usar backtest_2026.py")
    print("  2. Correr el backtest con datos disponibles hasta la fecha limite")
    print()
    # Intentar con lo disponible
    df_test = ticker.history(period="730d", interval="1h")
    if df_test.empty:
        print("Sin datos disponibles. Verifica tu conexion a internet.")
        exit(1)
    df_warm = pd.DataFrame()
    print(f"Usando datos disponibles: {df_test.index[0].date()} - {df_test.index[-1].date()}")

df_all = pd.concat([df_warm, df_test]) if not df_warm.empty else df_test
df_all.columns = [c.lower() for c in df_all.columns]
df_all = df_all[["open", "high", "low", "close", "volume"]].copy()
if df_all.index.tz is not None:
    df_all.index = df_all.index.tz_localize(None)
df_all.sort_index(inplace=True)
df_all = df_all[~df_all.index.duplicated(keep="first")]

print(f"Datos cargados: {len(df_all)} velas H1")
print(f"Rango: {df_all.index[0].date()} - {df_all.index[-1].date()}")
print()

# ── Indicadores ─────────────────────────────────────────────────────────────
c, h, l = df_all["close"], df_all["high"], df_all["low"]

df_all["ema20"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
df_all["ema50"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
df_all["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()

tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
df_all["atr"] = tr.rolling(ATR_PERIOD).mean()

delta = c.diff()
gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
loss_  = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
df_all["rsi"] = 100 - (100 / (1 + gain / loss_.replace(0, np.nan)))

ema_f            = c.ewm(span=MACD_FAST,   adjust=False).mean()
ema_s            = c.ewm(span=MACD_SLOW,   adjust=False).mean()
df_all["macd"]   = ema_f - ema_s
df_all["macd_sig"]  = df_all["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
df_all["macd_hist"] = df_all["macd"] - df_all["macd_sig"]

up  = h.diff(); dn = -l.diff()
pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.0), index=df_all.index)
mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.0), index=df_all.index)
atr14 = tr.rolling(ADX_PERIOD).mean()
pdi   = 100 * pdm.rolling(ADX_PERIOD).mean() / atr14
mdi   = 100 * mdm.rolling(ADX_PERIOD).mean() / atr14
dx    = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
df_all["adx"] = dx.rolling(ADX_PERIOD).mean()

# ── ORB por dia ─────────────────────────────────────────────────────────────
df_all["_hour"] = df_all.index.hour
df_all["_date"] = df_all.index.date

orb_high_map = {}
orb_low_map  = {}

for date_val, group in df_all.groupby("_date"):
    rng = group[(group["_hour"] >= ORB_HOUR_START) & (group["_hour"] < ORB_HOUR_END)]
    if len(rng) >= 2:
        orb_high_map[date_val] = rng["high"].max()
        orb_low_map[date_val]  = rng["low"].min()

df_all["orb_high"] = df_all["_date"].map(orb_high_map)
df_all["orb_low"]  = df_all["_date"].map(orb_low_map)

# ── EMA500 — tendencia macro ~20 dias en H1 ──────────────────────────────────
# v5: filtro macro. Solo longs cuando precio > EMA500, solo shorts cuando < EMA500
df_all["ema500"] = df_all["close"].ewm(span=500, adjust=False).mean()

df_all = df_all.dropna(subset=["ema200", "adx", "orb_high", "ema500"])

# ── Periodo real de prueba ───────────────────────────────────────────────────
df = df_all[df_all.index >= "2026-01-01"].copy()

if df.empty:
    # Fallback: usar ultimos 6 meses disponibles como "periodo de prueba"
    cutoff = df_all.index[int(len(df_all) * 0.5)]
    df = df_all[df_all.index >= cutoff].copy()
    print(f"[Fallback] Usando periodo: {df.index[0].date()} → {df.index[-1].date()}")
else:
    print(f"Velas H1 para backtest: {len(df)}")
    print(f"Inicio : {df.index[0].date()} | BTC: ${df['close'].iloc[0]:,.0f}")
    print(f"Fin    : {df.index[-1].date()} | BTC: ${df['close'].iloc[-1]:,.0f}")

print()

# ── Simulacion ───────────────────────────────────────────────────────────────
capital     = INITIAL_CAPITAL
peak        = capital
trades      = []
pos         = None
daily_start = {}

for i in range(1, len(df)):
    row  = df.iloc[i]
    prev = df.iloc[i-1]
    dt   = df.index[i].date()
    hour = df.index[i].hour

    if dt not in daily_start:
        daily_start[dt] = capital

    if pos:
        if hour >= ORB_HOUR_CLOSE:
            mult = 1 if pos["type"] == "long" else -1
            pnl  = (row["close"] - pos["entry"]) * mult * pos["lot"]
            capital += pnl
            peak = max(peak, capital)
            trades.append({
                "entry_date": pos["entry_date"], "exit_date": df.index[i],
                "type": pos["type"], "entry": pos["entry"],
                "exit": row["close"], "lot": pos["lot"],
                "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                "exit_reason": "EOD"
            })
            pos = None
            continue

        trail = (row["ema20"] - ATR_TRAIL_MULT * row["atr"]
                 if pos["type"] == "long"
                 else row["ema20"] + ATR_TRAIL_MULT * row["atr"])
        if pos["type"] == "long"  and trail > pos["sl"]: pos["sl"] = trail
        if pos["type"] == "short" and trail < pos["sl"]: pos["sl"] = trail

        sl_hit = ((pos["type"] == "long"  and row["low"]  <= pos["sl"]) or
                  (pos["type"] == "short" and row["high"] >= pos["sl"]))
        tp_hit = ((pos["type"] == "long"  and row["high"] >= pos["tp"]) or
                  (pos["type"] == "short" and row["low"]  <= pos["tp"]))

        if sl_hit or tp_hit:
            exit_price = pos["tp"] if tp_hit else pos["sl"]
            mult = 1 if pos["type"] == "long" else -1
            pnl  = (exit_price - pos["entry"]) * mult * pos["lot"]
            capital += pnl
            peak = max(peak, capital)
            trades.append({
                "entry_date": pos["entry_date"], "exit_date": df.index[i],
                "type": pos["type"], "entry": pos["entry"],
                "exit": exit_price, "lot": pos["lot"],
                "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                "exit_reason": "TP" if tp_hit else "SL"
            })
            pos = None
        continue

    if (capital - peak) / INITIAL_CAPITAL <= -CFT_MAX_DD: continue
    if (capital - daily_start[dt]) / INITIAL_CAPITAL <= -CFT_DAILY_DD: continue
    if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE): continue
    if pd.isna(row["orb_high"]) or pd.isna(row["orb_low"]): continue

    # v3: filtro de rango ORB minimo (evita dias sin direccion)
    orb_range = row["orb_high"] - row["orb_low"]
    if orb_range / row["close"] < ORB_MIN_RANGE_PCT: continue

    adx_ok      = row["adx"] >= ADX_MIN
    trend_up    = row["ema50"] > row["ema200"]
    trend_dn    = row["ema50"] < row["ema200"]
    mom_up      = row["ema20"] > row["ema50"]
    mom_dn      = row["ema20"] < row["ema50"]
    macro_up    = row["close"] > row["ema500"]   # v5: tendencia macro alcista
    macro_dn    = row["close"] < row["ema500"]   # v5: tendencia macro bajista
    macd_bull   = row["macd_hist"] > 0
    macd_bear   = row["macd_hist"] < 0
    orb_up      = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
    orb_dn      = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

    sl_dist = ATR_SL_MULT * row["atr"]
    tp_dist = sl_dist * TP_RR
    lot     = max(0.001, round((capital * RISK_PCT) / sl_dist, 4))

    # v5: filtro macro — no longs en bear macro, no shorts en bull macro
    if (orb_up and macro_up and trend_up and mom_up and macd_bull and adx_ok
            and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
        pos = {"type": "long",  "entry": row["close"],
               "sl": row["close"] - sl_dist, "tp": row["close"] + tp_dist,
               "lot": lot, "entry_date": df.index[i]}

    elif (orb_dn and macro_dn and trend_dn and mom_dn and macd_bear and adx_ok
            and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
        pos = {"type": "short", "entry": row["close"],
               "sl": row["close"] + sl_dist, "tp": row["close"] - tp_dist,
               "lot": lot, "entry_date": df.index[i]}

# ── Metricas ─────────────────────────────────────────────────────────────────
df_t = pd.DataFrame(trades)
if df_t.empty:
    print("Sin trades generados.")
    print("Posibles causas: pocos datos, filtros muy estrictos, o mercado lateral.")
    exit()

wins = df_t[df_t["pnl_usd"] > 0]
loss = df_t[df_t["pnl_usd"] <= 0]
tps  = df_t[df_t.get("exit_reason", "") == "TP"] if "exit_reason" in df_t.columns else pd.DataFrame()
sls  = df_t[df_t.get("exit_reason", "") == "SL"] if "exit_reason" in df_t.columns else pd.DataFrame()
eods = df_t[df_t.get("exit_reason", "") == "EOD"] if "exit_reason" in df_t.columns else pd.DataFrame()

n    = len(df_t)
wr   = len(wins) / n * 100
aw   = wins["pnl_usd"].mean() if len(wins) else 0
al   = loss["pnl_usd"].mean() if len(loss) else 0
pf   = wins["pnl_usd"].sum() / abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum() != 0 else 999
fin  = df_t["capital"].iloc[-1]
ret  = (fin - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
gpr  = abs(aw / al) if al else 0

eq   = [INITIAL_CAPITAL] + df_t["capital"].tolist()
pk   = eq[0]; dd_max = 0.0
for v in eq:
    pk = max(pk, v)
    dd_max = min(dd_max, (v - pk) / pk * 100)

target = INITIAL_CAPITAL * (1 + CFT_TARGET)
d2t = None; dd_at_target = None
for t in df_t.itertuples():
    if t.capital >= target:
        d2t = (t.exit_date - df_t["entry_date"].iloc[0]).days
        sub = [INITIAL_CAPITAL] + df_t[df_t["exit_date"] <= t.exit_date]["capital"].tolist()
        pk2 = sub[0]; dd2 = 0.0
        for v in sub:
            pk2 = max(pk2, v)
            dd2 = min(dd2, (v - pk2) / pk2 * 100)
        dd_at_target = dd2
        break

streak = ms = 0
for p in df_t["pnl_usd"]:
    if p <= 0: streak += 1; ms = max(ms, streak)
    else: streak = 0

months = max(1, (df_t["exit_date"].iloc[-1] - df_t["entry_date"].iloc[0]).days / 30)
cft_ok = d2t is not None and abs(dd_max) < 10

# ── Reporte ──────────────────────────────────────────────────────────────────
W = 65; SEP = "=" * W; S2 = "-" * W
print(); print(SEP)
print(f"  BACKTEST {df.index[0].date()} - {df.index[-1].date()}")
print("  Estrategia: ORB + MACD/RSI | BTCUSD H1 | Risk 1%")
print("  Cuenta objetivo: Crypto Fund Trader $10,000")
print("  Fuente: Yahoo Finance (datos reales)")
print(SEP)
print("  {:<32} {:>14}   {:>10}".format("METRICA", "RESULTADO", "CFT REF"))
print(S2)
print("  {:<32} {:>14}   {:>10}".format("Trades totales", n, "—"))
print("  {:<32} {:>14}   {:>10}".format("Ganadores", f"{len(wins)} ({wr:.1f}%)", ">50%"))
print("  {:<32} {:>14}   {:>10}".format("Perdedores", f"{len(loss)} ({100-wr:.1f}%)", "—"))
print("  {:<32} {:>14}   {:>10}".format("  -> Por TP", len(tps), "—"))
print("  {:<32} {:>14}   {:>10}".format("  -> Por SL", len(sls), "—"))
print("  {:<32} {:>14}   {:>10}".format("  -> Cierre EOD", len(eods), "—"))
print("  {:<32} {:>14}   {:>10}".format("Promedio ganancia", f"${aw:,.0f}", "—"))
print("  {:<32} {:>14}   {:>10}".format("Promedio perdida", f"${al:,.0f}", "—"))
print("  {:<32} {:>14}   {:>10}".format("Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
print("  {:<32} {:>14}   {:>10}".format("Profit Factor", f"{pf:.2f}", ">1.5"))
print("  {:<32} {:>14}   {:>10}".format("Trades / mes", f"{n/months:.1f}", "—"))
print("  {:<32} {:>14}   {:>10}".format("Retorno total", f"{ret:+.1f}%", "+8% obj"))
print("  {:<32} {:>14}   {:>10}".format("Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
print("  {:<32} {:>14}   {:>10}".format("Racha max perdidas", f"{ms} trades", "<6"))
print("  {:<32} {:>14}   {:>10}".format("Capital final", f"${fin:,.0f}", f">${INITIAL_CAPITAL*1.08:,.0f}"))
print(S2)
d2t_s  = f"{d2t} dias" if d2t else "NO ALCANZADO"
dd_t_s = f"{dd_at_target:+.1f}%" if dd_at_target else "N/A"
print("  {:<32} {:>14}   {:>10}".format("Dias para CFT +8%", d2t_s, "—"))
print("  {:<32} {:>14}   {:>10}".format("DD al alcanzar +8%", dd_t_s, ">-10%"))
print("  {:<32} {:>14}   {:>10}".format("Cumple CFT Challenge",
      "[SI]" if cft_ok else "[NO]", "[SI]" if cft_ok else "[NO]"))
print(SEP)

print()
print("  HISTORIAL DE TRADES")
print(S2)
print("  {:<16} {:<16} {:5} {:>10} {:>10} {:>7} {:>4} {:>9} {:>10}".format(
    "Entrada", "Salida", "Tipo", "Entry BTC", "Exit BTC", "Lot", "Sal", "P&L USD", "Capital"))
print("  " + "-" * 99)
for _, t in df_t.iterrows():
    flag   = " WIN" if t["pnl_usd"] > 0 else "    "
    reason = t.get("exit_reason", "?")
    print("  {:<16} {:<16} {:5} {:>10,.0f} {:>10,.0f} {:>7.4f} {:>4} ${:>+8,.0f} ${:>9,.0f}{}".format(
        str(t["entry_date"])[:16], str(t["exit_date"])[:16],
        t["type"][0].upper(), t["entry"], t["exit"],
        t["lot"], reason, t["pnl_usd"], t["capital"], flag))
print(); print(SEP)

print()
print("  EVALUACION CRYPTO FUND TRADER")
print(S2)
checks = [
    ("Profit target +8%",    ret >= CFT_TARGET * 100,   f"{ret:+.1f}%"),
    ("Max Drawdown < 10%",   abs(dd_max) < 10,           f"{dd_max:+.1f}%"),
    ("Profit Factor > 1.5",  pf > 1.5,                   f"{pf:.2f}"),
    ("Winrate > 50%",        wr > 50,                    f"{wr:.1f}%"),
    ("Ratio G/P > 1.5x",    gpr > 1.5,                  f"{gpr:.2f}x"),
    ("Racha perdidas < 6",   ms < 6,                     f"{ms} trades"),
]
for label, ok, val in checks:
    status = "[OK]" if ok else "[XX]"
    print(f"  {status}  {label:<30} {val:>10}")
print(SEP)
