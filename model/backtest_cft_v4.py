"""
BACKTEST CFT v4 | Supertrend H4 como filtro de tendencia principal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAMBIO CLAVE vs versiones anteriores:
  Reemplaza el stack de EMAs (EMA50/200/500 + pendiente) por UN SOLO indicador:
  Supertrend en H4 (periodo 10, multiplicador 3.0)
    -> H4 ST VERDE  = tendencia ALCISTA  -> solo LONGS
    -> H4 ST ROJO   = tendencia BAJISTA  -> solo SHORTS

  Filtros de sentimiento (funding + F&G) como confirmacion adicional.
  En H1 se mantiene: ORB breakout + MACD + ADX + RSI + ATR vol filter

  Objetivo: 0 operaciones contra tendencia

Tests:
  A) 2 anos completos: Jul 2024 - Jun 2026
  B) 2026 solo:        Ene 2026 - Jun 2026

Uso: python backtest_cft_v4.py
"""
import pandas as pd
import numpy as np
import os, warnings
warnings.filterwarnings("ignore")

# ── Parametros ────────────────────────────────────────────────────────────────
INITIAL_CAPITAL   = 10_000
RISK_PCT          = 0.015      # volvemos a 1.5% — mejor tendencia = mas confianza

EMA_FAST, EMA_SLOW = 20, 50    # solo para momentum H1 (EMA20 vs EMA50)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_PERIOD, ATR_PERIOD, ADX_PERIOD = 14, 14, 14

ADX_MIN            = 22        # ligeramente mas permisivo (ST ya filtra tendencia)
RSI_LONG_MIN,  RSI_LONG_MAX  = 35, 75
RSI_SHORT_MIN, RSI_SHORT_MAX = 25, 65

ORB_HOUR_START = 0
ORB_HOUR_END   = 4
ORB_HOUR_CLOSE = 20
ORB_MIN_RANGE_PCT = 0.003

ATR_SL_MULT    = 1.2
TP_RR          = 2.2
ATR_TRAIL_MULT = 1.0
ATR_VOL_MULT   = 1.8

CFT_MAX_DD   = 0.10
CFT_DAILY_DD = 0.05

# ── Supertrend H4 ─────────────────────────────────────────────────────────────
ST_PERIOD = 10
ST_MULT   = 3.0

# ── Filtros sentimiento (shorts) ──────────────────────────────────────────────
FUND_LONG_MIN   = -0.0003   # no long si funding < -0.03%
FG_LONG_MIN     = 35        # no long si F&G < 35
FUND_SHORT_MAX  =  0.00005  # no short si funding > ~0 (mercado long-biased)
FUND_SHORT_MIN  = -0.0004   # no short si funding < -0.04% (squeeze risk)
FG_SHORT_MIN    = 10
FG_SHORT_MAX    = 70

CSV_PRICE   = "btcusdt_h1_bybit.csv"
CSV_FUNDING = "btcusdt_funding_rate.csv"
CSV_FG      = "fear_greed_index.csv"

# ── Carga de datos ────────────────────────────────────────────────────────────
for f in [CSV_PRICE, CSV_FUNDING, CSV_FG]:
    if not os.path.exists(f):
        print(f"Falta archivo: {f}"); exit(1)

df_raw = pd.read_csv(CSV_PRICE, parse_dates=["datetime"])
df_raw.set_index("datetime", inplace=True)
df_raw.sort_index(inplace=True)
if df_raw.index.tz is not None:
    df_raw.index = df_raw.index.tz_localize(None)
df_raw = df_raw[["open","high","low","close","volume"]].dropna()

df_fund = pd.read_csv(CSV_FUNDING, parse_dates=["datetime"])
df_fund.set_index("datetime", inplace=True); df_fund.sort_index(inplace=True)

df_fg = pd.read_csv(CSV_FG, parse_dates=["date"])
df_fg.set_index("date", inplace=True); df_fg.sort_index(inplace=True)

# ── Supertrend en H4 (resample desde H1) ──────────────────────────────────────
df_h4 = df_raw.resample("4h").agg(
    open=("open","first"), high=("high","max"),
    low=("low","min"),  close=("close","last"), volume=("volume","sum")
).dropna()

