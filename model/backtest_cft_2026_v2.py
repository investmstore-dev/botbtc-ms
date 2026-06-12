"""
BACKTEST CFT 2026 v2 | Con Filtros de Sentimiento
  - Funding Rate Bybit (cada 8h): bias de mercado real
  - Fear & Greed Index (diario): sentimiento macro

LOGICA:
  LONG  permitido si: funding_rate >= -0.0002  AND  fg_value >= 40
  SHORT permitido si: funding_rate <=  0.0005  AND  fg_value <= 65

En mercado bajista (2026):
  - Funding negativo  ->  bloquea longs falsos
  - F&G en Fear/Extreme Fear  ->  bloquea longs, habilita shorts

Periodo test: 01 Ene 2026 - 11 Jun 2026
Periodo 2yr : 01 Jul 2024 - 11 Jun 2026  (para validar que no rompe el resto)

Uso: python backtest_cft_2026_v2.py
"""
import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ── Parametros estrategia v9b (igual que backtest_bybit_2y.py) ───────────────
INITIAL_CAPITAL   = 10_000
RISK_PCT          = 0.012

EMA_FAST, EMA_SLOW, EMA_TREND, EMA_MACRO = 20, 50, 200, 500
MACD_FAST, MACD_SLOW, MACD_SIGNAL       = 12, 26, 9
RSI_PERIOD, ATR_PERIOD, ADX_PERIOD       = 14, 14, 14

ADX_MIN           = 25
RSI_LONG_MIN, RSI_LONG_MAX   = 38, 72
RSI_SHORT_MIN, RSI_SHORT_MAX = 28, 62

ORB_HOUR_START    = 0
ORB_HOUR_END      = 4
ORB_HOUR_CLOSE    = 20
ORB_MIN_RANGE_PCT = 0.003

ATR_SL_MULT       = 1.2
TP_RR             = 2.2
ATR_TRAIL_MULT    = 1.0
ATR_VOL_MULT      = 1.8

CFT_MAX_DD        = 0.10
CFT_DAILY_DD      = 0.05

# ── Umbrales de sentimiento ───────────────────────────────────────────────────
# Funding rate: cada 8h. Negativo = market short-bias = bear
FUND_LONG_MIN     = -0.0002   # bloquear LONG si funding < -0.02% (mercado apostando a la baja)
FUND_SHORT_MAX    =  0.0005   # bloquear SHORT si funding > +0.05% (mercado eufórico alcista)

# Fear & Greed: 0=Extreme Fear, 100=Extreme Greed
FG_LONG_MIN       = 40        # bloquear LONG si F&G < 40 (mercado con miedo)
FG_SHORT_MAX      = 65        # bloquear SHORT si F&G > 65 (mercado codicioso)

CSV_PRICE    = "btcusdt_h1_bybit.csv"
CSV_FUNDING  = "btcusdt_funding_rate.csv"
CSV_FG       = "fear_greed_index.csv"

# ── Carga de datos ────────────────────────────────────────────────────────────
for f in [CSV_PRICE, CSV_FUNDING, CSV_FG]:
    if not os.path.exists(f):
        print(f"Falta: {f}. Ejecuta primero download_bybit.py y download_sentiment.py")
        exit(1)

df_raw = pd.read_csv(CSV_PRICE, parse_dates=["datetime"])
df_raw.set_index("datetime", inplace=True)
df_raw.sort_index(inplace=True)
if df_raw.index.tz is not None:
    df_raw.index = df_raw.index.tz_localize(None)
df_raw = df_raw[["open","high","low","close","volume"]].dropna()

# Funding rate: ultimo conocido para cada hora
df_fund = pd.read_csv(CSV_FUNDING, parse_dates=["datetime"])
df_fund.set_index("datetime", inplace=True)
df_fund.sort_index(inplace=True)

# Fear & Greed: por fecha
df_fg = pd.read_csv(CSV_FG, parse_dates=["date"])
df_fg.set_index("date", inplace=True)
df_fg.sort_index(inplace=True)

