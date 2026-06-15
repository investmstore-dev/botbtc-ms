"""
BACKTEST MULTI-PAR | Estrategia v5b sobre varios símbolos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Corre la MISMA estrategia v5b (ORB + Supertrend H4 + Choppiness + Sentimiento)
sobre BTCUSDT, ETHUSDT, BNBUSDT, DOGEUSDT y compara resultados.

La lógica es scale-invariant: el sizing = capital*riesgo/dist_SL, así que
funciona igual sin importar el precio del activo.

El Fear & Greed Index es macro (mismo para todo el mercado cripto).
El funding rate se descarga por par.

Uso:  python model/backtest_multipair.py
Los CSV se cachean en data_backtest/ para no re-descargar.
"""
import os
import time
import warnings
from datetime import datetime, timezone

import requests
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Config ──────────────────────────────────────────────────────────────────
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOGEUSDT"]

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data_backtest")
os.makedirs(CACHE_DIR, exist_ok=True)

START_DT = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DT   = datetime(2026, 6, 11, tzinfo=timezone.utc)

# ── Parámetros estrategia v5b (idénticos a producción) ──────────────────────
INITIAL_CAPITAL = 10_000
RISK_TREND, RISK_NEUTRAL, RISK_CHOPPY = 0.018, 0.010, 0.005
CHOP_TREND_MAX, CHOP_CHOPPY_MIN, CHOP_PERIOD = 48, 57, 14
EMA_FAST, EMA_SLOW = 20, 50
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_PERIOD, ATR_PERIOD, ADX_PERIOD = 14, 14, 14
ADX_MIN = 22
RSI_LONG_MIN, RSI_LONG_MAX = 35, 75
RSI_SHORT_MIN, RSI_SHORT_MAX = 25, 65
ORB_HOUR_START, ORB_HOUR_END, ORB_HOUR_CLOSE = 0, 4, 20
ORB_MIN_RANGE_PCT = 0.003
ATR_SL_MULT, TP_RR, ATR_TRAIL_MULT, ATR_VOL_MULT = 1.2, 2.2, 1.0, 1.8
CFT_MAX_DD, CFT_DAILY_DD = 0.10, 0.05
ST_PERIOD, ST_MULT = 10, 3.0
FUND_LONG_MIN = -0.0003
FUND_SHORT_MAX, FUND_SHORT_MIN = 0.00005, -0.0004
FG_LONG_MIN, FG_SHORT_MIN, FG_SHORT_MAX = 35, 10, 70


# ── Descarga ─────────────────────────────────────────────────────────────────
def _download_klines(symbol):
    out = os.path.join(CACHE_DIR, f"{symbol.lower()}_h1.csv")
    if os.path.exists(out):
        return out
    print(f"  Descargando velas H1 de {symbol}...")
    start_ms, end_ms = int(START_DT.timestamp()*1000), int(END_DT.timestamp()*1000)
    rows, cur = [], end_ms
    while cur > start_ms:
        try:
            r = requests.get("https://api.bybit.com/v5/market/kline", params={
                "category": "linear", "symbol": symbol, "interval": "60",
                "end": cur, "limit": 1000}, timeout=15)
            data = r.json()
        except requests.RequestException:
            time.sleep(5); continue
        if data.get("retCode") != 0:
            print(f"    Error API {symbol}: {data.get('retMsg')}"); break
        batch = data["result"].get("list", [])
        if not batch:
            break
        for x in batch:
            ts = int(x[0])
            if ts < start_ms:
                continue
            rows.append({"datetime": datetime.fromtimestamp(ts/1000, tz=timezone.utc),
                         "open": float(x[1]), "high": float(x[2]), "low": float(x[3]),
                         "close": float(x[4]), "volume": float(x[5])})
        cur = int(batch[-1][0]) - 1
        time.sleep(0.12)
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True).dt.tz_localize(None)
    df.sort_values("datetime", inplace=True)
    df.drop_duplicates(subset="datetime", inplace=True)
    df.set_index("datetime", inplace=True)
    df.to_csv(out)
    print(f"    {len(df):,} velas guardadas en {os.path.basename(out)}")
    return out


