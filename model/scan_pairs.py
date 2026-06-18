"""
ESCANER DE PARES | Estrategia v5b sobre canasta de pares volatiles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reutiliza prepare/run_backtest/metrics de backtest_multipair.py y prueba
mas pares para encontrar candidatos a sumar a la rotacion SINGLE.

Criterio de candidato: DD 2y < -9% (margen CFT) Y >= 2 challenges en 2 anos.

Uso: python model/scan_pairs.py
"""
import warnings
warnings.filterwarnings("ignore")

from backtest_multipair import prepare, run_backtest, metrics

# Canasta a evaluar (Bybit linear USDT) + BTC/DOGE como referencia.
# Pares volátiles y liquidos con historia desde 2024.
CANDIDATES = [
    "BTCUSDT", "DOGEUSDT",                 # referencia (ya en produccion)
    "SOLUSDT", "AVAXUSDT", "LINKUSDT",     # alta volatilidad direccional
    "XRPUSDT", "ADAUSDT", "DOTUSDT",
    "SUIUSDT", "LTCUSDT", "NEARUSDT",
]


def evaluate(sym):
    df = prepare(sym)
    df2y = df[(df.index >= "2024-07-01") & (df.index <= "2026-06-11")].copy()
    df26 = df[(df.index >= "2026-01-01") & (df.index <= "2026-06-11")].copy()
    return {
        "2y":     metrics(run_backtest(df2y)),
        "2026":   metrics(run_backtest(df26)),
        "chop2y": df2y["h4_chop"].mean(),
        "candles": len(df2y),
    }


if __name__ == "__main__":
    print("=" * 86)
    print("  ESCANER DE PARES | estrategia v5b (Jul 2024 - Jun 2026)")
    print("  Candidato = DD 2y < -9% (margen CFT) Y >= 2 challenges")
    print("=" * 86)

    results = {}
    for sym in CANDIDATES:
        try:
            print(f"\n[{sym}] preparando/backtest...")
            results[sym] = evaluate(sym)
            m = results[sym]["2y"]
            print(f"  ret {m['ret']:+.1f}% | DD {m['dd']:+.1f}% | PF {m['pf']:.2f} | "
                  f"{m['n']} trades | {m['ch']} challenges")
        except Exception as e:
            print(f"  ERROR {sym}: {e}")

    # Tabla comparativa ordenada por challenges, luego retorno
    print("\n" + "=" * 86)
    print("  RANKING 2 AÑOS (ordenado por challenges + retorno)")
    print("=" * 86)
    print("  {:<9} {:>7} {:>7} {:>6} {:>7} {:>5} {:>6} {:>8}  {}".format(
        "PAR", "RETORNO", "MAXDD", "PF", "TRADES", "WR", "CHALL", "RET2026", "CFT?"))
    print("  " + "-" * 84)

    rows = []
    for sym, r in results.items():
        m, m26 = r["2y"], r["2026"]
        if not m:
            continue
        safe = abs(m["dd"]) < 9.0 and m["ch"] >= 2
        rows.append((sym, m, m26, safe))

    for sym, m, m26, safe in sorted(rows, key=lambda x: (-x[1]["ch"], -x[1]["ret"])):
        flag = "** CANDIDATO **" if safe else ("DD alto" if abs(m["dd"]) >= 9 else "-")
        r26 = f"{m26['ret']:+.1f}%" if m26 else "n/a"
        print("  {:<9} {:>+6.1f}% {:>+6.1f}% {:>6.2f} {:>7} {:>4.0f}% {:>6} {:>8}  {}".format(
            sym, m["ret"], m["dd"], m["pf"], m["n"], m["wr"], m["ch"], r26, flag))

    print("\n  Detalle challenges (dias para cada +8%):")
    print("  " + "-" * 84)
    for sym, m, _, _ in sorted(rows, key=lambda x: (-x[1]["ch"], -x[1]["ret"])):
        print(f"    {sym:<9} {m['ch']} -> {m['ch_days']}")
    print("=" * 86)