def calc_supertrend(df, period=10, mult=3.0):
    hl2 = (df["high"] + df["low"]) / 2
    tr  = pd.concat([(df["high"]-df["low"]),
                     (df["high"]-df["close"].shift()).abs(),
                     (df["low"] -df["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    bu = hl2 + mult * atr   # basic upper
    bl = hl2 - mult * atr   # basic lower

    fu = bu.copy()   # final upper
    fl = bl.copy()   # final lower
    st = pd.Series(np.nan, index=df.index)
    di = pd.Series(0,   index=df.index, dtype=int)   # 1=up, -1=down

    for i in range(1, len(df)):
        # Final upper: solo baja, nunca sube durante tendencia bajista
        fu.iloc[i] = bu.iloc[i] if bu.iloc[i] < fu.iloc[i-1] or df["close"].iloc[i-1] > fu.iloc[i-1] else fu.iloc[i-1]
        # Final lower: solo sube, nunca baja durante tendencia alcista
        fl.iloc[i] = bl.iloc[i] if bl.iloc[i] > fl.iloc[i-1] or df["close"].iloc[i-1] < fl.iloc[i-1] else fl.iloc[i-1]

        prev_st = st.iloc[i-1]
        c = df["close"].iloc[i]
        if pd.isna(prev_st):
            di.iloc[i] = 1
        elif prev_st == fu.iloc[i-1]:           # estabamos en bajista
            di.iloc[i] = 1  if c > fu.iloc[i] else -1
        else:                                    # estabamos en alcista
            di.iloc[i] = -1 if c < fl.iloc[i] else  1

        st.iloc[i] = fl.iloc[i] if di.iloc[i] == 1 else fu.iloc[i]

    return st, di

print("Calculando Supertrend H4...")
df_h4["st"], df_h4["st_dir"] = calc_supertrend(df_h4, ST_PERIOD, ST_MULT)

# Mapear H4 Supertrend de vuelta a H1 (forward-fill)
st_dir_h1 = df_h4["st_dir"].reindex(df_raw.index, method="ffill")
st_val_h1 = df_h4["st"].reindex(df_raw.index, method="ffill")
df_raw["h4_st_dir"] = st_dir_h1
df_raw["h4_st"]     = st_val_h1

# ── Indicadores H1 ────────────────────────────────────────────────────────────
c, h, l = df_raw["close"], df_raw["high"], df_raw["low"]

df_raw["ema20"] = c.ewm(span=EMA_FAST, adjust=False).mean()
df_raw["ema50"] = c.ewm(span=EMA_SLOW, adjust=False).mean()

tr1 = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
df_raw["atr"]      = tr1.rolling(ATR_PERIOD).mean()
df_raw["atr_avg20"]= df_raw["atr"].rolling(20).mean()

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
atr14 = tr1.rolling(ADX_PERIOD).mean()
pdi   = 100 * pdm.rolling(ADX_PERIOD).mean() / atr14
mdi   = 100 * mdm.rolling(ADX_PERIOD).mean() / atr14
dx    = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
df_raw["adx"] = dx.rolling(ADX_PERIOD).mean()

# ── ORB por dia ───────────────────────────────────────────────────────────────
df_raw["_hour"] = df_raw.index.hour
df_raw["_date"] = df_raw.index.date
orb_hi, orb_lo = {}, {}
for dt, grp in df_raw.groupby("_date"):
    rng = grp[(grp["_hour"]>=ORB_HOUR_START)&(grp["_hour"]<ORB_HOUR_END)]
    if len(rng) >= 2:
        orb_hi[dt] = rng["high"].max()
        orb_lo[dt] = rng["low"].min()
df_raw["orb_high"] = df_raw["_date"].map(orb_hi)
df_raw["orb_low"]  = df_raw["_date"].map(orb_lo)

# ── Sentimiento ───────────────────────────────────────────────────────────────
df_raw["funding_rate"] = df_fund["funding_rate"].reindex(df_raw.index, method="ffill")
df_raw["fg_value"]     = pd.Series(df_raw.index.date, index=df_raw.index).map(df_fg["fg_value"].to_dict())
df_raw["fg_value"]     = df_raw["fg_value"].ffill()

df_all = df_raw.dropna(subset=["h4_st_dir","adx","orb_high","funding_rate","fg_value"])
print(f"Velas totales listas: {len(df_all):,}")


# ── Simulacion ────────────────────────────────────────────────────────────────
def run_backtest(df):
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
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "exit": row["close"], "pnl_usd": round(pnl,2),
                               "capital": round(capital,2), "exit_reason": "EOD",
                               "exit_date": df.index[i]})
                pos = None; continue

            trail = (row["ema20"] - ATR_TRAIL_MULT*row["atr"]
                     if pos["type"]=="long" else row["ema20"]+ATR_TRAIL_MULT*row["atr"])
            if pos["type"]=="long"  and trail>pos["sl"]: pos["sl"]=trail
            if pos["type"]=="short" and trail<pos["sl"]: pos["sl"]=trail

            sl_hit = ((pos["type"]=="long"  and row["low"] <=pos["sl"]) or
                      (pos["type"]=="short" and row["high"]>=pos["sl"]))
            tp_hit = ((pos["type"]=="long"  and row["high"]>=pos["tp"]) or
                      (pos["type"]=="short" and row["low"] <=pos["tp"]))

            if sl_hit or tp_hit:
                ep = pos["tp"] if tp_hit else pos["sl"]
                mult = 1 if pos["type"]=="long" else -1
                pnl  = (ep - pos["entry"]) * mult * pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "exit": ep, "pnl_usd": round(pnl,2),
                               "capital": round(capital,2),
                               "exit_reason": "TP" if tp_hit else "SL",
                               "exit_date": df.index[i]})
                pos = None
            continue

        # Guardas CFT
        if peak>0 and (capital-peak)/peak <= -CFT_MAX_DD: continue
        if (capital-daily_start[dt])/daily_start[dt] <= -CFT_DAILY_DD: continue
        if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE): continue
        if pd.isna(row["orb_high"]) or pd.isna(row["orb_low"]): continue
        orb_range = row["orb_high"] - row["orb_low"]
        if orb_range/row["close"] < ORB_MIN_RANGE_PCT: continue
        if not pd.isna(row["atr_avg20"]) and row["atr"] > ATR_VOL_MULT*row["atr_avg20"]: continue

        # ── SUPERTREND H4: filtro de tendencia principal ──────────────────────
        st_bull = row["h4_st_dir"] == 1    # H4 en ALCISTA -> solo longs
        st_bear = row["h4_st_dir"] == -1   # H4 en BAJISTA -> solo shorts

        # ── Confirmacion H1 momentum ──────────────────────────────────────────
        mom_up   = row["ema20"] > row["ema50"]
        mom_dn   = row["ema20"] < row["ema50"]
        macd_bull= row["macd_hist"] > 0
        macd_bear= row["macd_hist"] < 0
        adx_ok   = row["adx"] >= ADX_MIN

        # ── ORB breakout H1 ───────────────────────────────────────────────────
        orb_up = prev["close"] <= row["orb_high"] and row["close"] > row["orb_high"]
        orb_dn = prev["close"] >= row["orb_low"]  and row["close"] < row["orb_low"]

        # ── Filtros sentimiento ───────────────────────────────────────────────
        fr = row["funding_rate"]
        fg = row["fg_value"]
        long_ok_sent  = fr >= FUND_LONG_MIN   and fg >= FG_LONG_MIN
        short_ok_sent = FUND_SHORT_MIN <= fr <= FUND_SHORT_MAX and FG_SHORT_MIN <= fg <= FG_SHORT_MAX

        # ── Sizing dinamico ───────────────────────────────────────────────────
        sl_dist = ATR_SL_MULT * row["atr"]
        tp_dist = sl_dist * TP_RR
        dd_pct  = abs((capital-peak)/peak) if peak>0 else 0
        if   dd_pct >= 0.06: risk_now = 0.005
        elif dd_pct >= 0.04: risk_now = 0.008
        else:                risk_now = RISK_PCT
        lot = max(0.001, round((capital*risk_now)/sl_dist, 4))

        # ── LONG: H4 alcista + H1 momentum alcista + ORB + sentimiento ───────
        if (st_bull and long_ok_sent and orb_up and mom_up
                and macd_bull and adx_ok
                and RSI_LONG_MIN <= row["rsi"] <= RSI_LONG_MAX):
            pos = {"type":"long",  "entry":row["close"],
                   "sl":row["close"]-sl_dist, "tp":row["close"]+tp_dist,
                   "lot":lot, "entry_date":df.index[i],
                   "h4_dir":int(row["h4_st_dir"]),
                   "funding":float(fr), "fg":float(fg)}

        # ── SHORT: H4 bajista + H1 momentum bajista + ORB + sentimiento ──────
        elif (st_bear and short_ok_sent and orb_dn and mom_dn
                and macd_bear and adx_ok
                and RSI_SHORT_MIN <= row["rsi"] <= RSI_SHORT_MAX):
            pos = {"type":"short", "entry":row["close"],
                   "sl":row["close"]+sl_dist, "tp":row["close"]-tp_dist,
                   "lot":lot, "entry_date":df.index[i],
                   "h4_dir":int(row["h4_st_dir"]),
                   "funding":float(fr), "fg":float(fg)}

    return pd.DataFrame(trades)