def _download_funding(symbol):
    out = os.path.join(CACHE_DIR, f"{symbol.lower()}_funding.csv")
    if os.path.exists(out):
        return out
    print(f"  Descargando funding rate de {symbol}...")
    start_ms, end_ms = int(START_DT.timestamp()*1000), int(END_DT.timestamp()*1000)
    rows, cur = [], end_ms
    while cur > start_ms:
        try:
            r = requests.get("https://api.bybit.com/v5/market/funding/history", params={
                "category": "linear", "symbol": symbol, "endTime": cur, "limit": 200},
                timeout=15)
            data = r.json()
        except requests.RequestException:
            time.sleep(5); continue
        if data.get("retCode") != 0:
            break
        batch = data["result"].get("list", [])
        if not batch:
            break
        for x in batch:
            ts = int(x["fundingRateTimestamp"])
            if ts < start_ms:
                continue
            rows.append({"datetime": datetime.fromtimestamp(ts/1000, tz=timezone.utc).replace(tzinfo=None),
                         "funding_rate": float(x["fundingRate"])})
        oldest = int(batch[-1]["fundingRateTimestamp"])
        if oldest <= start_ms:
            break
        cur = oldest - 1
        time.sleep(0.15)
    df = pd.DataFrame(rows)
    df.sort_values("datetime", inplace=True)
    df.drop_duplicates(subset="datetime", inplace=True)
    df.set_index("datetime", inplace=True)
    df.to_csv(out)
    print(f"    {len(df):,} entradas funding guardadas")
    return out


def _download_fg():
    out = os.path.join(CACHE_DIR, "fear_greed.csv")
    if os.path.exists(out):
        return out
    print("  Descargando Fear & Greed Index (macro)...")
    r = requests.get("https://api.alternative.me/fng/?limit=2000&format=json", timeout=20)
    rows = [{"date": datetime.fromtimestamp(int(d["timestamp"])).date(),
             "fg_value": int(d["value"])} for d in r.json()["data"]]
    df = pd.DataFrame(rows)
    df.sort_values("date", inplace=True)
    df.drop_duplicates(subset="date", inplace=True)
    df.set_index("date", inplace=True)
    df.to_csv(out)
    return out


# ── Indicadores ──────────────────────────────────────────────────────────────
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
        if pd.isna(prev):               di.iloc[i] = 1
        elif prev == fu.iloc[i-1]:      di.iloc[i] = 1 if c > fu.iloc[i] else -1
        else:                           di.iloc[i] = -1 if c < fl.iloc[i] else 1
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


def prepare(symbol):
    df = pd.read_csv(_download_klines(symbol), parse_dates=["datetime"]).set_index("datetime").sort_index()
    df = df[["open","high","low","close","volume"]].dropna()
    df_fund = pd.read_csv(_download_funding(symbol), parse_dates=["datetime"]).set_index("datetime").sort_index()
    df_fg = pd.read_csv(_download_fg(), parse_dates=["date"]).set_index("date").sort_index()

    h4 = df.resample("4h").agg(open=("open","first"), high=("high","max"),
                               low=("low","min"), close=("close","last"),
                               volume=("volume","sum")).dropna()
    h4["st"], h4["st_dir"] = calc_supertrend(h4, ST_PERIOD, ST_MULT)
    h4["chop"] = calc_choppiness(h4, CHOP_PERIOD)
    df["h4_st_dir"] = h4["st_dir"].reindex(df.index, method="ffill")
    df["h4_chop"]   = h4["chop"].reindex(df.index, method="ffill")

    c, h, l = df["close"], df["high"], df["low"]
    df["ema20"] = c.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema50"] = c.ewm(span=EMA_SLOW, adjust=False).mean()
    tr1 = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr1.rolling(ATR_PERIOD).mean()
    df["atr_avg20"] = df["atr"].rolling(20).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss_ = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    df["rsi"] = 100 - (100 / (1 + gain/loss_.replace(0, np.nan)))
    ema_f = c.ewm(span=MACD_FAST, adjust=False).mean()
    ema_s = c.ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd"] = ema_f - ema_s
    df["macd_sig"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]
    up = h.diff(); dn = -l.diff()
    pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.0), index=df.index)
    atr14 = tr1.rolling(ADX_PERIOD).mean()
    pdi = 100 * pdm.rolling(ADX_PERIOD).mean() / atr14
    mdi = 100 * mdm.rolling(ADX_PERIOD).mean() / atr14
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    df["adx"] = dx.rolling(ADX_PERIOD).mean()

    df["_hour"] = df.index.hour; df["_date"] = df.index.date
    orb_hi, orb_lo = {}, {}
    for dt, grp in df.groupby("_date"):
        rng = grp[(grp["_hour"]>=ORB_HOUR_START)&(grp["_hour"]<ORB_HOUR_END)]
        if len(rng) >= 2:
            orb_hi[dt] = rng["high"].max(); orb_lo[dt] = rng["low"].min()
    df["orb_high"] = df["_date"].map(orb_hi)
    df["orb_low"]  = df["_date"].map(orb_lo)

    df["funding_rate"] = df_fund["funding_rate"].reindex(df.index, method="ffill")
    df["fg_value"] = pd.Series(df.index.date, index=df.index).map(df_fg["fg_value"].to_dict())
    df["fg_value"] = df["fg_value"].ffill()
    return df.dropna(subset=["h4_st_dir","h4_chop","adx","orb_high","funding_rate","fg_value"])


