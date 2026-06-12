"""
TEST CFT 2026 | BTCUSDT H1 | Datos reales Bybit
Periodo: 01 Ene 2026 - 11 Jun 2026

TEST 1: Estrategia v9b (ORB + MACD/RSI + EMA200 pendiente)
TEST 2: Estrategia v9b + Martingala (doblar riesgo tras perdida, max 3x)

Cuenta objetivo: Crypto Fund Trader 2 PHASES $10k
  Phase 1: +8%  target | -10% max DD | -5% daily DD | min 5 dias
  Phase 2: +5%  target | -10% max DD | -5% daily DD | min 5 dias

Uso: python backtest_cft_2026.py
"""
import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ── Parametros estrategia v9b ───────────────────────────────────────────────
INITIAL_CAPITAL   = 10_000
RISK_PCT          = 0.012      # 1.2% riesgo base

EMA_FAST          = 20
EMA_SLOW          = 50
EMA_TREND         = 200
EMA_MACRO         = 500
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
ORB_MIN_RANGE_PCT = 0.003

ATR_SL_MULT       = 1.2
TP_RR             = 2.2
ATR_TRAIL_MULT    = 1.0
ATR_VOL_MULT      = 1.8

CFT_MAX_DD        = 0.10
CFT_DAILY_DD      = 0.05
CFT_TARGET_P1     = 0.08
CFT_TARGET_P2     = 0.05

# ── Parametros Martingala ────────────────────────────────────────────────────
MART_MAX_MULT     = 3.0        # maximo multiplicador (no mas de 3x riesgo base)
MART_STEP         = 2.0        # multiplicar riesgo por 2 tras cada perdida

CSV_FILE          = "btcusdt_h1_bybit.csv"
TEST_START        = "2026-01-01"
TEST_END          = "2026-06-11"

# ── Carga y preparacion de datos ────────────────────────────────────────────
if not os.path.exists(CSV_FILE):
    print(f"Archivo {CSV_FILE} no encontrado. Ejecuta: python download_bybit.py")
    exit(1)

df_raw = pd.read_csv(CSV_FILE, parse_dates=["datetime"])
df_raw.set_index("datetime", inplace=True)
df_raw.sort_index(inplace=True)
if df_raw.index.tz is not None:
    df_raw.index = df_raw.index.tz_localize(None)
df_raw = df_raw[["open","high","low","close","volume"]].dropna()

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

df_raw["atr_avg20"]   = df_raw["atr"].rolling(20).mean()
df_raw["ema200_48h"]  = df_raw["ema200"].shift(48)   # pendiente EMA200

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
df = df_all[(df_all.index >= TEST_START) & (df_all.index <= TEST_END)].copy()


