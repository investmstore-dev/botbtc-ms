"""
TEST: Cierre EOD (20:00 UTC) vs Mantener overnight (hasta SL/TP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compara la estrategia actual (cierra al final de la sesion) contra dejar
correr el trade hasta que toque SL o TP, aunque cruce la medianoche.

Reutiliza prepare/check_entry/PARAMS de backtest_portfolio.py (no toca produccion).
Prueba por par (BTC, DOGE, AVAX), 2 anos.

Uso: python model/test_hold_overnight.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import backtest_portfolio as bp

# AVAX no esta en el config base de backtest_portfolio; lo agregamos (config-D)
bp.PARAMS.setdefault("AVAXUSDT", dict(
    risk_trend=0.014, risk_neutral=0.008, risk_choppy=0.004,
    adx_min=22, adx_choppy=28, dd_lo=0.03, dd_lo_risk=0.006,
    dd_hi=0.05, dd_hi_risk=0.003))

INITIAL = bp.INITIAL_CAPITAL


def run_single(df, sym, hold_overnight: bool):
    """Backtest de un par. hold_overnight=False replica el cierre EOD actual."""
    p = bp.PARAMS[sym]
    capital, peak = INITIAL, INITIAL
    trades, pos, daily_start = [], None, {}
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        dt, hour = df.index[i].date(), df.index[i].hour
        daily_start.setdefault(dt, capital)
        if pos:
            # Cierre EOD (solo si NO mantenemos overnight)
            if not hold_overnight and hour >= 20:
                m = 1 if pos["type"]=="long" else -1
                pnl = (row["close"]-pos["entry"])*m*pos["lot"]
                capital += pnl; peak = max(peak, capital)
                trades.append({**pos, "pnl_usd":pnl, "capital":capital, "exit_date":df.index[i]})
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
                trades.append({**pos, "pnl_usd":pnl, "capital":capital, "exit_date":df.index[i]})
                pos = None
            continue
        if peak>0 and (capital-peak)/peak <= -0.10: continue
        if (capital-daily_start[dt])/daily_start[dt] <= -0.05: continue
        if not (4 <= hour < 20): continue
        np_ = bp.check_entry(row, prev, p, capital, peak)
        if np_:
            np_["entry_date"] = df.index[i]
            pos = np_
    return pd.DataFrame(trades)


def stats(t):
    if t.empty:
        return None
    wins = t[t["pnl_usd"]>0]; loss = t[t["pnl_usd"]<=0]
    n = len(t); wr = len(wins)/n*100
    pf = wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin = t["capital"].iloc[-1]; ret = (fin-INITIAL)/INITIAL*100
    eq=[INITIAL]+t["capital"].tolist(); pk=eq[0]; dd=0.0
    for v in eq:
        pk=max(pk,v)
        if pk>0: dd=min(dd,(v-pk)/pk*100)
    ch=0; cap=INITIAL; active=True
    for x in t.itertuples():
        if not active: active=True; cap=x.capital
        if x.capital>=cap*1.08: ch+=1; active=False
        elif (x.capital-cap)/cap<=-0.10: active=False
    return dict(ret=ret, dd=dd, pf=pf, n=n, wr=wr, ch=ch)


if __name__ == "__main__":
    print("="*82)
    print("  TEST: Cierre EOD (actual) vs Mantener overnight hasta SL/TP")
    print("  2 anos (Jul 2024 - Jun 2026)")
    print("="*82)
    print("  {:<9} {:<14} {:>8} {:>7} {:>6} {:>7} {:>5} {:>6}".format(
        "PAR","MODO","RETORNO","MAXDD","PF","TRADES","WR","CHALL"))
    print("  "+"-"*78)
    for sym in ["BTCUSDT","DOGEUSDT","AVAXUSDT"]:
        df = bp.prepare(sym)
        d2y = df[(df.index>="2024-07-01")&(df.index<="2026-06-11")].copy()
        for hold, label in [(False,"EOD (actual)"), (True,"Overnight")]:
            s = stats(run_single(d2y, sym, hold))
            if s:
                print("  {:<9} {:<14} {:>+7.1f}% {:>+6.1f}% {:>6.2f} {:>7} {:>4.0f}% {:>6}".format(
                    sym, label, s["ret"], s["dd"], s["pf"], s["n"], s["wr"], s["ch"]))
        print("  "+"-"*78)
    print("="*82)
