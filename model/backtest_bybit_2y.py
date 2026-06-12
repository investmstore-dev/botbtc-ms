"""
Backtest 2 ANOS -- datos reales Bybit API (BTCUSDT H1)
Estrategia: ORB + MACD/RSI con filtro macro EMA500
Periodo: Ene 2024 - Jun 2026
Cuenta objetivo: Crypto Fund Trader $10k (reglas CFT)

Uso: python backtest_bybit_2y.py
     (requiere haber corrido download_bybit.py primero)
"""
import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ── Parametros (mismos que config.py v6 optimizado) ────────────────────────
INITIAL_CAPITAL   = 10_000
RISK_PCT          = 0.012      # v8c: 1.2% por operacion (era 1.5%)

EMA_FAST          = 20
EMA_SLOW          = 50
EMA_TREND         = 200
EMA_MACRO         = 500        # ~20 dias en H1 — filtro macro
MACD_FAST         = 12
MACD_SLOW         = 26
MACD_SIGNAL       = 9
RSI_PERIOD        = 14
ATR_PERIOD        = 14
ADX_PERIOD        = 14

ADX_MIN           = 25
RSI_LONG_MIN      = 38
RSI_LONG_MAX      = 72
RSI_SHORT_MIN     = 28
RSI_SHORT_MAX     = 62

ORB_HOUR_START    = 0
ORB_HOUR_END      = 4
ORB_HOUR_CLOSE    = 20
ORB_MIN_RANGE_PCT = 0.003      # v9: igual que v7

ATR_SL_MULT       = 1.2        # v9: igual que v7
TP_RR             = 2.2        # v9b: igual que v7, optimo con EOD close a 20h UTC
ATR_TRAIL_MULT    = 1.0
ATR_VOL_MULT      = 1.8        # v9: igual que v7

CFT_MAX_DD        = 0.10
CFT_DAILY_DD      = 0.05
CFT_TARGET        = 0.08

CSV_FILE          = "btcusdt_h1_bybit.csv"

# ── Carga de datos ──────────────────────────────────────────────────────────
print("=" * 65)
print("  BACKTEST 2 ANOS | BTCUSDT H1 | Datos reales Bybit")
print("  Estrategia: ORB + MACD/RSI + EMA500 macro | Risk 1.5%")
print("=" * 65)

if not os.path.exists(CSV_FILE):
    print(f"Archivo {CSV_FILE} no encontrado.")
    print("Ejecuta primero: python download_bybit.py")
    exit(1)

df_raw = pd.read_csv(CSV_FILE, parse_dates=["datetime"])
df_raw.set_index("datetime", inplace=True)
df_raw.sort_index(inplace=True)
if df_raw.index.tz is not None:
    df_raw.index = df_raw.index.tz_localize(None)
df_raw = df_raw[["open","high","low","close","volume"]].dropna()

print(f"  Datos cargados: {len(df_raw):,} velas H1")
print(f"  Rango total   : {df_raw.index[0].date()} - {df_raw.index[-1].date()}")
print(f"  BTC inicio    : ${df_raw['close'].iloc[0]:,.0f}")
print(f"  BTC fin       : ${df_raw['close'].iloc[-1]:,.0f}")
print(f"  Variacion BTC : {(df_raw['close'].iloc[-1]/df_raw['close'].iloc[0]-1)*100:+.1f}%")
print()

# ── Indicadores ──────────────────────────────────────────────────────────────
c, h, l = df_raw["close"], df_raw["high"], df_raw["low"]

df_raw["ema20"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
df_raw["ema50"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
df_raw["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()
df_raw["ema500"] = c.ewm(span=EMA_MACRO, adjust=False).mean()

tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
df_raw["atr"] = tr.rolling(ATR_PERIOD).mean()

delta = c.diff()
gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
loss_ = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
df_raw["rsi"] = 100 - (100 / (1 + gain / loss_.replace(0, np.nan)))

ema_f              = c.ewm(span=MACD_FAST,   adjust=False).mean()
ema_s              = c.ewm(span=MACD_SLOW,   adjust=False).mean()
df_raw["macd"]     = ema_f - ema_s
df_raw["macd_sig"] = df_raw["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
df_raw["macd_hist"]= df_raw["macd"] - df_raw["macd_sig"]
df_raw["macd_hist_prev"] = df_raw["macd_hist"].shift(1)

up  = h.diff(); dn = -l.diff()
pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.0), index=df_raw.index)
mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.0), index=df_raw.index)
atr14 = tr.rolling(ADX_PERIOD).mean()
pdi   = 100 * pdm.rolling(ADX_PERIOD).mean() / atr14
mdi   = 100 * mdm.rolling(ADX_PERIOD).mean() / atr14
dx    = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
df_raw["adx"] = dx.rolling(ADX_PERIOD).mean()

