"""
OPTIMIZACIÓN DOGE | Bajar el Max DD de -10% a ~-7% manteniendo challenges
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reutiliza los datos cacheados en data_backtest/ (DOGE H1 + funding + F&G).
Prueba varias configuraciones de riesgo/filtros y reporta cuál da el mejor
balance entre retorno, drawdown y challenges pasados.

Uso: python model/optimize_doge.py
"""
import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data_backtest")
INITIAL_CAPITAL = 10_000

# ── Indicadores (idénticos a v5b) ────────────────────────────────────────────
def calc_supertrend(df, period=10, mult=3.0):
    hl2 = (df["high"] + df["low"]) / 2
    tr = pd.concat([(df["high"]-df["low"]),
                    (df["high"]-df["close"].shift()).abs(),
                    (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    bu, bl = hl2 + mult*atr, hl2 - mult*atr
    fu, fl = bu.copy(), bl.copy()
    st = pd.Series(np.nan, index=df.index)
    di = pd.Series(0, index=df.index, dtype=int)
    for i in range(1, len(df)):
        fu.iloc[i] = bu.iloc[i] if bu.iloc[i] < fu.iloc[i-1] or df["close"].iloc[i-1] > fu.iloc[i-1] else fu.iloc[i-1]
        fl.iloc[i] = bl.iloc[i] if bl.iloc[i] > fl.iloc[i-1] or df["close"].iloc[i-1] < fl.iloc[i-1] else fl.iloc[i-1]
        prev = st.iloc[i-1]; c = df["close"].iloc[i]
        if pd.isna(prev):           di.iloc[i] = 1
        elif prev == fu.iloc[i-1]:  di.iloc[i] = 1 if c > fu.iloc[i] else -1
        else:                       di.iloc[i] = -1 if c < fl.iloc[i] else 1
        st.iloc[i] = fl.iloc[i] if di.iloc[i] == 1 else fu.iloc[i]
    return st, di


def calc_choppiness(df, period=14):
    tr = pd.concat([(df["high"]-df["low"]),
                    (df["high"]-df["close"].shift()).abs(),
                    (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1)
    atr_sum = tr.rolling(period).sum()
    hh = df["high"].rolling(period).max()
    ll = df["low"].rolling(period).min()
    chop = 100 * np.log10(atr_sum / (hh-ll).replace(0, np.nan)) / np.log10(period)
    return chop.clip(0, 100)


def prepare():
    df = pd.read_csv(os.path.join(CACHE_DIR, "dogeusdt_h1.csv"),
                     parse_dates=["datetime"]).set_index("datetime").sort_index()
    df = df[["open","high","low","close","volume"]].dropna()
    df_fund = pd.read_csv(os.path.join(CACHE_DIR, "dogeusdt_funding.csv"),
                          parse_dates=["datetime"]).set_index("datetime").sort_index()
    df_fg = pd.read_csv(os.path.join(CACHE_DIR, "fear_greed.csv"),
                        parse_dates=["date"]).set_index("date").sort_index()

    h4 = df.resample("4h").agg(open=("open","first"), high=("high","max"),
                               low=("low","min"), close=("close","last"),
                               volume=("volume","sum")).dropna()
    h4["st"], h4["st_dir"] = calc_supertrend(h4, 10, 3.0)
    h4["chop"] = calc_choppiness(h4, 14)
    df["h4_st_dir"] = h4["st_dir"].reindex(df.index, method="ffill")
    df["h4_chop"]   = h4["chop"].reindex(df.index, method="ffill")

    c, h, l = df["close"], df["high"], df["low"]
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    tr1 = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr1.rolling(14).mean()
    df["atr_avg20"] = df["atr"].rolling(20).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss_ = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain/loss_.replace(0, np.nan)))
    ema_f = c.ewm(span=12, adjust=False).mean()
    ema_s = c.ewm(span=26, adjust=False).mean()
    df["macd_hist"] = (ema_f-ema_s) - (ema_f-ema_s).ewm(span=9, adjust=False).mean()
    up = h.diff(); dn = -l.diff()
    pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.0), index=df.index)
    atr14 = tr1.rolling(14).mean()
    pdi = 100 * pdm.rolling(14).mean() / atr14
    mdi = 100 * mdm.rolling(14).mean() / atr14
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    df["adx"] = dx.rolling(14).mean()

    df["_hour"] = df.index.hour; df["_date"] = df.index.date
    orb_hi, orb_lo = {}, {}
    for dt, grp in df.groupby("_date"):
        rng = grp[(grp["_hour"]>=0)&(grp["_hour"]<4)]
        if len(rng) >= 2:
            orb_hi[dt] = rng["high"].max(); orb_lo[dt] = rng["low"].min()
    df["orb_high"] = df["_date"].map(orb_hi)
    df["orb_low"]  = df["_date"].map(orb_lo)
    df["funding_rate"] = df_fund["funding_rate"].reindex(df.index, method="ffill")
    df["fg_value"] = pd.Series(df.index.date, index=df.index).map(df_fg["fg_value"].to_dict())
    df["fg_value"] = df["fg_value"].ffill()
    return df.dropna(subset=["h4_st_dir","h4_chop","adx","orb_high","funding_rate","fg_value"])


# ── Backtest parametrizado ────────────────────────────────────────────────────
def run(df, p):
    capital, peak = INITIAL_CAPITAL, INITIAL_CAPITAL
    trades, pos, daily_start = [], None, {}
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        dt, hour = df.index[i].date(), df.index[i].hour
        daily_start.setdefault(dt, capital)
        if pos:
            if hour >= 20:
                m = 1 if pos["type"]=="long" else -1
                pnl = (row["close"]-pos["entry"])*m*pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "pnl_usd":pnl, "capital":capital,
                               "exit_reason":"EOD", "exit_date":df.index[i]})
                pos = None; continue
            trail = (row["ema20"]-1.0*row["atr"] if pos["type"]=="long"
                     else row["ema20"]+1.0*row["atr"])
            if pos["type"]=="long" and trail>pos["sl"]: pos["sl"]=trail
            if pos["type"]=="short" and trail<pos["sl"]: pos["sl"]=trail
            sl_hit = ((pos["type"]=="long" and row["low"]<=pos["sl"]) or
                      (pos["type"]=="short" and row["high"]>=pos["sl"]))
            tp_hit = ((pos["type"]=="long" and row["high"]>=pos["tp"]) or
                      (pos["type"]=="short" and row["low"]<=pos["tp"]))
            if sl_hit or tp_hit:
                ep = pos["tp"] if tp_hit else pos["sl"]
                m = 1 if pos["type"]=="long" else -1
                pnl = (ep-pos["entry"])*m*pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "pnl_usd":pnl, "capital":capital,
                               "exit_reason":"TP" if tp_hit else "SL", "exit_date":df.index[i]})
                pos = None
            continue
        if peak>0 and (capital-peak)/peak <= -0.10: continue
        if (capital-daily_start[dt])/daily_start[dt] <= -0.05: continue
        if not (4 <= hour < 20): continue
        if pd.isna(row["orb_high"]): continue
        if (row["orb_high"]-row["orb_low"])/row["close"] < 0.003: continue
        if not pd.isna(row["atr_avg20"]) and row["atr"]>1.8*row["atr_avg20"]: continue
        chop = row["h4_chop"]
        if chop < 48:    regime, risk = "trend", p["risk_trend"]
        elif chop > 57:  regime, risk = "choppy", p["risk_choppy"]
        else:            regime, risk = "neutral", p["risk_neutral"]
        if regime == "choppy" and row["adx"] < p["adx_choppy"]: continue
        st_bull, st_bear = row["h4_st_dir"]==1, row["h4_st_dir"]==-1
        mom_up, mom_dn = row["ema20"]>row["ema50"], row["ema20"]<row["ema50"]
        adx_ok = row["adx"]>=p["adx_min"]
        orb_up = prev["close"]<=row["orb_high"] and row["close"]>row["orb_high"]
        orb_dn = prev["close"]>=row["orb_low"] and row["close"]<row["orb_low"]
        fr, fg = row["funding_rate"], row["fg_value"]
        long_sent = fr>=-0.0003 and fg>=35
        short_sent = -0.0004<=fr<=0.00005 and 10<=fg<=70
        sl_dist = 1.2*row["atr"]; tp_dist = sl_dist*2.2
        dd_pct = abs((capital-peak)/peak) if peak>0 else 0
        if dd_pct >= p["dd_hi"]: risk = min(risk, p["dd_hi_risk"])
        elif dd_pct >= p["dd_lo"]: risk = min(risk, p["dd_lo_risk"])
        lot = max(0.000001, (capital*risk)/sl_dist)
        if (st_bull and long_sent and orb_up and mom_up and row["macd_hist"]>0 and adx_ok
                and 35 <= row["rsi"] <= 75):
            pos = {"type":"long", "entry":row["close"], "sl":row["close"]-sl_dist,
                   "tp":row["close"]+tp_dist, "lot":lot, "entry_date":df.index[i]}
        elif (st_bear and short_sent and orb_dn and mom_dn and row["macd_hist"]<0 and adx_ok
                and 25 <= row["rsi"] <= 65):
            pos = {"type":"short", "entry":row["close"], "sl":row["close"]+sl_dist,
                   "tp":row["close"]-tp_dist, "lot":lot, "entry_date":df.index[i]}
    return pd.DataFrame(trades)


