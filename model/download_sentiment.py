"""
Descarga datos de sentimiento para integrar en el backtest:
  1. Bybit Funding Rate BTCUSDT (cada 8h) - Jan 2024 a Jun 2026
  2. Crypto Fear & Greed Index (diario)   - Jan 2024 a Jun 2026

Uso: python download_sentiment.py
"""
import requests
import pandas as pd
import time
from datetime import datetime, timezone

# ── 1. BYBIT FUNDING RATE ────────────────────────────────────────────────────
print("=" * 55)
print("  Descargando Bybit Funding Rate BTCUSDT...")
print("=" * 55)

BASE_URL  = "https://api.bybit.com/v5/market/funding/history"
START_MS  = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS    = int(datetime(2026, 6, 12, tzinfo=timezone.utc).timestamp() * 1000)
INTERVAL_MS = 8 * 60 * 60 * 1000  # 8 horas

all_funding = []
current_end = END_MS
calls = 0

while current_end > START_MS:
    params = {
        "category": "linear",
        "symbol":   "BTCUSDT",
        "endTime":  current_end,
        "limit":    200,
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  Error: {e} — reintentando en 5s...")
        time.sleep(5)
        continue

    if data.get("retCode") != 0:
        print(f"  Error API: {data.get('retMsg')}")
        break

    rows = data["result"].get("list", [])
    if not rows:
        break

    for row in rows:
        ts_ms = int(row["fundingRateTimestamp"])
        if ts_ms < START_MS:
            continue
        all_funding.append({
            "datetime":    datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
            "funding_rate": float(row["fundingRate"]),
        })

    oldest_ts = int(rows[-1]["fundingRateTimestamp"])
    if oldest_ts <= START_MS:
        break
    current_end = oldest_ts - 1
    calls += 1

    pct = (END_MS - current_end) / (END_MS - START_MS) * 100
    print(f"  [{calls:3d}] Hasta {datetime.fromtimestamp(oldest_ts/1000).date()} | {len(all_funding):,} entradas | {pct:.1f}%", end="\r")
    time.sleep(0.2)

print()

if all_funding:
    df_fund = pd.DataFrame(all_funding)
    df_fund.sort_values("datetime", inplace=True)
    df_fund.drop_duplicates(subset="datetime", inplace=True)
    df_fund.set_index("datetime", inplace=True)
    df_fund.to_csv("btcusdt_funding_rate.csv")
    print(f"  Entradas descargadas : {len(df_fund):,}")
    print(f"  Rango                : {df_fund.index[0].date()} - {df_fund.index[-1].date()}")
    fr_neg = (df_fund["funding_rate"] < 0).sum()
    print(f"  Funding negativo     : {fr_neg:,} de {len(df_fund):,} ({fr_neg/len(df_fund)*100:.1f}%)")
    print(f"  Funding rate max     : {df_fund['funding_rate'].max():.5f}")
    print(f"  Funding rate min     : {df_fund['funding_rate'].min():.5f}")
    print(f"  Guardado             : btcusdt_funding_rate.csv")
else:
    print("  Sin datos descargados.")

print()

# ── 2. FEAR & GREED INDEX ────────────────────────────────────────────────────
print("=" * 55)
print("  Descargando Fear & Greed Index (alternative.me)...")
print("=" * 55)

try:
    r = requests.get(
        "https://api.alternative.me/fng/?limit=2000&format=json",
        timeout=20
    )
    r.raise_for_status()
    fg_data = r.json()["data"]

    fg_rows = []
    for d in fg_data:
        ts = int(d["timestamp"])
        dt = datetime.fromtimestamp(ts).date()
        fg_rows.append({
            "date":  dt,
            "fg_value": int(d["value"]),
            "fg_class": d["value_classification"],
        })

    df_fg = pd.DataFrame(fg_rows)
    df_fg.sort_values("date", inplace=True)
    df_fg.drop_duplicates(subset="date", inplace=True)
    df_fg.set_index("date", inplace=True)

    # Filtrar rango 2024-2026
    df_fg = df_fg[df_fg.index >= pd.to_datetime("2024-01-01").date()]

    df_fg.to_csv("fear_greed_index.csv")
    print(f"  Entradas descargadas : {len(df_fg):,} dias")
    print(f"  Rango                : {df_fg.index[0]} - {df_fg.index[-1]}")
    ef = (df_fg["fg_value"] < 25).sum()
    f  = ((df_fg["fg_value"] >= 25) & (df_fg["fg_value"] < 50)).sum()
    g  = ((df_fg["fg_value"] >= 50) & (df_fg["fg_value"] < 75)).sum()
    eg = (df_fg["fg_value"] >= 75).sum()
    print(f"  Extreme Fear (<25)   : {ef} dias")
    print(f"  Fear (25-50)         : {f} dias")
    print(f"  Greed (50-75)        : {g} dias")
    print(f"  Extreme Greed (>75)  : {eg} dias")
    print(f"  Guardado             : fear_greed_index.csv")

except Exception as e:
    print(f"  Error descargando Fear & Greed: {e}")

print()
print("=" * 55)
print("  Descarga completada. Ahora ejecuta:")
print("  python backtest_cft_2026_v2.py")
print("=" * 55)
