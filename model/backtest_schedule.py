"""
TEST horario de entrada | cuenta PERSONAL (sin sentimiento, overnight, x compounding)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Compara la ventana de entrada actual (04:00-20:00 UTC) contra extenderla a casi 24h
(04:00-23:59), manteniendo la formacion del rango ORB (00:00-04:00).

Replica la config de la cuenta personal:
  - SIN sentimiento (funding=0, fg=50 -> filtros pasan siempre)
  - Overnight (no se cierra por fin de sesion; corre hasta SL/TP)
  - BTC v5b + DOGE config-D

Uso: python model/backtest_schedule.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import backtest_portfolio as bp

INITIAL = bp.INITIAL_CAPITAL


def run_single(df, sym, close_hour):
    """Personal: sin sentimiento, overnight, ventana de entrada 04:00-close_hour."""
    p = bp.PARAMS[sym]
    capital, peak = INITIAL, INITIAL
    trades, pos, daily_start = [], None, {}
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        dt, hour = df.index[i].date(), df.index[i].hour
        daily_start.setdefault(dt, capital)
        if pos:  # overnight: solo cierra por SL/TP
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
        if not (4 <= hour < close_hour): continue           # <-- ventana de entrada
        np_ = bp.check_entry(row, prev, p, capital, peak)
        if np_:
            np_["entry_date"] = df.index[i]; pos = np_
    return pd.DataFrame(trades)


def stats(t):
    if t.empty: return None
    wins=t[t["pnl_usd"]>0]; loss=t[t["pnl_usd"]<=0]
    n=len(t); wr=len(wins)/n*100
    pf=wins["pnl_usd"].sum()/abs(loss["pnl_usd"].sum()) if len(loss) and loss["pnl_usd"].sum()!=0 else 999
    fin=t["capital"].iloc[-1]; ret=(fin-INITIAL)/INITIAL*100
    eq=[INITIAL]+t["capital"].tolist(); pk=eq[0]; dd=0.0
    for v in eq:
        pk=max(pk,v)
        if pk>0: dd=min(dd,(v-pk)/pk*100)
    return dict(ret=ret, dd=dd, pf=pf, n=n, wr=wr)


if __name__ == "__main__":
    print("="*80)
    print("  TEST ventana de entrada | cuenta PERSONAL (sin sentimiento + overnight)")
    print("  2 anos (Jul 2024 - Jun 2026)")
    print("="*80)
    print("  {:<9} {:<22} {:>8} {:>7} {:>6} {:>7} {:>5}".format(
        "PAR","VENTANA","RETORNO","MAXDD","PF","TRADES","WR"))
    print("  "+"-"*74)
    for sym in ["BTCUSDT","DOGEUSDT"]:
        df = bp.prepare(sym)
        d2y = df[(df.index>="2024-07-01")&(df.index<="2026-06-11")].copy()
        d2y["funding_rate"]=0.0; d2y["fg_value"]=50.0   # SIN sentimiento
        for close_h, label in [(20,"04-20 UTC (actual)"), (24,"04-24 UTC (extendida)")]:
            s = stats(run_single(d2y, sym, close_h))
            if s:
                print("  {:<9} {:<22} {:>+7.1f}% {:>+6.1f}% {:>6.2f} {:>7} {:>4.0f}%".format(
                    sym, label, s["ret"], s["dd"], s["pf"], s["n"], s["wr"]))
        print("  "+"-"*74)
    print("="*80)