def print_report(df_t, label, start, end, show_trades=True):
    W = 70; SEP="="*W; S2="-"*W
    if df_t.empty:
        print(f"\n  {label}: Sin trades.\n"); return {}

    wins=df_t[df_t["pnl_usd"]>0]; loss=df_t[df_t["pnl_usd"]<=0]
    tps =df_t[df_t["exit_reason"]=="TP"]; sls=df_t[df_t["exit_reason"]=="SL"]
    eods=df_t[df_t["exit_reason"]=="EOD"]
    n=len(df_t); wr=len(wins)/n*100
    aw=wins["pnl_usd"].mean() if len(wins) else 0
    al=loss["pnl_usd"].mean() if len(loss) else 0
    pf=wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin=df_t["capital"].iloc[-1]; ret=(fin-INITIAL_CAPITAL)/INITIAL_CAPITAL*100
    gpr=abs(aw/al) if al else 0
    eq=[INITIAL_CAPITAL]+df_t["capital"].tolist(); pk=eq[0]; dd_max=0.0
    for v in eq:
        pk=max(pk,v)
        if pk>0: dd_max=min(dd_max,(v-pk)/pk*100)
    streak=ms=0
    for p in df_t["pnl_usd"]:
        if p<=0: streak+=1; ms=max(ms,streak)
        else: streak=0
    td=df_t["entry_date"].dt.date.nunique()
    lo=df_t[df_t["type"]=="long"]; sh=df_t[df_t["type"]=="short"]
    sw=sh[sh["pnl_usd"]>0]; sl_=sh[sh["pnl_usd"]<=0]
    swr=len(sw)/len(sh)*100 if len(sh) else 0
    spf=sw["pnl_usd"].sum()/abs(sl_["pnl_usd"].sum()) if len(sl_) and sl_["pnl_usd"].sum()!=0 else 999
    lw=lo[lo["pnl_usd"]>0]; ll=lo[lo["pnl_usd"]<=0]
    lwr=len(lw)/len(lo)*100 if len(lo) else 0
    lpf=lw["pnl_usd"].sum()/abs(ll["pnl_usd"].sum()) if len(ll) and ll["pnl_usd"].sum()!=0 else 999

    print(); print(SEP)
    print(f"  {label}")
    print(f"  Periodo: {start} a {end}")
    print(SEP)
    print("  {:<36} {:>14}   {:>8}".format("METRICA","RESULTADO","CFT REF"))
    print(S2)
    print("  {:<36} {:>14}".format("Trades totales", n))
    print("  {:<36} {:>14}".format(f"  LONGS  WR {lwr:.0f}% / PF {lpf:.2f}", f"{len(lo)} ({len(lo)/n*100:.0f}%)"))
    print("  {:<36} {:>14}".format(f"  SHORTS WR {swr:.0f}% / PF {spf:.2f}", f"{len(sh)} ({len(sh)/n*100:.0f}%)"))
    print("  {:<36} {:>14}   {:>8}".format("Dias operados", td, ">= 5"))
    print("  {:<36} {:>14}".format("Ganadores", f"{len(wins)} ({wr:.1f}%)"))
    print("  {:<36} {:>14}".format("  Por TP / SL / EOD", f"{len(tps)} / {len(sls)} / {len(eods)}"))
    print("  {:<36} {:>14}".format("Promedio ganancia / perdida", f"${aw:,.0f} / ${al:,.0f}"))
    print("  {:<36} {:>14}   {:>8}".format("Ratio G/P", f"{gpr:.2f}x", ">1.5x"))
    print("  {:<36} {:>14}   {:>8}".format("Profit Factor", f"{pf:.2f}", ">1.2"))
    print("  {:<36} {:>14}".format("Capital final", f"${fin:,.0f}"))
    print("  {:<36} {:>14}   {:>8}".format("Retorno total", f"{ret:+.1f}%", "+8%"))
    print("  {:<36} {:>14}   {:>8}".format("Drawdown maximo", f"{dd_max:+.1f}%", ">-10%"))
    print("  {:<36} {:>14}   {:>8}".format("Racha max perdidas", f"{ms} trades", "< 8"))
    print(S2)
    p1=fin>=INITIAL_CAPITAL*1.08; dok=abs(dd_max)<10; daysok=td>=5
    print()
    print("  CFT PHASE 1  (+8% / max -10% DD / min 5 dias)")
    print(S2)
    print(f"  {'[OK]' if p1    else '[XX]'}  Profit +8%             {ret:+.1f}%")
    print(f"  {'[OK]' if dok   else '[XX]'}  Max DD < 10%           {dd_max:+.1f}%")
    print(f"  {'[OK]' if daysok else '[XX]'} Min 5 dias             {td} dias")
    if p1 and dok and daysok:
        print(f"\n  *** CFT PHASE 1 PASADA ***")
    else:
        falta=INITIAL_CAPITAL*1.08-fin
        if falta>0: print(f"\n  Falta: ${falta:,.0f}  ({ret:+.1f}% de 8%)")
    print(SEP)

    if show_trades:
        print()
        print("  HISTORIAL (H4-ST=tendencia | Fund=funding rate | F&G=fear&greed)")
        print(S2)
        print("  {:<16} {:<16} {:5} {:>10} {:>10} {:>4} {:>9} {:>10}  H4 {:>5} {:>4}".format(
            "Entrada","Salida","Tipo","BTC Entry","BTC Exit","Sal","P&L","Capital","Fund","F&G"))
        print("  "+"-"*104)
        for _,t in df_t.iterrows():
            flag=" WIN" if t["pnl_usd"]>0 else "    "
            h4s = "UP " if t.get("h4_dir",0)==1 else "DN "
            frs = f"{t.get('funding',0)*10000:+.1f}bp"
            fgs = f"{int(t.get('fg',50)):3d}"
            print("  {:<16} {:<16} {:5} {:>10,.0f} {:>10,.0f} {:>4} ${:>+8,.0f} ${:>9,.0f}  {} {:>5} {:>4}{}".format(
                str(t["entry_date"])[:16], str(t["exit_date"])[:16],
                t["type"][0].upper(), t["entry"], t["exit"],
                t.get("exit_reason","?"), t["pnl_usd"], t["capital"],
                h4s, frs, fgs, flag))
        print()

    return {"n":n,"wr":wr,"pf":pf,"ret":ret,"dd":dd_max,"fin":fin,
            "longs":len(lo),"shorts":len(sh),"ms":ms,"swr":swr,"spf":spf,"lwr":lwr,"lpf":lpf}


