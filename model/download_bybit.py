"""
Descarga datos historicos BTCUSDT H1 desde Bybit API v5 (publica, sin API key).
Guarda en btcusdt_h1_bybit.csv listo para el backtest.

Uso: python download_bybit.py
"""
import requests
import pandas as pd
import time
from datetime import datetime, timezone

SYMBOL    = "BTCUSDT"
INTERVAL  = "60"          # 60 minutos = H1
CATEGORY  = "linear"      # USDT perpetual
BASE_URL  = "https://api.bybit.com/v5/market/kline"
LIMIT     = 1000          # max por request
OUT_FILE  = "btcusdt_h1_bybit.csv"

# Rango: 2 años + 6 meses warmup = Jun 2024 → Jun 2026
START_DT  = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DT    = datetime(2026, 6, 11, tzinfo=timezone.utc)

start_ms  = int(START_DT.timestamp() * 1000)
end_ms    = int(END_DT.timestamp()   * 1000)
interval_ms = 60 * 60 * 1000   # 1 hora en ms


def fetch_klines(start_ms: int, end_ms: int) -> list:
    """Descarga velas H1 en lotes de 1000 de mas antiguo a mas reciente."""
    all_rows = []
    current_end = end_ms

    total_expected = (end_ms - start_ms) // interval_ms
    print(f"Estimado: ~{total_expected:,} velas H1 ({total_expected//24} dias)")

    calls = 0
    while current_end > start_ms:
        params = {
            "category": CATEGORY,
            "symbol":   SYMBOL,
            "interval": INTERVAL,
            "end":      current_end,
            "limit":    LIMIT,
        }
        try:
            r = requests.get(BASE_URL, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            print(f"Error HTTP: {e} — reintentando en 5s...")
            time.sleep(5)
            continue

        if data.get("retCode") != 0:
            print(f"Error Bybit API: {data.get('retMsg')}")
            break

        rows = data["result"].get("list", [])
        if not rows:
            break

        # Bybit devuelve de mas reciente a mas antiguo
        # Formato: [timestamp_ms, open, high, low, close, volume, turnover]
        for row in rows:
            ts_ms = int(row[0])
            if ts_ms < start_ms:
                continue
            all_rows.append({
                "datetime": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "open":     float(row[1]),
                "high":     float(row[2]),
                "low":      float(row[3]),
                "close":    float(row[4]),
                "volume":   float(row[5]),
            })

        oldest_ts = int(rows[-1][0])
        current_end = oldest_ts - 1
        calls += 1

        pct = (end_ms - current_end) / (end_ms - start_ms) * 100
        print(f"  [{calls:3d} calls] Descargado hasta {datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).date()} | {len(all_rows):,} velas | {pct:.1f}%", end="\r")

        time.sleep(0.15)   # respetar rate limit

    print()
    return all_rows


def main():
    print("=" * 60)
    print(f"  Descargando {SYMBOL} H1 desde Bybit API v5")
    print(f"  Rango: {START_DT.date()} - {END_DT.date()}")
    print("=" * 60)

    rows = fetch_klines(start_ms, end_ms)

    if not rows:
        print("Sin datos descargados.")
        return

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True).dt.tz_localize(None)
    df.sort_values("datetime", inplace=True)
    df.drop_duplicates(subset="datetime", inplace=True)
    df.set_index("datetime", inplace=True)

    df.to_csv(OUT_FILE)

    print()
    print(f"  Velas descargadas : {len(df):,}")
    print(f"  Inicio            : {df.index[0]}")
    print(f"  Fin               : {df.index[-1]}")
    print(f"  BTC inicio        : ${df['close'].iloc[0]:,.0f}")
    print(f"  BTC fin           : ${df['close'].iloc[-1]:,.0f}")
    print(f"  Archivo guardado  : {OUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
