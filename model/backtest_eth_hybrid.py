"""
BACKTEST ESTRATEGIA HIBRIDA ETH/USDT (documento externo) | DATOS REALES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Implementacion fiel de la estrategia del documento 'estrategia_hibrido_eth.docx'
para validarla con datos reales de Bybit (NO toca el bot de produccion).

Sistema hibrido:
  ADX(1H) > 27  -> SWING : tendencia 4H + pullback EMA50 | SL 2.0xATR  TP 9.0xATR (R:R 4.5)
  ADX(1H) < 27  -> SCALP : scoring S9+S6+ADX (>=2)       | SL 1.5xATR  TP 4.5xATR (R:R 3)

Reglas: riesgo 1.2%/trade (equilibrado), DD diario 4% stop, max 6 trades/dia,
cooldown 1 barra, sesion 06-22 UTC, mantiene overnight (sale por SL/TP).

Reclamo del documento: +119% 30 meses, DD -6.1%, PF 2.72, WR 51.3%, 39 trades.

Uso: python model/backtest_eth_hybrid.py
"""
import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data_backtest")
INITIAL_CAPITAL = 10_000

# ── Parametros (config 'equilibrado' del documento) ──────────────────────────
RISK_PCT       = 0.012
ADX_REGIME     = 27       # > swing, < scalp
SWING_SL, SWING_TP = 2.0, 9.0
SCALP_SL, SCALP_TP = 1.5, 4.5
MAX_TRADES_DAY = 6
COOLDOWN_BARS  = 1
SESSION_START, SESSION_END = 6, 22   # UTC
DAILY_DD_STOP  = 0.04     # documento: para el dia si DD diario > 4%
CFT_MAX_DD     = 0.10     # nuestra cuenta CFT real (-10%)
CFT_DAILY_DD   = 0.05     # nuestra cuenta CFT real (-5%)


def ema(s, n):  return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - (100 / (1 + g / l.replace(0, np.nan)))


