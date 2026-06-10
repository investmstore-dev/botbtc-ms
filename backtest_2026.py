"""
Backtest Ene 2026 - Jun 2026 -- datos reales MT5
Estrategia: ORB + MACD/RSI | BTCUSD H1
Cuenta objetivo: Crypto Fund Trader $10k
"""
import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ── Parametros ─────────────────────────────────────────────────────────────
INITIAL_CAPITAL  = 10_000
RISK_PCT         = 0.01       # 1% por operacion

EMA_FAST         = 20
EMA_SLOW         = 50
EMA_TREND        = 200
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
RSI_PERIOD       = 14
ATR_PERIOD       = 14
ADX_PERIOD       = 14

ADX_MIN          = 20
RSI_LONG_MIN     = 40
RSI_LONG_MAX     = 70
RSI_SHORT_MIN    = 30
RSI_SHORT_MAX    = 60

ATR_SL_MULT      = 1.5
TP_RR            = 2.5
ATR_TRAIL_MULT   = 1.0

ORB_HOUR_START   = 0
ORB_HOUR_END     = 4
ORB_HOUR_CLOSE   = 20

CFT_MAX_DD       = 0.10
CFT_DAILY_DD     = 0.05
CFT_TARGET       = 0.08

# ── Carga de datos ──────────────────────────────────────────────────────────
MT5_CSV = os.path.join(os.environ["APPDATA"],
          "MetaQuotes", "Terminal", "Common", "Files", "btcusd_h1_data.csv")

print(f"Cargando datos desde: {MT5_CSV}")
df_raw = pd.read_csv(MT5_CSV, parse_dates=["datetime"], encoding="utf-16")
df_raw.columns = [c.lower().strip() for c in df_raw.columns]
df_raw.set_index("datetime", inplace=True)
df_raw.sort_index(inplace=True)
if df_raw.index.tz is not None:
    df_raw.index = df_raw.index.tz_localize(None)
df_raw = df_raw[["open", "high", "low", "close", "volume"]].dropna()

# Warmup desde Jun 2025 para calentar EMA200
df_raw = df_raw[df_raw.index >= "2025-06-01"]

# ── Indicadores ─────────────────────────────────────────────────────────────
c, h, l = df_raw["close"], df_raw["high"], df_raw["low"]