# ── EJECUTAR ──────────────────────────────────────────────────────────────────
W=70; SEP="="*W
print(); print(SEP)
print("  BACKTEST CFT v4 | Supertrend H4 + ORB H1 + Sentimiento")
print("  Funding Rate Bybit + Fear & Greed | Sin operaciones contra tendencia")
print(SEP)

# Test A: 2026
df_2026 = df_all[(df_all.index>="2026-01-01")&(df_all.index<="2026-06-11")].copy()
print(f"\n  2026 | BTC: ${df_2026['close'].iloc[0]:,.0f} -> ${df_2026['close'].iloc[-1]:,.0f} | "
      f"H4 ST bajista: {(df_2026['h4_st_dir']==-1).sum()/len(df_2026)*100:.0f}% del tiempo | "
      f"F&G medio: {df_2026['fg_value'].mean():.0f}")
t2026 = run_backtest(df_2026.copy())
r2026 = print_report(t2026, "TEST A | 2026 (Ene-Jun) | v4 Supertrend H4", "2026-01-01", "2026-06-11")

# Test B: 2 anos
df_2y = df_all[(df_all.index>="2024-07-01")&(df_all.index<="2026-06-11")].copy()
print(f"\n  2 Anos | BTC: ${df_2y['close'].iloc[0]:,.0f} -> ${df_2y['close'].iloc[-1]:,.0f}")
t2y = run_backtest(df_2y.copy())
r2y = print_report(t2y, "TEST B | 2 ANOS (Jul 2024 - Jun 2026) | v4 Supertrend H4",
                   "2024-07-01", "2026-06-11", show_trades=False)