def atr(df, n=14):
    tr = pd.concat([(df["high"]-df["low"]),
                    (df["high"]-df["close"].shift()).abs(),
                    (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(n).mean()
    pdi = 100 * pdm.rolling(n).mean() / atr_
    mdi = 100 * mdm.rolling(n).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(n).mean()


def prepare():
    df = pd.read_csv(os.path.join(CACHE_DIR, "ethusdt_h1.csv"),
                     parse_dates=["datetime"]).set_index("datetime").sort_index()
    df = df[["open","high","low","close","volume"]].dropna()
    c = df["close"]

    # 1H
    df["ema21"] = ema(c, 21); df["ema50"] = ema(c, 50); df["ema200"] = ema(c, 200)
    df["rsi"]   = rsi(c, 14)
    df["atr"]   = atr(df, 14)
    df["adx"]   = adx(df, 14)
    macd = ema(c, 12) - ema(c, 26)
    sig  = macd.ewm(span=9, adjust=False).mean()
    df["macd"] = macd; df["macd_sig"] = sig; df["macd_hist"] = macd - sig
    df["macd_hist_prev"] = df["macd_hist"].shift(1)
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    # 4H
    h4 = df.resample("4h").agg(open=("open","first"), high=("high","max"),
                              low=("low","min"), close=("close","last"),
                              volume=("volume","sum")).dropna()
    h4["ema21"] = ema(h4["close"], 21)
    h4["ema50"] = ema(h4["close"], 50)
    h4["ema200"] = ema(h4["close"], 200)
    h4["slope_up"]   = h4["ema21"] > h4["ema21"].shift(6)
    h4["slope_down"] = h4["ema21"] < h4["ema21"].shift(6)
    for col in ["ema21","ema50","ema200","slope_up","slope_down"]:
        df[f"h4_{col}"] = h4[col].reindex(df.index, method="ffill")

    return df.dropna(subset=["ema200","adx","atr","h4_ema200","vol_ma20"])


def swing_signal(r):
    """Modo swing (ADX>27): tendencia 4H + pullback. Retorna 'long'/'short'/None."""
    h4_bull = r["h4_ema21"] > r["h4_ema50"] > r["h4_ema200"] and r["h4_slope_up"]
    h4_bear = r["h4_ema21"] < r["h4_ema50"] < r["h4_ema200"] and r["h4_slope_down"]
    if (h4_bull and r["close"] > r["ema50"] and 36 <= r["rsi"] <= 54
            and r["adx"] > 20 and r["macd"] > r["macd_sig"]):
        return "long"
    if (h4_bear and r["close"] < r["ema50"] and 46 <= r["rsi"] <= 64
            and r["adx"] > 20 and r["macd"] < r["macd_sig"]):
        return "short"
    return None


def scalp_signal(r):
    """Modo scalp (ADX<27): scoring S9+S6+ADX (>=2) + volumen. 'long'/'short'/None."""
    if r["volume"] <= 0.8 * r["vol_ma20"]:
        return None
    # LONG
    s9_l = (r["ema21"] > r["ema50"] > r["ema200"] and 40 <= r["rsi"] <= 55
            and r["close"] > r["ema21"] and r["adx"] > 25)
    s6_l = (r["macd"] > r["macd_sig"] and r["macd_hist"] > r["macd_hist_prev"]
            and 45 <= r["rsi"] <= 70 and r["close"] > r["ema50"])
    bonus_l = r["adx"] > 28
    if (s9_l + s6_l + bonus_l) >= 2 and (s9_l or s6_l):
        return "long"
    # SHORT (invertido)
    s9_s = (r["ema21"] < r["ema50"] < r["ema200"] and 45 <= r["rsi"] <= 60
            and r["close"] < r["ema21"] and r["adx"] > 25)
    s6_s = (r["macd"] < r["macd_sig"] and r["macd_hist"] < r["macd_hist_prev"]
            and 30 <= r["rsi"] <= 55 and r["close"] < r["ema50"])
    bonus_s = r["adx"] > 28
    if (s9_s + s6_s + bonus_s) >= 2 and (s9_s or s6_s):
        return "short"
    return None


def run(df):
    capital, peak = INITIAL_CAPITAL, INITIAL_CAPITAL
    trades, pos = [], None
    daily_start, daily_count, daily_stopped = {}, {}, set()
    last_exit_idx = -COOLDOWN_BARS - 1

    idx = list(df.index)
    for i in range(1, len(df)):
        r = df.iloc[i]
        ts = idx[i]; dt = ts.date(); hour = ts.hour
        daily_start.setdefault(dt, capital)
        daily_count.setdefault(dt, 0)

        # Gestionar posicion abierta (SL/TP intrabar, mantiene overnight)
        if pos:
            sl_hit = ((pos["type"]=="long" and r["low"]<=pos["sl"]) or
                      (pos["type"]=="short" and r["high"]>=pos["sl"]))
            tp_hit = ((pos["type"]=="long" and r["high"]>=pos["tp"]) or
                      (pos["type"]=="short" and r["low"]<=pos["tp"]))
            if sl_hit or tp_hit:
                ep = pos["tp"] if tp_hit else pos["sl"]
                m = 1 if pos["type"]=="long" else -1
                pnl = (ep - pos["entry"]) * m * pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "exit":ep, "pnl_usd":pnl, "capital":capital,
                               "exit_reason":"TP" if tp_hit else "SL", "exit_date":ts})
                pos = None; last_exit_idx = i
            continue

        # Reglas de riesgo
        if peak>0 and (capital-peak)/peak <= -CFT_MAX_DD: continue
        dd_day = (capital - daily_start[dt]) / daily_start[dt]
        if dd_day <= -DAILY_DD_STOP: daily_stopped.add(dt)
        if dt in daily_stopped: continue
        if daily_count[dt] >= MAX_TRADES_DAY: continue
        if i - last_exit_idx <= COOLDOWN_BARS: continue
        if not (SESSION_START <= hour < SESSION_END): continue

        # Deteccion de regimen + senal
        if r["adx"] > ADX_REGIME:
            sig = swing_signal(r); sl_m, tp_m, mode = SWING_SL, SWING_TP, "swing"
        else:
            sig = scalp_signal(r); sl_m, tp_m, mode = SCALP_SL, SCALP_TP, "scalp"
        if not sig:
            continue

        sl_dist = sl_m * r["atr"]; tp_dist = tp_m * r["atr"]
        lot = (capital * RISK_PCT) / sl_dist
        entry = r["close"]
        if sig == "long":
            pos = {"type":"long", "entry":entry, "sl":entry-sl_dist, "tp":entry+tp_dist,
                   "lot":lot, "entry_date":ts, "mode":mode}
        else:
            pos = {"type":"short", "entry":entry, "sl":entry+sl_dist, "tp":entry-tp_dist,
                   "lot":lot, "entry_date":ts, "mode":mode}
        daily_count[dt] += 1

    return pd.DataFrame(trades)


def report(t, label):
    print("\n" + "="*78)
    print(f"  {label}")
    print("="*78)
    if t.empty:
        print("  Sin trades."); return
    wins = t[t["pnl_usd"]>0]; loss = t[t["pnl_usd"]<=0]
    n = len(t); wr = len(wins)/n*100
    pf = wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin = t["capital"].iloc[-1]; ret = (fin-INITIAL_CAPITAL)/INITIAL_CAPITAL*100
    eq = [INITIAL_CAPITAL]+t["capital"].tolist(); pk=eq[0]; dd=0.0
    for v in eq:
        pk=max(pk,v)
        if pk>0: dd=min(dd,(v-pk)/pk*100)
    days = t["entry_date"].dt.date.nunique()
    # challenges +8% sin violar -10%
    ch=0; cap=INITIAL_CAPITAL; start=None; active=True; ch_days=[]
    for x in t.itertuples():
        if not active:
            active=True; cap=x.capital; start=x.entry_date
        if x.capital >= cap*1.08:
            ch_days.append((pd.to_datetime(x.exit_date)-pd.to_datetime(start or x.entry_date)).days)
            ch+=1; active=False
        elif (x.capital-cap)/cap <= -0.10:
            active=False
    print(f"  Retorno total   : {ret:+.1f}%   |  Capital final: ${fin:,.0f}")
    print(f"  Max Drawdown    : {dd:+.1f}%   {'[OK CFT -10%]' if abs(dd)<10 else '[VIOLA -10%]'}")
    print(f"  Profit Factor   : {pf:.2f}   |  Win Rate: {wr:.1f}%")
    print(f"  Trades totales  : {n}  |  Dias operados: {days}")
    print(f"  Challenges CFT  : {ch}  (dias c/u: {ch_days})")
    print("  " + "-"*74)
    for mode in ["swing","scalp"]:
        m_ = t[t["mode"]==mode]
        if len(m_):
            w = m_[m_["pnl_usd"]>0]
            mpf = w["pnl_usd"].sum()/abs(m_[m_["pnl_usd"]<=0]["pnl_usd"].sum()) if len(m_[m_["pnl_usd"]<=0]) else 999
            print(f"    {mode.upper():<6} {len(m_):>3} trades | WR {len(w)/len(m_)*100:>4.0f}% | "
                  f"PF {mpf:.2f} | P&L ${m_['pnl_usd'].sum():>+8,.0f}")
    for side in ["long","short"]:
        s_ = t[t["type"]==side]
        if len(s_):
            w = s_[s_["pnl_usd"]>0]
            print(f"    {side.upper():<6} {len(s_):>3} trades | WR {len(w)/len(s_)*100:>4.0f}% | "
                  f"P&L ${s_['pnl_usd'].sum():>+8,.0f}")


if __name__ == "__main__":
    print("="*78)
    print("  BACKTEST ESTRATEGIA HIBRIDA ETH/USDT | datos reales Bybit")
    print("  Reclamo del documento: +119% 30m | DD -6.1% | PF 2.72 | 39 trades")
    print("="*78)
    df = prepare()
    print(f"  Velas preparadas: {len(df):,}  ({df.index[0].date()} a {df.index[-1].date()})")

    full = df[(df.index>="2024-01-01")&(df.index<="2026-06-11")].copy()
    report(run(full), "PERIODO COMPLETO (Ene 2024 - Jun 2026, ~30 meses)")

    y2 = df[(df.index>="2024-07-01")&(df.index<="2026-06-11")].copy()
    report(run(y2), "2 ANOS (Jul 2024 - Jun 2026) - comparable con BTC/DOGE")

    y26 = df[(df.index>="2026-01-01")&(df.index<="2026-06-11")].copy()
    report(run(y26), "2026 (Ene-Jun, mercado choppy)")
    print("="*78)