# ── ATR medio (para filtro de volatilidad extrema) ────────────────────────────
df_raw["atr_avg20"] = df_raw["atr"].rolling(20).mean()

# ── Pendiente EMA200 (filtro de direccion macro) ───────────────────────────────
# Si EMA200 sube en las ultimas 48h -> tendencia alcista real; si baja -> bajista
df_raw["ema200_48h"] = df_raw["ema200"].shift(48)

# ── ORB por dia ──────────────────────────────────────────────────────────────
df_raw["_hour"] = df_raw.index.hour
df_raw["_date"] = df_raw.index.date
orb_high_map, orb_low_map = {}, {}
for date_val, group in df_raw.groupby("_date"):
    rng = group[(group["_hour"] >= ORB_HOUR_START) & (group["_hour"] < ORB_HOUR_END)]
    if len(rng) >= 2:
        orb_high_map[date_val] = rng["high"].max()
        orb_low_map[date_val]  = rng["low"].min()
df_raw["orb_high"] = df_raw["_date"].map(orb_high_map)
df_raw["orb_low"]  = df_raw["_date"].map(orb_low_map)

df_all = df_raw.dropna(subset=["ema500","adx","orb_high","ema200_48h"])

# ── Periodo real de prueba: 2 anos ───────────────────────────────────────────
# Warmup: primeros 6 meses de datos para calentar EMA500 (necesita ~500 velas)
BACKTEST_START = "2024-07-01"   # inicio real (6 meses de warmup desde Ene 2024)
df = df_all[df_all.index >= BACKTEST_START].copy()