# Por ano
print("\n  RENDIMIENTO POR ANO")
print("-"*W)
t2y["year"] = pd.to_datetime(t2y["exit_date"]).dt.year
print("  {:<8} {:>8} {:>10} {:>11} {:>6} {:>9}  {:>7} {:>7}".format(
    "ANO","TRADES","WINRATE","P&L","PF","RET ANUAL","L WR","S WR"))
print("  "+"-"*70)
for year, grp in t2y.groupby("year"):
    yw=grp[grp["pnl_usd"]>0]; yl=grp[grp["pnl_usd"]<=0]
    ypf=yw["pnl_usd"].sum()/abs(yl["pnl_usd"].sum()) if len(yl) and yl["pnl_usd"].sum()!=0 else 999
    lo=grp[grp["type"]=="long"]; sh=grp[grp["type"]=="short"]
    lw=lo[lo["pnl_usd"]>0]; sw=sh[sh["pnl_usd"]>0]
    lwr_y=len(lw)/len(lo)*100 if len(lo) else 0
    swr_y=len(sw)/len(sh)*100 if len(sh) else 0
    ok="[OK]" if ypf>1.2 and grp["pnl_usd"].sum()>0 else "[  ]"
    print("  {:<8} {:>8} {:>9.1f}% ${:>10,.0f} {:>6.2f} {:>+8.1f}%  {:>6.0f}% {:>6.0f}%  {}".format(
        year,len(grp),len(yw)/len(grp)*100,grp["pnl_usd"].sum(),ypf,
        grp["pnl_usd"].sum()/INITIAL_CAPITAL*100,lwr_y,swr_y,ok))