# ── Indicadores tecnicos ──────────────────────────────────────────────────────
c, h, l = df_raw["close"], df_raw["high"], df_raw["low"]
df_raw["ema20"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
df_raw["ema50"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
df_raw["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()
df_raw["ema500"] = c.ewm(span=EMA_MACRO, adjust=False).mean()

tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
df_raw["atr"] = tr.rolling(ATR_PERIOD).mean()

delta = c.diff()
gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
loss_ = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
df_raw["rsi"] = 100 - (100 / (1 + gain / loss_.replace(0, np.nan)))

ema_f               = c.ewm(span=MACD_FAST,   adjust=False).mean()
ema_s               = c.ewm(span=MACD_SLOW,   adjust=False).mean()
df_raw["macd"]      = ema_f - ema_s
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

df_raw["atr_avg20"]  = df_raw["atr"].rolling(20).mean()
df_raw["ema200_48h"] = df_raw["ema200"].shift(48)

# ── ORB por dia ───────────────────────────────────────────────────────────────
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

# ── Merge sentimiento en H1 ────────────────────────────────────────────────────
# Funding rate: forward-fill al timeframe H1
fund_h1 = df_fund["funding_rate"].reindex(df_raw.index, method="ffill")
df_raw["funding_rate"] = fund_h1

# Fear & Greed: mapear por fecha
df_raw["fg_value"] = df_raw.index.date
df_raw["fg_value"] = df_raw["fg_value"].map(df_fg["fg_value"].to_dict())
df_raw["fg_value"] = df_raw["fg_value"].ffill()

df_all = df_raw.dropna(subset=["ema500","adx","orb_high","ema200_48h","funding_rate","fg_value"])

# ── Funcion de simulacion ──────────────────────────────────────────────────────
def run_backtest(df, use_sentiment=True, label=""):
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
                    "type": pos["type"], "entry": pos["entry"], "exit": row["close"],
                    "lot": pos["lot"], "pnl_usd": round(pnl, 2),
                    "capital": round(capital, 2), "exit_reason": "EOD",
                    "funding": pos["funding"], "fg": pos["fg"],
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
                    "type": pos["type"], "entry": pos["entry"], "exit": exit_price,
                    "lot": pos["lot"], "pnl_usd": round(pnl, 2),
                    "capital": round(capital, 2), "exit_reason": "TP" if tp_hit else "SL",
                    "funding": pos["funding"], "fg": pos["fg"],
                })
                pos = None
            continue

        # Guardas CFT
        if peak > 0 and (capital - peak) / peak <= -CFT_MAX_DD: continue
        if (capital - daily_start[dt]) / daily_start[dt] <= -CFT_DAILY_DD: continue
        if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE): continue
        if pd.isna(row["orb_high"]) or pd.isna(row["orb_low"]): continue

        orb_range = row["orb_high"] - row["orb_low"]
        if orb_range / row["close"] < ORB_MIN_RANGE_PCT: continue
        if not pd.isna(row["atr_avg20"]) and row["atr"] > ATR_VOL_MULT * row["atr_avg20"]: continue

        adx_ok    = row["adx"] >= ADX_MIN
        trend_up  = row["ema50"] > row["ema200"]
        trend_dn  = row["ema50"] < row["ema200"]
        mom_up    = row["ema20"] > row["ema50"]
        mom_dn    = row["ema20"] < row["ema50"]
        macro_up  = row["close"] > row["ema500"]
        macro_dn  = row["close"] < row["ema500"]
        ema200_up = row["ema200"] > row["ema200_48h"]
        ema200_dn = row["ema200"] < row["ema200_48h"]
        macd_bull = row["macd_hist"] > 0
        macd_bear = row["macd_hist"] < 0
        orb_up    = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
        orb_dn    = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

        # Filtros de sentimiento (v2 nuevo)
        if use_sentiment:
            fr = row["funding_rate"]
            fg = row["fg_value"]
            long_ok_sent  = (fr >= FUND_LONG_MIN)  and (fg >= FG_LONG_MIN)
            short_ok_sent = (fr <= FUND_SHORT_MAX) and (fg <= FG_SHORT_MAX)
        else:
            long_ok_sent  = True
            short_ok_sent = True

        sl_dist = ATR_SL_MULT * row["atr"]
        tp_dist = sl_dist * TP_RR

        dd_pct = abs((capital - peak) / peak) if peak > 0 else 0
        if dd_pct >= 0.06:    risk_now = 0.004
        elif dd_pct >= 0.04:  risk_now = 0.006
        else:                 risk_now = RISK_PCT

        lot = max(0.001, round((capital * risk_now) / sl_dist, 4))
        fr_val = row.get("funding_rate", 0)
        fg_val = row.get("fg_value", 50)

        if (long_ok_sent and orb_up and macro_up and trend_up and mom_up
                and ema200_up and macd_bull and adx_ok
                and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
            pos = {"type": "long", "entry": row["close"],
                   "sl": row["close"] - sl_dist, "tp": row["close"] + tp_dist,
                   "lot": lot, "entry_date": df.index[i],
                   "funding": fr_val, "fg": fg_val}

        elif (short_ok_sent and orb_dn and macro_dn and trend_dn and mom_dn
                and ema200_dn and macd_bear and adx_ok
                and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
            pos = {"type": "short", "entry": row["close"],
                   "sl": row["close"] + sl_dist, "tp": row["close"] - tp_dist,
                   "lot": lot, "entry_date": df.index[i],
                   "funding": fr_val, "fg": fg_val}

    return pd.DataFrame(trades)


def print_report(df_t, label, period_start, period_end, show_trades=True):
    SEP = "=" * 67; S2 = "-" * 67
    if df_t.empty:
        print(f"\n  {label}: Sin trades.\n")
        return {}

    wins = df_t[df_t["pnl_usd"] > 0]
    loss = df_t[df_t["pnl_usd"] <= 0]
    tps  = df_t[df_t["exit_reason"] == "TP"]
    sls  = df_t[df_t["exit_reason"] == "SL"]
    eods = df_t[df_t["exit_reason"] == "EOD"]

    n   = len(df_t)
    wr  = len(wins) / n * 100
    aw  = wins["pnl_usd"].mean() if len(wins) else 0
    al  = loss["pnl_usd"].mean() if len(loss) else 0
    pf  = wins["pnl_usd"].sum() / abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum() != 0 else 999
    fin = df_t["capital"].iloc[-1]
    ret = (fin - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    gpr = abs(aw / al) if al else 0

    eq = [INITIAL_CAPITAL] + df_t["capital"].tolist()
    pk = eq[0]; dd_max = 0.0
    for v in eq:
        pk = max(pk, v)
        if pk > 0: dd_max = min(dd_max, (v - pk) / pk * 100)

    streak = ms = 0
    for p in df_t["pnl_usd"]:
        if p <= 0: streak += 1; ms = max(ms, streak)
        else: streak = 0

    trading_days = df_t["entry_date"].dt.date.nunique()
    longs  = df_t[df_t["type"] == "long"]
    shorts = df_t[df_t["type"] == "short"]

    print(); print(SEP)
    print(f"  {label}")
    print(f"  Periodo: {period_start} a {period_end}")
    print(SEP)
    print("  {:<34} {:>14}   {:>8}".format("METRICA", "RESULTADO", "CFT REF"))
    print(S2)
    print("  {:<34} {:>14}   {:>8}".format("Trades totales", n, "--"))
    print("  {:<34} {:>14}   {:>8}".format("  Longs", f"{len(longs)} ({len(longs)/n*100:.0f}%)", "--"))
    print("  {:<34} {:>14}   {:>8}".format("  Shorts", f"{len(shorts)} ({len(shorts)/n*100:.0f}%)", "--"))
    print("  {:<34} {:>14}   {:>8}".format("Dias operados", trading_days, ">= 5"))
    print("  {:<34} {:>14}   {:>8}".format("Ganadores", f"{len(wins)} ({wr:.1f}%)", "--"))
    print("  {:<34} {:>14}   {:>8}".format("  -> Por TP", len(tps), "--"))
    print("  {:<34} {:>14}   {:>8}".format("  -> Por SL", len(sls), "--"))
    print("  {:<34} {:>14}   {:>8}".format("  -> Cierre EOD", len(eods), "--"))
    print("  {:<34} {:>14}   {:>8}".format("Promedio ganancia", f"${aw:,.0f}", "--"))
    print("  {:<34} {:>14}   {:>8}".format("Promedio perdida", f"${al:,.0f}", "--"))
    print("  {:<34} {:>14}   {:>8}".format("Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
    print("  {:<34} {:>14}   {:>8}".format("Profit Factor", f"{pf:.2f}", ">1.2"))
    print("  {:<34} {:>14}   {:>8}".format("Capital final", f"${fin:,.0f}", "--"))
    print("  {:<34} {:>14}   {:>8}".format("Retorno total", f"{ret:+.1f}%", "+8% P1"))
    print("  {:<34} {:>14}   {:>8}".format("Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
    print("  {:<34} {:>14}   {:>8}".format("Racha max perdidas", f"{ms} trades", "< 8"))
    print(S2)

    p1_ok   = fin >= INITIAL_CAPITAL * 1.08
    dd_ok   = abs(dd_max) < 10
    days_ok = trading_days >= 5
    print()
    print("  CFT PHASE 1 (+8% / -10% DD / min 5 dias)")
    print(S2)
    print(f"  {'[OK]' if p1_ok  else '[XX]'}  Profit target +8%       {ret:+.1f}%")
    print(f"  {'[OK]' if dd_ok  else '[XX]'}  Max DD < 10%            {dd_max:+.1f}%")
    print(f"  {'[OK]' if days_ok else '[XX]'}  Min 5 dias              {trading_days} dias")
    if p1_ok and dd_ok and days_ok:
        print(f"\n  *** CFT PHASE 1 PASADA ***")
    else:
        falta = INITIAL_CAPITAL * 1.08 - fin
        if falta > 0:
            print(f"\n  Falta: ${falta:,.0f} ({ret:+.1f}% de 8% objetivo)")
    print(SEP)

    if show_trades:
        print()
        print("  HISTORIAL DE TRADES")
        print(S2)
        print("  {:<16} {:<16} {:5} {:>10} {:>10} {:>4} {:>9} {:>10}  {:>5} {:>4}".format(
            "Entrada", "Salida", "Tipo", "BTC Entry", "BTC Exit", "Sal", "P&L", "Capital", "Fund", "F&G"))
        print("  " + "-" * 100)
        for _, t in df_t.iterrows():
            flag = " WIN" if t["pnl_usd"] > 0 else "    "
            fr_s = f"{t.get('funding',0)*10000:+.2f}bp"
            fg_s = f"{int(t.get('fg',50)):3d}"
            print("  {:<16} {:<16} {:5} {:>10,.0f} {:>10,.0f} {:>4} ${:>+8,.0f} ${:>9,.0f}  {:>5} {:>4}{}".format(
                str(t["entry_date"])[:16], str(t["exit_date"])[:16],
                t["type"][0].upper(), t["entry"], t["exit"],
                t.get("exit_reason","?"), t["pnl_usd"], t["capital"],
                fr_s, fg_s, flag))
        print()

    return {"n": n, "wr": wr, "pf": pf, "ret": ret, "dd": dd_max, "fin": fin,
            "longs": len(longs), "shorts": len(shorts), "ms": ms}


# ── EJECUTAR: periodo 2026 con y sin sentimiento ─────────────────────────────
W = 67; SEP = "=" * W
print(SEP)
print("  BACKTEST CFT 2026 v2 | Con Filtros de Sentimiento")
print("  Funding Rate Bybit + Fear & Greed Index (alternative.me)")
print(SEP)

# Periodo 2026
df_2026 = df_all[(df_all.index >= "2026-01-01") & (df_all.index <= "2026-06-11")].copy()
print(f"\n  Velas 2026: {len(df_2026):,} | BTC: ${df_2026['close'].iloc[0]:,.0f} -> ${df_2026['close'].iloc[-1]:,.0f}")
print(f"  F&G promedio 2026: {df_2026['fg_value'].mean():.0f} | Funding negativo: {(df_2026['funding_rate']<0).sum()/len(df_2026)*100:.0f}%")

print("\n  Ejecutando sin sentimiento (baseline)...")
df_base = run_backtest(df_2026.copy(), use_sentiment=False)
r_base = print_report(df_base, "2026 | SIN SENTIMIENTO (baseline v9b)", "2026-01-01", "2026-06-11")

print("\n  Ejecutando CON sentimiento (funding + F&G)...")
df_sent = run_backtest(df_2026.copy(), use_sentiment=True)
r_sent = print_report(df_sent, "2026 | CON SENTIMIENTO (funding rate + Fear & Greed)", "2026-01-01", "2026-06-11")

# ── EJECUTAR: 2 anos completos CON sentimiento ────────────────────────────────
df_2y = df_all[(df_all.index >= "2024-07-01") & (df_all.index <= "2026-06-11")].copy()
print(f"\n  Velas 2 anos: {len(df_2y):,}")
print("\n  Ejecutando backtest 2 ANOS con sentimiento...")
df_2y_sent = run_backtest(df_2y.copy(), use_sentiment=True)
r_2y = print_report(df_2y_sent, "2 ANOS (Jul 2024 - Jun 2026) | CON SENTIMIENTO",
                    "2024-07-01", "2026-06-11", show_trades=False)

# Analisis por ano - 2 anos
print()
print("  RENDIMIENTO POR ANO (con sentimiento)")
print("-" * W)
df_2y_sent["year"] = pd.to_datetime(df_2y_sent["exit_date"]).dt.year
print("  {:<8} {:>8} {:>11} {:>10} {:>8} {:>10}".format("ANO","TRADES","WINRATE","P&L","PF","RET ANUAL"))
print("  " + "-" * 60)
for year, grp in df_2y_sent.groupby("year"):
    yw = grp[grp["pnl_usd"] > 0]
    yl = grp[grp["pnl_usd"] <= 0]
    ypf = yw["pnl_usd"].sum()/abs(yl["pnl_usd"].sum()) if len(yl) and yl["pnl_usd"].sum()!=0 else 999
    ok = "[OK]" if ypf > 1.2 else "[  ]"
    print("  {:<8} {:>8} {:>10.1f}% ${:>9,.0f} {:>8.2f} {:>+9.1f}%  {}".format(
        year, len(grp), len(yw)/len(grp)*100, grp["pnl_usd"].sum(), ypf,
        grp["pnl_usd"].sum()/INITIAL_CAPITAL*100, ok))

# Challenges simulados 2 anos
eq = [INITIAL_CAPITAL] + df_2y_sent["capital"].tolist()
pk = eq[0]; dd_max_2y = 0.0
for v in eq:
    pk = max(pk, v)
    if pk > 0: dd_max_2y = min(dd_max_2y, (v-pk)/pk*100)

challenges = 0; in_ch = True; ch_cap = INITIAL_CAPITAL; ch_pk = INITIAL_CAPITAL
for t in df_2y_sent.itertuples():
    if not in_ch:
        in_ch = True; ch_cap = t.capital; ch_pk = t.capital
    ch_pk = max(ch_pk, t.capital)
    if t.capital >= ch_cap * 1.08:
        challenges += 1; in_ch = False
    elif (t.capital - ch_cap) / ch_cap <= -0.10:
        in_ch = False

print("=" * W)
print(f"  Retorno 2 anos : {r_2y.get('ret',0):+.1f}%")
print(f"  Capital final  : ${df_2y_sent['capital'].iloc[-1]:,.0f}")
print(f"  Max DD 2 anos  : {dd_max_2y:+.1f}%")
print(f"  Challenges CFT : {challenges}")
print("=" * W)

# ── COMPARATIVA FINAL ─────────────────────────────────────────────────────────
print()
print("=" * W)
print("  COMPARATIVA 2026: SIN vs CON SENTIMIENTO")
print("-" * W)
print("  {:<30} {:>15} {:>15}".format("METRICA", "Sin Sentim.", "Con Sentim."))
print("-" * W)
for key, label in [("n","Trades"), ("wr","Winrate %"), ("pf","Profit Factor"),
                    ("ret","Retorno"), ("dd","Max Drawdown"), ("longs","Longs"),
                    ("shorts","Shorts"), ("ms","Racha max SL")]:
    v1 = r_base.get(key, 0); v2 = r_sent.get(key, 0)
    if key in ("wr","ret","dd"):
        print("  {:<30} {:>14.1f}% {:>14.1f}%".format(label, v1, v2))
    elif key == "pf":
        print("  {:<30} {:>15.2f} {:>15.2f}".format(label, v1, v2))
    else:
        print("  {:<30} {:>15} {:>15}".format(label, v1, v2))
print("=" * W)

# Exportar trades 2026 con sentimiento
df_sent.to_csv("test_2026_sentiment.csv", index=False)
df_2y_sent.to_csv("test_2y_sentiment.csv", index=False)
print(f"\n  Exportado: test_2026_sentiment.csv  |  test_2y_sentiment.csv")
print("=" * W)
