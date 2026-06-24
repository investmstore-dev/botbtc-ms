"""
BACKTEST ESTRATEGIA FUNDAMENTAL — MVRV Z-Score (BTC)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Estrategia on-chain (fundamental), NO tecnica:
  - Comprar/acumular cuando MVRV Z-Score < umbral_bajo  (BTC infravalorado)
  - Vender/salir cuando MVRV Z-Score > umbral_alto       (BTC sobrevalorado)
Long-only, mantiene a traves de la volatilidad (enfoque de ciclo).

Datos GRATIS: bitcoin-data.com (MVRV Z-Score + precio BTC), 2022-2026.
Uso: python model/backtest_mvrv.py
"""
import requests
import pandas as pd
import numpy as np

HDR = {"User-Agent": "Mozilla/5.0"}


def load_data():
    mvrv = requests.get("https://bitcoin-data.com/v1/mvrv-zscore", timeout=30, headers=HDR).json()
    price = requests.get("https://bitcoin-data.com/v1/btc-price", timeout=30, headers=HDR).json()
    dm = pd.DataFrame(mvrv)[["d", "mvrvZscore"]].rename(columns={"d": "date", "mvrvZscore": "z"})
    dp = pd.DataFrame(price)[["d", "btcPrice"]].rename(columns={"d": "date", "btcPrice": "price"})
    df = dm.merge(dp, on="date")
    df["date"] = pd.to_datetime(df["date"])
    df["z"] = df["z"].astype(float)
    df["price"] = df["price"].astype(float)
    return df.sort_values("date").reset_index(drop=True)


def backtest(df, buy_th, sell_th, capital=10_000):
    cash, btc, in_pos = capital, 0.0, False
    equity = []
    trades = []
    entry_price = None
    for _, r in df.iterrows():
        z, px = r["z"], r["price"]
        if not in_pos and z < buy_th:               # comprar (infravalorado)
            btc = cash / px; cash = 0.0; in_pos = True; entry_price = px
        elif in_pos and z > sell_th:                # vender (sobrevalorado)
            cash = btc * px; pnl = (px/entry_price - 1)*100
            trades.append({"entry": entry_price, "exit": px, "ret_pct": pnl, "exit_date": r["date"]})
            btc = 0.0; in_pos = False
        equity.append(cash + btc * px)
    df = df.copy(); df["equity"] = equity
    fin = equity[-1]; ret = (fin/capital - 1)*100
    peak = -1e18; dd = 0.0
    for e in equity:
        peak = max(peak, e); dd = min(dd, (e-peak)/peak*100)
    tim = (df["equity"].diff().fillna(0) != 0).mean()*100  # aprox % tiempo en mercado
    days_in = sum(1 for i in range(1,len(df)) if df["equity"].iloc[i] != df["equity"].iloc[i-1])
    return {"ret": ret, "dd": dd, "trades": len(trades), "fin": fin,
            "open_now": in_pos, "tlist": trades, "days_in": days_in, "n_days": len(df)}


if __name__ == "__main__":
    print("="*78)
    print("  BACKTEST FUNDAMENTAL — MVRV Z-Score (BTC) | datos bitcoin-data.com")
    df = load_data()
    print(f"  Periodo: {df['date'].iloc[0].date()} a {df['date'].iloc[-1].date()}  ({len(df)} dias)")
    print(f"  MVRV Z rango: min {df['z'].min():.2f}  max {df['z'].max():.2f}  actual {df['z'].iloc[-1]:.2f}")
    bh = (df['price'].iloc[-1]/df['price'].iloc[0]-1)*100
    print(f"  Buy & Hold BTC en el periodo: {bh:+.1f}%")
    print("="*78)
    print("  {:<22} {:>8} {:>8} {:>7} {:>10}".format("REGLA (buy/sell Z)","RETORNO","MAXDD","TRADES","% TIEMPO"))
    print("  "+"-"*70)
    for buy_th, sell_th in [(0.0,3.0),(0.0,2.0),(-0.1,3.0),(0.5,3.0),(0.0,5.0),(0.5,2.5)]:
        m = backtest(df, buy_th, sell_th)
        flag = " (posicion ABIERTA)" if m["open_now"] else ""
        print("  Z<{:+.1f} / Z>{:.1f}        {:>+7.1f}% {:>+7.1f}% {:>7} {:>9.0f}%{}".format(
            buy_th, sell_th, m["ret"], m["dd"], m["trades"], m["days_in"]/m["n_days"]*100, flag))
    print("  "+"-"*70)
    # detalle de la mejor regla tipica
    m = backtest(df, 0.0, 3.0)
    print(f"\n  Detalle regla Z<0 / Z>3:")
    for t in m["tlist"]:
        print(f"    compra ${t['entry']:,.0f} -> vende ${t['exit']:,.0f} = {t['ret_pct']:+.1f}%  ({t['exit_date'].date()})")
    if m["open_now"]:
        print(f"    posicion ABIERTA actualmente (entrada en zona barata, esperando techo)")
    print("="*78)