# ── Simulación (idéntica a v5b) ──────────────────────────────────────────────
def run_backtest(df):
    capital, peak = INITIAL_CAPITAL, INITIAL_CAPITAL
    trades, pos, daily_start = [], None, {}
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        dt, hour = df.index[i].date(), df.index[i].hour
        daily_start.setdefault(dt, capital)
        if pos:
            if hour >= ORB_HOUR_CLOSE:
                m = 1 if pos["type"]=="long" else -1
                pnl = (row["close"]-pos["entry"])*m*pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "exit":row["close"], "pnl_usd":pnl,
                               "capital":capital, "exit_reason":"EOD", "exit_date":df.index[i]})
                pos = None; continue
            trail = (row["ema20"]-ATR_TRAIL_MULT*row["atr"] if pos["type"]=="long"
                     else row["ema20"]+ATR_TRAIL_MULT*row["atr"])
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
                trades.append({**pos, "exit":ep, "pnl_usd":pnl, "capital":capital,
                               "exit_reason":"TP" if tp_hit else "SL", "exit_date":df.index[i]})
                pos = None
            continue
        if peak>0 and (capital-peak)/peak <= -CFT_MAX_DD: continue
        if (capital-daily_start[dt])/daily_start[dt] <= -CFT_DAILY_DD: continue
        if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE): continue
        if pd.isna(row["orb_high"]): continue
        if (row["orb_high"]-row["orb_low"])/row["close"] < ORB_MIN_RANGE_PCT: continue
        if not pd.isna(row["atr_avg20"]) and row["atr"]>ATR_VOL_MULT*row["atr_avg20"]: continue
        chop = row["h4_chop"]
        if chop < CHOP_TREND_MAX:    regime, risk = "trend", RISK_TREND
        elif chop > CHOP_CHOPPY_MIN: regime, risk = "choppy", RISK_CHOPPY
        else:                        regime, risk = "neutral", RISK_NEUTRAL
        if regime == "choppy" and row["adx"] < 28: continue
        st_bull, st_bear = row["h4_st_dir"]==1, row["h4_st_dir"]==-1
        mom_up, mom_dn = row["ema20"]>row["ema50"], row["ema20"]<row["ema50"]
        macd_bull, macd_bear = row["macd_hist"]>0, row["macd_hist"]<0
        adx_ok = row["adx"]>=ADX_MIN
        orb_up = prev["close"]<=row["orb_high"] and row["close"]>row["orb_high"]
        orb_dn = prev["close"]>=row["orb_low"] and row["close"]<row["orb_low"]
        fr, fg = row["funding_rate"], row["fg_value"]
        long_sent = fr>=FUND_LONG_MIN and fg>=FG_LONG_MIN
        short_sent = FUND_SHORT_MIN<=fr<=FUND_SHORT_MAX and FG_SHORT_MIN<=fg<=FG_SHORT_MAX
        sl_dist = ATR_SL_MULT*row["atr"]; tp_dist = sl_dist*TP_RR
        dd_pct = abs((capital-peak)/peak) if peak>0 else 0
        if dd_pct >= 0.06: risk = min(risk, 0.005)
        elif dd_pct >= 0.04: risk = min(risk, 0.008)
        lot = max(0.000001, (capital*risk)/sl_dist)
        if (st_bull and long_sent and orb_up and mom_up and macd_bull and adx_ok
                and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
            pos = {"type":"long", "entry":row["close"], "sl":row["close"]-sl_dist,
                   "tp":row["close"]+tp_dist, "lot":lot, "entry_date":df.index[i], "regime":regime}
        elif (st_bear and short_sent and orb_dn and mom_dn and macd_bear and adx_ok
                and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
            pos = {"type":"short", "entry":row["close"], "sl":row["close"]+sl_dist,
                   "tp":row["close"]-tp_dist, "lot":lot, "entry_date":df.index[i], "regime":regime}
    return pd.DataFrame(trades)


def metrics(t):
    if t.empty:
        return None
    wins = t[t["pnl_usd"]>0]; loss = t[t["pnl_usd"]<=0]
    n = len(t); wr = len(wins)/n*100
    pf = wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin = t["capital"].iloc[-1]; ret = (fin-INITIAL_CAPITAL)/INITIAL_CAPITAL*100
    eq = [INITIAL_CAPITAL]+t["capital"].tolist(); pk = eq[0]; dd = 0.0
    for v in eq:
        pk = max(pk, v)
        if pk>0: dd = min(dd, (v-pk)/pk*100)
    days = t["entry_date"].dt.date.nunique()
    sh = t[t["type"]=="short"]
    spf = (sh[sh["pnl_usd"]>0]["pnl_usd"].sum() /
           abs(sh[sh["pnl_usd"]<=0]["pnl_usd"].sum())) if len(sh[sh["pnl_usd"]<=0]) else 999
    # challenges
    ch = 0; cap = INITIAL_CAPITAL; start = None; active = True
    ch_days = []
    for r in t.itertuples():
        if not active:
            active = True; cap = r.capital; start = r.entry_date
        if r.capital >= cap*1.08:
            ch_days.append((pd.to_datetime(r.exit_date)-pd.to_datetime(start or r.entry_date)).days)
            ch += 1; active = False
        elif (r.capital-cap)/cap <= -0.10:
            active = False
    return {"n":n, "wr":wr, "pf":pf, "ret":ret, "dd":dd, "days":days,
            "spf":spf, "shorts":len(sh), "ch":ch, "ch_days":ch_days}


# ── EJECUTAR ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*78)
    print("  BACKTEST MULTI-PAR | Estrategia v5b (Jul 2024 - Jun 2026)")
    print("="*78)
    results = {}
    for sym in SYMBOLS:
        print(f"\n[{sym}] Preparando datos...")
        df = prepare(sym)
        df2y = df[(df.index>="2024-07-01")&(df.index<="2026-06-11")].copy()
        df26 = df[(df.index>="2026-01-01")&(df.index<="2026-06-11")].copy()
        results[sym] = {"2y": metrics(run_backtest(df2y)),
                        "2026": metrics(run_backtest(df26)),
                        "chop2y": df2y["h4_chop"].mean()}
        print(f"  Listo ({len(df2y):,} velas)")

    # Tabla comparativa 2 años
    print("\n" + "="*78)
    print("  RESULTADOS 2 AÑOS (Jul 2024 - Jun 2026)")
    print("="*78)
    print("  {:<9} {:>7} {:>7} {:>6} {:>8} {:>7} {:>6} {:>7} {:>6}".format(
        "PAR","RETORNO","MAXDD","PF","TRADES","WR","SHORTPF","CHALL","CHOP"))
    print("  "+"-"*74)
    for sym in SYMBOLS:
        m = results[sym]["2y"]
        if not m:
            print(f"  {sym:<9}  sin trades"); continue
        print("  {:<9} {:>+6.1f}% {:>+5.1f}% {:>6.2f} {:>8} {:>5.0f}% {:>7.2f} {:>4}  {:>6.0f}".format(
            sym, m["ret"], m["dd"], m["pf"], m["n"], m["wr"], m["spf"], m["ch"], results[sym]["chop2y"]))

    # Tabla 2026
    print("\n  RESULTADOS 2026 (Ene-Jun, mercado choppy)")
    print("  "+"-"*74)
    print("  {:<9} {:>7} {:>7} {:>6} {:>8} {:>7}".format("PAR","RETORNO","MAXDD","PF","TRADES","WR"))
    print("  "+"-"*74)
    for sym in SYMBOLS:
        m = results[sym]["2026"]
        if not m:
            print(f"  {sym:<9}  sin trades"); continue
        print("  {:<9} {:>+6.1f}% {:>+5.1f}% {:>6.2f} {:>8} {:>5.0f}%".format(
            sym, m["ret"], m["dd"], m["pf"], m["n"], m["wr"]))

    # Detalle challenges
    print("\n  CHALLENGES CFT PASADOS (2 años, +8% cada uno, sin violar -10% DD)")
    print("  "+"-"*74)
    for sym in SYMBOLS:
        m = results[sym]["2y"]
        if m:
            print(f"  {sym:<9} {m['ch']} challenges | días c/u: {m['ch_days']}")
    print("="*78)