# ── Funcion de simulacion ────────────────────────────────────────────────────
def run_backtest(df, use_martingale=False, label="TEST"):
    capital     = INITIAL_CAPITAL
    peak        = capital
    trades      = []
    pos         = None
    daily_start = {}
    mart_mult   = 1.0    # multiplicador martingala actual
    consec_loss = 0      # perdidas consecutivas

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
                result = "WIN" if pnl > 0 else "LOSS"
                if use_martingale:
                    if pnl <= 0:
                        consec_loss += 1
                        mart_mult = min(MART_STEP ** consec_loss, MART_MAX_MULT)
                    else:
                        consec_loss = 0
                        mart_mult = 1.0
                trades.append({
                    "entry_date": pos["entry_date"], "exit_date": df.index[i],
                    "type": pos["type"], "entry": pos["entry"],
                    "exit": row["close"], "lot": pos["lot"],
                    "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                    "exit_reason": "EOD", "mart_mult": pos.get("mart_mult", 1.0)
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
                if use_martingale:
                    if pnl <= 0:
                        consec_loss += 1
                        mart_mult = min(MART_STEP ** consec_loss, MART_MAX_MULT)
                    else:
                        consec_loss = 0
                        mart_mult = 1.0
                trades.append({
                    "entry_date": pos["entry_date"], "exit_date": df.index[i],
                    "type": pos["type"], "entry": pos["entry"],
                    "exit": exit_price, "lot": pos["lot"],
                    "pnl_usd": round(pnl, 2), "capital": round(capital, 2),
                    "exit_reason": "TP" if tp_hit else "SL",
                    "mart_mult": pos.get("mart_mult", 1.0)
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

        adx_ok      = row["adx"] >= ADX_MIN
        trend_up    = row["ema50"] > row["ema200"]
        trend_dn    = row["ema50"] < row["ema200"]
        mom_up      = row["ema20"] > row["ema50"]
        mom_dn      = row["ema20"] < row["ema50"]
        macro_up    = row["close"] > row["ema500"]
        macro_dn    = row["close"] < row["ema500"]
        ema200_up   = row["ema200"] > row["ema200_48h"]
        ema200_dn   = row["ema200"] < row["ema200_48h"]
        macd_bull   = row["macd_hist"] > 0
        macd_bear   = row["macd_hist"] < 0
        orb_up      = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
        orb_dn      = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

        sl_dist = ATR_SL_MULT * row["atr"]
        tp_dist = sl_dist * TP_RR

        # Riesgo dinamico: reduccion por DD + martingala
        dd_pct = abs((capital - peak) / peak) if peak > 0 else 0
        if dd_pct >= 0.06:
            base_risk = 0.004
        elif dd_pct >= 0.04:
            base_risk = 0.006
        else:
            base_risk = RISK_PCT

        if use_martingale:
            risk_now = min(base_risk * mart_mult, RISK_PCT * MART_MAX_MULT)
            risk_now = min(risk_now, 0.05)  # cap absoluto al 5% por trade
        else:
            risk_now = base_risk

        lot = max(0.001, round((capital * risk_now) / sl_dist, 4))

        if (orb_up and macro_up and trend_up and mom_up and ema200_up and macd_bull and adx_ok
                and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
            pos = {"type": "long", "entry": row["close"],
                   "sl": row["close"] - sl_dist, "tp": row["close"] + tp_dist,
                   "lot": lot, "entry_date": df.index[i], "mart_mult": mart_mult}

        elif (orb_dn and macro_dn and trend_dn and mom_dn and ema200_dn and macd_bear and adx_ok
                and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
            pos = {"type": "short", "entry": row["close"],
                   "sl": row["close"] + sl_dist, "tp": row["close"] - tp_dist,
                   "lot": lot, "entry_date": df.index[i], "mart_mult": mart_mult}

    return pd.DataFrame(trades)


def print_report(df_t, label, target_p1=CFT_TARGET_P1, target_p2=CFT_TARGET_P2):
    if df_t.empty:
        print(f"\n  {label}: Sin trades generados.\n")
        return

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
        if pk > 0:
            dd_max = min(dd_max, (v - pk) / pk * 100)

    streak = ms = 0
    for p in df_t["pnl_usd"]:
        if p <= 0: streak += 1; ms = max(ms, streak)
        else: streak = 0

    # Dias operados unicos
    trading_days = df_t["entry_date"].dt.date.nunique()

    # Simulacion de fase CFT
    p1_passed = fin >= INITIAL_CAPITAL * (1 + target_p1) and abs(dd_max) < 10
    p1_days   = None
    cap_tmp   = INITIAL_CAPITAL
    for row in df_t.itertuples():
        if cap_tmp >= INITIAL_CAPITAL * (1 + target_p1):
            p1_days = (row.exit_date - df_t["entry_date"].iloc[0]).days
            break
        cap_tmp = row.capital

    W = 65; SEP = "=" * W; S2 = "-" * W
    print(); print(SEP)
    print(f"  {label}")
    print(f"  Periodo: {TEST_START} - {TEST_END}")
    print(f"  BTC: ${df['close'].iloc[0]:,.0f} -> ${df['close'].iloc[-1]:,.0f}")
    print(SEP)
    print("  {:<32} {:>14}   {:>10}".format("METRICA", "RESULTADO", "CFT REF"))
    print(S2)
    print("  {:<32} {:>14}   {:>10}".format("Trades totales", n, "--"))
    print("  {:<32} {:>14}   {:>10}".format("Dias operados", trading_days, ">= 5"))
    print("  {:<32} {:>14}   {:>10}".format("Ganadores", f"{len(wins)} ({wr:.1f}%)", "--"))
    print("  {:<32} {:>14}   {:>10}".format("  -> Por TP", len(tps), "--"))
    print("  {:<32} {:>14}   {:>10}".format("  -> Por SL", len(sls), "--"))
    print("  {:<32} {:>14}   {:>10}".format("  -> Cierre EOD", len(eods), "--"))
    print("  {:<32} {:>14}   {:>10}".format("Promedio ganancia", f"${aw:,.0f}", "--"))
    print("  {:<32} {:>14}   {:>10}".format("Promedio perdida", f"${al:,.0f}", "--"))
    print("  {:<32} {:>14}   {:>10}".format("Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
    print("  {:<32} {:>14}   {:>10}".format("Profit Factor", f"{pf:.2f}", ">1.2"))
    print("  {:<32} {:>14}   {:>10}".format("Capital final", f"${fin:,.0f}", "--"))
    print("  {:<32} {:>14}   {:>10}".format("Retorno total", f"{ret:+.1f}%", "+8% P1"))
    print("  {:<32} {:>14}   {:>10}".format("Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
    print("  {:<32} {:>14}   {:>10}".format("Racha max perdidas", f"{ms} trades", "< 8"))
    print(S2)

    # Evaluacion CFT Phase 1
    p1_ok    = fin >= INITIAL_CAPITAL * (1 + target_p1)
    dd_ok    = abs(dd_max) < 10
    days_ok  = trading_days >= 5

    print()
    print("  EVALUACION CFT PHASE 1 (+8% target)")
    print(S2)
    print(f"  {'[OK]' if p1_ok  else '[XX]'}  Profit target +8%           {ret:+.1f}%")
    print(f"  {'[OK]' if dd_ok  else '[XX]'}  Max DD < 10%                {dd_max:+.1f}%")
    print(f"  {'[OK]' if days_ok else '[XX]'}  Min 5 dias operados         {trading_days} dias")
    if p1_ok and dd_ok and days_ok:
        print(f"\n  *** PHASE 1 PASADA ***")
        if p1_days:
            print(f"  Dias hasta +8%: {p1_days} dias")
    else:
        deficit = INITIAL_CAPITAL * (1 + target_p1) - fin
        if deficit > 0:
            print(f"\n  Falta para +8%: ${deficit:,.0f} ({target_p1*100 - ret:.1f}%)")
    print(SEP)

    # Historial trades
    print()
    print("  HISTORIAL DE TRADES")
    print(S2)
    print("  {:<16} {:<16} {:5} {:>10} {:>10} {:>6} {:>4} {:>9} {:>10}".format(
        "Entrada", "Salida", "Tipo", "BTC Entry", "BTC Exit", "Lot", "Sal", "P&L", "Capital"))
    print("  " + "-" * 92)
    for _, t in df_t.iterrows():
        flag   = " WIN" if t["pnl_usd"] > 0 else "    "
        reason = t.get("exit_reason","?")
        mult_s = f"x{t['mart_mult']:.0f}" if t.get("mart_mult", 1.0) > 1.0 else "   "
        print("  {:<16} {:<16} {:5} {:>10,.0f} {:>10,.0f} {:>6.4f} {:>4} ${:>+8,.0f} ${:>9,.0f} {}{}".format(
            str(t["entry_date"])[:16], str(t["exit_date"])[:16],
            t["type"][0].upper(), t["entry"], t["exit"],
            t["lot"], reason, t["pnl_usd"], t["capital"], flag, mult_s))
    print()


# ── EJECUTAR TESTS ───────────────────────────────────────────────────────────
W = 65; SEP = "=" * W
print(SEP)
print("  TEST CFT 2026 | BTCUSDT H1 | Datos reales Bybit")
print(f"  Periodo: {TEST_START} a {TEST_END}")
print(f"  Velas: {len(df):,} H1 | BTC: ${df['close'].iloc[0]:,.0f} -> ${df['close'].iloc[-1]:,.0f}")
print(SEP)

# ── TEST 1: Estrategia pura v9b ──────────────────────────────────────────────
print("\n  Ejecutando TEST 1 (estrategia v9b)...")
df_t1 = run_backtest(df.copy(), use_martingale=False, label="TEST 1")
print_report(df_t1, "TEST 1: Estrategia v9b (sin Martingala)")
df_t1.to_csv("test1_cft_2026.csv", index=False)
print(f"  Trades exportados: test1_cft_2026.csv")

# ── TEST 2: Estrategia v9b + Martingala ─────────────────────────────────────
print("\n  Ejecutando TEST 2 (v9b + Martingala)...")
df_t2 = run_backtest(df.copy(), use_martingale=True, label="TEST 2")
print_report(df_t2, "TEST 2: Estrategia v9b + Martingala (max 3x)")
df_t2.to_csv("test2_cft_2026.csv", index=False)
print(f"  Trades exportados: test2_cft_2026.csv")

# ── COMPARATIVA FINAL ────────────────────────────────────────────────────────
print()
print(SEP)
print("  COMPARATIVA FINAL")
print("-" * W)
if not df_t1.empty and not df_t2.empty:
    ret1 = (df_t1["capital"].iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    ret2 = (df_t2["capital"].iloc[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    wins1 = df_t1[df_t1["pnl_usd"] > 0]
    wins2 = df_t2[df_t2["pnl_usd"] > 0]
    loss1 = df_t1[df_t1["pnl_usd"] <= 0]
    loss2 = df_t2[df_t2["pnl_usd"] <= 0]
    pf1 = wins1["pnl_usd"].sum() / abs(loss1["pnl_usd"].sum()) if len(loss1) and loss1["pnl_usd"].sum() != 0 else 999
    pf2 = wins2["pnl_usd"].sum() / abs(loss2["pnl_usd"].sum()) if len(loss2) and loss2["pnl_usd"].sum() != 0 else 999

    eq1 = [INITIAL_CAPITAL] + df_t1["capital"].tolist()
    eq2 = [INITIAL_CAPITAL] + df_t2["capital"].tolist()
    pk1 = pk2 = INITIAL_CAPITAL; dd1 = dd2 = 0.0
    for v in eq1:
        pk1 = max(pk1, v)
        if pk1 > 0: dd1 = min(dd1, (v - pk1)/pk1 * 100)
    for v in eq2:
        pk2 = max(pk2, v)
        if pk2 > 0: dd2 = min(dd2, (v - pk2)/pk2 * 100)

    print("  {:<28} {:>14} {:>14}".format("METRICA", "TEST 1 (puro)", "TEST 2 (+Mart)"))
    print("-" * W)
    print("  {:<28} {:>14} {:>14}".format("Trades", len(df_t1), len(df_t2)))
    print("  {:<28} {:>13.1f}% {:>13.1f}%".format("Winrate", len(wins1)/len(df_t1)*100, len(wins2)/len(df_t2)*100))
    print("  {:<28} {:>14.2f} {:>14.2f}".format("Profit Factor", pf1, pf2))
    print("  {:<28} {:>13.1f}% {:>13.1f}%".format("Retorno total", ret1, ret2))
    print("  {:<28} ${:>13,.0f} ${:>13,.0f}".format("Capital final", df_t1["capital"].iloc[-1], df_t2["capital"].iloc[-1]))
    print("  {:<28} {:>13.1f}% {:>13.1f}%".format("Max Drawdown", dd1, dd2))
    p1_t1 = df_t1["capital"].iloc[-1] >= INITIAL_CAPITAL * 1.08 and abs(dd1) < 10
    p1_t2 = df_t2["capital"].iloc[-1] >= INITIAL_CAPITAL * 1.08 and abs(dd2) < 10
    print("  {:<28} {:>14} {:>14}".format("Phase 1 pasada?",
          "SI ✓" if p1_t1 else "NO", "SI ✓" if p1_t2 else "NO"))
print(SEP)