def metrics(t):
    if t.empty:
        return {"n":0,"wr":0,"pf":0,"ret":0,"dd":0,"ch":0,"ch_days":[]}
    wins = t[t["pnl_usd"]>0]; loss = t[t["pnl_usd"]<=0]
    n = len(t); wr = len(wins)/n*100
    pf = wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin = t["capital"].iloc[-1]; ret = (fin-INITIAL_CAPITAL)/INITIAL_CAPITAL*100
    eq = [INITIAL_CAPITAL]+t["capital"].tolist(); pk = eq[0]; dd = 0.0
    for v in eq:
        pk = max(pk, v)
        if pk>0: dd = min(dd, (v-pk)/pk*100)
    ch = 0; cap = INITIAL_CAPITAL; start = None; active = True; ch_days = []
    for r in t.itertuples():
        if not active:
            active = True; cap = r.capital; start = r.entry_date
        if r.capital >= cap*1.08:
            ch_days.append((pd.to_datetime(r.exit_date)-pd.to_datetime(start or r.entry_date)).days)
            ch += 1; active = False
        elif (r.capital-cap)/cap <= -0.10:
            active = False
    return {"n":n,"wr":wr,"pf":pf,"ret":ret,"dd":dd,"ch":ch,"ch_days":ch_days}