# DD y challenges 2 anos
eq=[INITIAL_CAPITAL]+t2y["capital"].tolist(); pk=eq[0]; dd2y=0.0
for v in eq:
    pk=max(pk,v)
    if pk>0: dd2y=min(dd2y,(v-pk)/pk*100)

ch=0; in_ch=True; ch_cap=INITIAL_CAPITAL; ch_pk=INITIAL_CAPITAL
for t in t2y.itertuples():
    if not in_ch: in_ch=True; ch_cap=t.capital; ch_pk=t.capital
    ch_pk=max(ch_pk,t.capital)
    if t.capital>=ch_cap*1.08: ch+=1; in_ch=False
    elif (t.capital-ch_cap)/ch_cap<=-0.10: in_ch=False

print("="*W)
print(f"  Retorno 2 anos  : {r2y.get('ret',0):+.1f}%  |  Capital: ${t2y['capital'].iloc[-1]:,.0f}")
print(f"  Max DD 2 anos   : {dd2y:+.1f}%")
print(f"  PF 2 anos       : {r2y.get('pf',0):.2f}  |  WR: {r2y.get('wr',0):.1f}%")
print(f"  Short WR / PF   : {r2y.get('swr',0):.1f}% / {r2y.get('spf',0):.2f}")
print(f"  Long  WR / PF   : {r2y.get('lwr',0):.1f}% / {r2y.get('lpf',0):.2f}")
print(f"  Challenges CFT  : {ch}")
print("="*W)

t2026.to_csv("test_2026_v4.csv", index=False)
t2y.to_csv("test_2y_v4.csv", index=False)
print(f"\n  Exportado: test_2026_v4.csv  |  test_2y_v4.csv")
print("="*W)