df_raw["ema20"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
df_raw["ema50"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
df_raw["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()

tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
df_raw["atr"] = tr.rolling(ATR_PERIOD).mean()

delta = c.diff()
gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
loss  = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
df_raw["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

ema_f          = c.ewm(span=MACD_FAST,   adjust=False).mean()
ema_s          = c.ewm(span=MACD_SLOW,   adjust=False).mean()
df_raw["macd"] = ema_f - ema_s
df_raw["macd_sig"]  = df_raw["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
df_raw["macd_hist"] = df_raw["macd"] - df_raw["macd_sig"]

up  = h.diff(); dn = -l.diff()
pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.0), index=df_raw.index)
mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.0), index=df_raw.index)
atr14 = tr.rolling(ADX_PERIOD).mean()
pdi   = 100 * pdm.rolling(ADX_PERIOD).mean() / atr14
mdi   = 100 * mdm.rolling(ADX_PERIOD).mean() / atr14
dx    = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
df_raw["adx"] = dx.rolling(ADX_PERIOD).mean()

# ── ORB por dia ─────────────────────────────────────────────────────────────
df_raw["_hour"] = df_raw.index.hour
df_raw["_date"] = df_raw.index.date

orb_high_map = {}
orb_low_map  = {}

for date, group in df_raw.groupby("_date"):
    rng = group[(group["_hour"] >= ORB_HOUR_START) & (group["_hour"] < ORB_HOUR_END)]
    if len(rng) >= 2:
        orb_high_map[date] = rng["high"].max()
        orb_low_map[date]  = rng["low"].min()

df_raw["orb_high"] = df_raw["_date"].map(orb_high_map)
df_raw["orb_low"]  = df_raw["_date"].map(orb_low_map)

df_all = df_raw.dropna(subset=["ema200", "adx", "orb_high"])

# ── Periodo real de prueba ───────────────────────────────────────────────────
df = df_all[df_all.index >= "2026-01-01"].copy()
print(f"Velas H1 reales (Ene-Jun 2026): {len(df)}")
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

    # ── Gestion de posicion abierta ─────────────────────────────────────────
    if pos:
        # Cierre forzado al fin de ventana
        if hour >= ORB_HOUR_CLOSE:
            mult = 1 if pos["type"] == "long" else -1
            pnl  = (row["close"] - pos["entry"]) * mult * pos["lot"]
            capital += pnl
            peak = max(peak, capital)
            trades.append({
                "entry_date": pos["entry_date"], "exit_date": df.index[i],
                "type": pos["type"], "entry": round(pos["entry"], 2),
                "exit": round(row["close"], 2), "lot": pos["lot"],
                "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                "exit_reason": "EOD"
            })
            pos = None
            continue

        # Trailing stop
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
                "type": pos["type"], "entry": round(pos["entry"], 2),
                "exit": round(exit_price, 2), "lot": pos["lot"],
                "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                "exit_reason": "TP" if tp_hit else "SL"
            })
            pos = None
        continue

    # ── Guardas de riesgo CFT ────────────────────────────────────────────────
    if (capital - peak) / INITIAL_CAPITAL <= -CFT_MAX_DD:
        continue
    if (capital - daily_start[dt]) / INITIAL_CAPITAL <= -CFT_DAILY_DD:
        continue

    # Solo en ventana activa (no en rango ORB, no overnight)
    if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE):
        continue

    if pd.isna(row["orb_high"]) or pd.isna(row["orb_low"]):
        continue

    adx_ok      = row["adx"] >= ADX_MIN
    trend_up    = row["ema50"] > row["ema200"]
    trend_dn    = row["ema50"] < row["ema200"]
    mom_up      = row["ema20"] > row["ema50"]
    mom_dn      = row["ema20"] < row["ema50"]
    macd_bull   = row["macd_hist"] > 0
    macd_bear   = row["macd_hist"] < 0
    orb_up      = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
    orb_dn      = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

    sl_dist = ATR_SL_MULT * row["atr"]
    tp_dist = sl_dist * TP_RR
    lot     = max(0.001, round((capital * RISK_PCT) / sl_dist, 3))

    if (orb_up and (trend_up or mom_up) and macd_bull and adx_ok
            and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
        pos = {
            "type": "long", "entry": row["close"],
            "sl": row["close"] - sl_dist, "tp": row["close"] + tp_dist,
            "lot": lot, "entry_date": df.index[i]
        }

    elif (orb_dn and (trend_dn or mom_dn) and macd_bear and adx_ok
            and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
        pos = {
            "type": "short", "entry": row["close"],
            "sl": row["close"] + sl_dist, "tp": row["close"] - tp_dist,
            "lot": lot, "entry_date": df.index[i]
        }

# ── Metricas ─────────────────────────────────────────────────────────────────
df_t = pd.DataFrame(trades)
if df_t.empty:
    print("Sin trades en Ene-Jun 2026.")
    print("Verifica que el CSV tiene datos de BTCUSD H1 para 2026.")
    exit()

wins = df_t[df_t["pnl_usd"] > 0]
loss = df_t[df_t["pnl_usd"] <= 0]
tps  = df_t[df_t["exit_reason"] == "TP"] if "exit_reason" in df_t.columns else pd.DataFrame()
sls  = df_t[df_t["exit_reason"] == "SL"] if "exit_reason" in df_t.columns else pd.DataFrame()
eods = df_t[df_t["exit_reason"] == "EOD"] if "exit_reason" in df_t.columns else pd.DataFrame()

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
d2t    = None; dd_at_target = None
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
trades_month = n / months

cft_ok = d2t is not None and abs(dd_max) < 10

# ── Reporte ──────────────────────────────────────────────────────────────────
W = 65; SEP = "=" * W; S2 = "-" * W
print(); print(SEP)
print("  BACKTEST Ene 2026 - Jun 2026  |  Datos reales MT5")
print("  Estrategia: ORB + MACD/RSI | BTCUSD H1 | Risk 1%")
print("  Cuenta objetivo: Crypto Fund Trader $10,000")
print(SEP)
print("  {:<32} {:>14}   {:>10}".format("METRICA", "RESULTADO", "CFT REF"))
print(S2)
print("  {:<32} {:>14}   {:>10}".format("Trades totales", n, "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "Ganadores", f"{len(wins)} ({wr:.1f}%)", ">50%"))
print("  {:<32} {:>14}   {:>10}".format(
    "Perdedores", f"{len(loss)} ({100-wr:.1f}%)", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "  -> Por TP", f"{len(tps)}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "  -> Por SL", f"{len(sls)}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "  -> Cierre EOD", f"{len(eods)}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "Promedio ganancia", f"${aw:,.0f}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "Promedio perdida", f"${al:,.0f}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
print("  {:<32} {:>14}   {:>10}".format(
    "Profit Factor", f"{pf:.2f}", ">1.5"))
print("  {:<32} {:>14}   {:>10}".format(
    "Trades / mes", f"{trades_month:.1f}", "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "Retorno total", f"{ret:+.1f}%", "+8% obj"))
print("  {:<32} {:>14}   {:>10}".format(
    "Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
print("  {:<32} {:>14}   {:>10}".format(
    "Racha max perdidas", f"{ms} trades", "<6"))
print("  {:<32} {:>14}   {:>10}".format(
    "Capital final", f"${fin:,.0f}", f">${INITIAL_CAPITAL*1.08:,.0f}"))
print(S2)
d2t_s  = f"{d2t} dias" if d2t else "NO ALCANZADO"
dd_t_s = f"{dd_at_target:+.1f}%" if dd_at_target else "N/A"
print("  {:<32} {:>14}   {:>10}".format(
    "Dias para CFT +8%", d2t_s, "—"))
print("  {:<32} {:>14}   {:>10}".format(
    "DD al alcanzar +8%", dd_t_s, ">-10%"))
print("  {:<32} {:>14}   {:>10}".format(
    "Cumple CFT Challenge", "[SI]" if cft_ok else "[NO]",
    "[SI]" if cft_ok else "[NO]"))
print(SEP)

# ── Historial de trades ───────────────────────────────────────────────────────
print()
print("  HISTORIAL DE TRADES")
print(S2)
print("  {:<14} {:<14} {:5} {:>10} {:>10} {:>6} {:>5} {:>10} {:>10}".format(
    "Entrada", "Salida", "Tipo", "Entry", "Exit", "Lot", "Salida", "P&L USD", "Capital"))
print("  " + "-" * 95)
for _, t in df_t.iterrows():
    flag = " WIN" if t["pnl_usd"] > 0 else "    "
    reason = t.get("exit_reason", "?")
    print("  {:<14} {:<14} {:5} {:>10,.0f} {:>10,.0f} {:>6.3f} {:>5} ${:>+9,.0f} ${:>9,.0f}{}".format(
        str(t["entry_date"])[:14], str(t["exit_date"])[:14],
        t["type"][0].upper(), t["entry"], t["exit"],
        t["lot"], reason, t["pnl_usd"], t["capital"], flag))
print(); print(SEP)

# ── Resumen rapido de evaluacion ─────────────────────────────────────────────
print()
print("  EVALUACION CRYPTO FUND TRADER")
print(S2)
checks = [
    ("Profit target +8%",          ret >= CFT_TARGET * 100,    f"{ret:+.1f}%"),
    ("Max Drawdown < 10%",         abs(dd_max) < 10,           f"{dd_max:+.1f}%"),
    ("Profit Factor > 1.5",        pf > 1.5,                   f"{pf:.2f}"),
    ("Winrate > 50%",              wr > 50,                    f"{wr:.1f}%"),
    ("Ratio G/P > 1.5x",          gpr > 1.5,                  f"{gpr:.2f}x"),
    ("Racha perdidas < 6",         ms < 6,                     f"{ms} trades"),
]
for label, ok, val in checks:
    status = "[OK]" if ok else "[XX]"
    print(f"  {status}  {label:<30} {val:>10}")
print(SEP)