# ── Configuraciones a probar ─────────────────────────────────────────────────
CONFIGS = {
    "BASELINE v5b":        dict(risk_trend=0.018, risk_neutral=0.010, risk_choppy=0.005,
                                adx_min=22, adx_choppy=28, dd_lo=0.04, dd_lo_risk=0.008,
                                dd_hi=0.06, dd_hi_risk=0.005),
    "A: riesgo -33%":      dict(risk_trend=0.012, risk_neutral=0.007, risk_choppy=0.004,
                                adx_min=22, adx_choppy=28, dd_lo=0.04, dd_lo_risk=0.008,
                                dd_hi=0.06, dd_hi_risk=0.005),
    "B: riesgo -45%":      dict(risk_trend=0.010, risk_neutral=0.006, risk_choppy=0.003,
                                adx_min=22, adx_choppy=28, dd_lo=0.04, dd_lo_risk=0.006,
                                dd_hi=0.06, dd_hi_risk=0.004),
    "C: ADX +alto":        dict(risk_trend=0.018, risk_neutral=0.010, risk_choppy=0.005,
                                adx_min=26, adx_choppy=32, dd_lo=0.04, dd_lo_risk=0.008,
                                dd_hi=0.06, dd_hi_risk=0.005),
    "D: DD-guard agresivo":dict(risk_trend=0.014, risk_neutral=0.008, risk_choppy=0.004,
                                adx_min=22, adx_choppy=28, dd_lo=0.03, dd_lo_risk=0.006,
                                dd_hi=0.05, dd_hi_risk=0.003),
    "E: riesgo-33 + ADX26":dict(risk_trend=0.012, risk_neutral=0.007, risk_choppy=0.004,
                                adx_min=26, adx_choppy=30, dd_lo=0.04, dd_lo_risk=0.007,
                                dd_hi=0.055, dd_hi_risk=0.004),
}


if __name__ == "__main__":
    print("="*82)
    print("  OPTIMIZACIÓN DOGE | objetivo: DD <= -7% manteniendo challenges")
    print("="*82)
    df = prepare()
    df2y = df[(df.index>="2024-07-01")&(df.index<="2026-06-11")].copy()
    df26 = df[(df.index>="2026-01-01")&(df.index<="2026-06-11")].copy()

    print("\n  {:<22} {:>8} {:>8} {:>6} {:>7} {:>6} {:>6}   {:>8}".format(
        "CONFIG","RET 2Y","MAXDD","PF","TRADES","WR","CHALL","RET 2026"))
    print("  "+"-"*80)
    rows = []
    for name, p in CONFIGS.items():
        m = metrics(run(df2y, p))
        m26 = metrics(run(df26, p))
        rows.append((name, m, m26))
        flag = "  <-- DD OK" if abs(m["dd"]) <= 7.5 and m["ch"] >= 2 else ""
        print("  {:<22} {:>+7.1f}% {:>+7.1f}% {:>6.2f} {:>7} {:>5.0f}% {:>6} {:>+8.1f}%{}".format(
            name, m["ret"], m["dd"], m["pf"], m["n"], m["wr"], m["ch"], m26["ret"], flag))

    print("\n  DETALLE CHALLENGES (días para pasar cada +8%)")
    print("  "+"-"*80)
    for name, m, _ in rows:
        print(f"  {name:<22} {m['ch']} challenges | {m['ch_days']}")
    print("="*82)