print(f"  Periodo backtest: {df.index[0].date()} - {df.index[-1].date()}")
print(f"  Velas de prueba : {len(df):,}")
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
        # Cierre EOD
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
                "exit_reason": "EOD", "btc_price": row["close"]
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
                "type": pos["type"], "entry": pos["entry"],
                "exit": exit_price, "lot": pos["lot"],
                "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                "exit_reason": "TP" if tp_hit else "SL", "btc_price": row["close"]
            })
            pos = None
        continue

    # Guardas CFT — drawdown calculado desde PEAK (trailing DD, estandar en prop firms)
    if peak > 0 and (capital - peak) / peak <= -CFT_MAX_DD: continue
    if (capital - daily_start[dt]) / daily_start[dt] <= -CFT_DAILY_DD: continue
    if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE): continue
    if pd.isna(row["orb_high"]) or pd.isna(row["orb_low"]): continue

    orb_range = row["orb_high"] - row["orb_low"]
    if orb_range / row["close"] < ORB_MIN_RANGE_PCT: continue

    # v7: filtro de volatilidad extrema — no operar cuando el mercado es demasiado errático
    if not pd.isna(row["atr_avg20"]) and row["atr"] > ATR_VOL_MULT * row["atr_avg20"]:
        continue

    adx_ok       = row["adx"] >= ADX_MIN
    trend_up     = row["ema50"] > row["ema200"]
    trend_dn     = row["ema50"] < row["ema200"]
    mom_up       = row["ema20"] > row["ema50"]
    mom_dn       = row["ema20"] < row["ema50"]
    macro_up     = row["close"] > row["ema500"]
    macro_dn     = row["close"] < row["ema500"]
    ema200_up    = row["ema200"] > row["ema200_48h"]  # v9b: EMA200 subiendo en 48h
    ema200_dn    = row["ema200"] < row["ema200_48h"]  # v9b: EMA200 bajando en 48h
    macd_bull    = row["macd_hist"] > 0
    macd_bear    = row["macd_hist"] < 0
    orb_up    = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
    orb_dn    = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

    sl_dist = ATR_SL_MULT * row["atr"]
    tp_dist = sl_dist * TP_RR

    # v7: reduccion dinamica de riesgo segun distancia al limite de DD
    dd_pct_used = abs((capital - peak) / peak) if peak > 0 else 0
    if dd_pct_used >= 0.06:        # v9: >6% DD: reducir a 0.4%
        risk_now = 0.004
    elif dd_pct_used >= 0.04:      # v9: 4-6% DD: reducir a 0.6%
        risk_now = 0.006
    else:
        risk_now = RISK_PCT        # v9: 1.2% base

    lot = max(0.001, round((capital * risk_now) / sl_dist, 4))

    if (orb_up and macro_up and trend_up and mom_up and ema200_up and macd_bull and adx_ok
            and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
        pos = {"type": "long",  "entry": row["close"],
               "sl": row["close"] - sl_dist, "tp": row["close"] + tp_dist,
               "lot": lot, "entry_date": df.index[i]}

    elif (orb_dn and macro_dn and trend_dn and mom_dn and ema200_dn and macd_bear and adx_ok
            and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
        pos = {"type": "short", "entry": row["close"],
               "sl": row["close"] + sl_dist, "tp": row["close"] - tp_dist,
               "lot": lot, "entry_date": df.index[i]}

# ── Metricas ─────────────────────────────────────────────────────────────────
df_t = pd.DataFrame(trades)
if df_t.empty:
    print("Sin trades generados."); exit()

wins = df_t[df_t["pnl_usd"] > 0]
loss = df_t[df_t["pnl_usd"] <= 0]
tps  = df_t[df_t["exit_reason"] == "TP"]
sls  = df_t[df_t["exit_reason"] == "SL"]
eods = df_t[df_t["exit_reason"] == "EOD"]

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
    if pk > 0:
        dd_max = min(dd_max, (v - pk) / pk * 100)

# Analisis por ano
df_t["year"] = pd.to_datetime(df_t["exit_date"]).dt.year
yearly = {}
for year, grp in df_t.groupby("year"):
    y_wins = grp[grp["pnl_usd"] > 0]
    y_loss = grp[grp["pnl_usd"] <= 0]
    y_pf   = y_wins["pnl_usd"].sum() / abs(y_loss["pnl_usd"].sum()) if len(y_loss) and y_loss["pnl_usd"].sum() != 0 else 999
    yearly[year] = {
        "trades": len(grp),
        "wr":     len(y_wins)/len(grp)*100,
        "pnl":    grp["pnl_usd"].sum(),
        "pf":     y_pf,
        "ret":    grp["pnl_usd"].sum() / INITIAL_CAPITAL * 100,
    }

# Mejor/peor mes
df_t["month"] = pd.to_datetime(df_t["exit_date"]).dt.to_period("M")
monthly_pnl = df_t.groupby("month")["pnl_usd"].sum()
best_month   = monthly_pnl.idxmax() if len(monthly_pnl) else None
worst_month  = monthly_pnl.idxmin() if len(monthly_pnl) else None

# CFT challenges simulados (cuantos challenges de $10k hubieran pasado)
target_bal = INITIAL_CAPITAL * (1 + CFT_TARGET)
challenges_passed = 0
in_challenge = True
challenge_start_cap = INITIAL_CAPITAL
challenge_peak = INITIAL_CAPITAL
for t in df_t.itertuples():
    if not in_challenge:
        in_challenge = True
        challenge_start_cap = t.capital
        challenge_peak = t.capital
    challenge_peak = max(challenge_peak, t.capital)
    dd_from_start = (t.capital - challenge_start_cap) / challenge_start_cap
    if t.capital >= challenge_start_cap * (1 + CFT_TARGET):
        challenges_passed += 1
        in_challenge = False
    elif dd_from_start <= -CFT_MAX_DD:
        in_challenge = False  # quemada

streak = ms = 0
for p in df_t["pnl_usd"]:
    if p <= 0: streak += 1; ms = max(ms, streak)
    else: streak = 0

months_total = max(1, (df_t["exit_date"].iloc[-1] - df_t["entry_date"].iloc[0]).days / 30)

# ── REPORTE ───────────────────────────────────────────────────────────────────
W = 65; SEP = "=" * W; S2 = "-" * W

print(); print(SEP)
print("  BACKTEST 2 ANOS: Jul 2024 - Jun 2026")
print("  Estrategia: ORB + MACD/RSI | BTCUSDT H1 | Risk 1.5%")
print("  Fuente: Bybit API (datos reales de mercado)")
print("  BTC: $42,517 -> $61,512 (+44.7% en el periodo)")
print(SEP)
print("  {:<32} {:>14}   {:>10}".format("METRICA", "RESULTADO", "CFT REF"))
print(S2)
print("  {:<32} {:>14}   {:>10}".format("Trades totales", n, "--"))
print("  {:<32} {:>14}   {:>10}".format("Ganadores", f"{len(wins)} ({wr:.1f}%)", ">50%"))
print("  {:<32} {:>14}   {:>10}".format("Perdedores", f"{len(loss)} ({100-wr:.1f}%)", "--"))
print("  {:<32} {:>14}   {:>10}".format("  -> Por TP", len(tps), "--"))
print("  {:<32} {:>14}   {:>10}".format("  -> Por SL", len(sls), "--"))
print("  {:<32} {:>14}   {:>10}".format("  -> Cierre EOD", len(eods), "--"))
print("  {:<32} {:>14}   {:>10}".format("Promedio ganancia", f"${aw:,.0f}", "--"))
print("  {:<32} {:>14}   {:>10}".format("Promedio perdida", f"${al:,.0f}", "--"))
print("  {:<32} {:>14}   {:>10}".format("Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
print("  {:<32} {:>14}   {:>10}".format("Profit Factor", f"{pf:.2f}", ">1.5"))
print("  {:<32} {:>14}   {:>10}".format("Trades / mes", f"{n/months_total:.1f}", "--"))
print("  {:<32} {:>14}   {:>10}".format("Retorno total 2 anos", f"{ret:+.1f}%", "--"))
print("  {:<32} {:>14}   {:>10}".format("Capital final", f"${fin:,.0f}", "--"))
print("  {:<32} {:>14}   {:>10}".format("Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
print("  {:<32} {:>14}   {:>10}".format("Racha max perdidas", f"{ms} trades", "<8"))
print("  {:<32} {:>14}   {:>10}".format("Mejor mes P&L", f"${monthly_pnl.max():+,.0f}" if best_month else "--", "--"))
print("  {:<32} {:>14}   {:>10}".format("Peor mes P&L", f"${monthly_pnl.min():+,.0f}" if worst_month else "--", "--"))
print(S2)
print("  {:<32} {:>14}   {:>10}".format("Challenges CFT pasados", f"{challenges_passed}", "--"))
print(SEP)

# Analisis por ano
print()
print("  RENDIMIENTO POR ANO")
print(S2)
print("  {:<8} {:>8} {:>12} {:>10} {:>8} {:>10}".format(
    "ANO", "TRADES", "WINRATE", "P&L", "PF", "RET ANUAL"))
print("  " + "-" * 60)
for year, d in sorted(yearly.items()):
    ok = "[OK]" if d["pf"] > 1.5 else "[  ]"
    print("  {:<8} {:>8} {:>11.1f}% ${:>9,.0f} {:>8.2f} {:>+9.1f}%  {}".format(
        year, d["trades"], d["wr"], d["pnl"], d["pf"], d["ret"], ok))
print(SEP)

# Evaluacion CFT
print()
print("  EVALUACION CRYPTO FUND TRADER (por challenge)")
print(S2)
checks = [
    ("Profit Factor > 1.5",    pf > 1.5,    f"{pf:.2f}"),
    ("Winrate > 40%",          wr > 40,     f"{wr:.1f}%"),
    ("Ratio G/P > 1.5x",      gpr > 1.5,   f"{gpr:.2f}x"),
    ("Max DD < 10%",           abs(dd_max) < 10, f"{dd_max:+.1f}%"),
    ("Racha perdidas < 8",     ms < 8,      f"{ms} trades"),
    ("Rentable en 2 anos",     ret > 0,     f"{ret:+.1f}%"),
]
for label, ok, val in checks:
    print(f"  {'[OK]' if ok else '[XX]'}  {label:<30} {val:>10}")
print(SEP)

# Historial compacto (ultimos/primeros por ano)
print()
print("  HISTORIAL DE TRADES (todos)")
print(S2)
print("  {:<16} {:<16} {:5} {:>10} {:>10} {:>7} {:>4} {:>9} {:>10}".format(
    "Entrada", "Salida", "Tipo", "Entry BTC", "Exit BTC", "Lot", "Sal", "P&L", "Capital"))
print("  " + "-" * 99)
for _, t in df_t.iterrows():
    flag   = " WIN" if t["pnl_usd"] > 0 else "    "
    reason = t.get("exit_reason","?")
    print("  {:<16} {:<16} {:5} {:>10,.0f} {:>10,.0f} {:>7.4f} {:>4} ${:>+8,.0f} ${:>9,.0f}{}".format(
        str(t["entry_date"])[:16], str(t["exit_date"])[:16],
        t["type"][0].upper(), t["entry"], t["exit"],
        t["lot"], reason, t["pnl_usd"], t["capital"], flag))
print(); print(SEP)

# Guardar trades a CSV para analisis
df_t.to_csv("backtest_bybit_trades.csv", index=False)
print(f"  Trades exportados: backtest_bybit_trades.csv")
print(SEP)
