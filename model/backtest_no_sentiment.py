"""
TEST: Estrategia CON vs SIN sentimiento (funding rate + Fear&Greed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MT5/ADN Broker NO provee funding rate ni Fear&Greed. Este test valida si la
estrategia crypto (ORB+Supertrend+Choppiness) se sostiene sin esos filtros,
para decidir si tiene sentido operar crypto-CFD en ADN.

Truco: poner funding_rate=0 y fg_value=50 hace que los filtros de sentimiento
SIEMPRE pasen -> equivale a desactivarlos, sin tocar el codigo.

Reutiliza backtest_portfolio.py. Uso: python model/backtest_no_sentiment.py
"""
import warnings
warnings.filterwarnings("ignore")

import backtest_portfolio as bp

bp.PARAMS.setdefault("AVAXUSDT", dict(
    risk_trend=0.014, risk_neutral=0.008, risk_choppy=0.004,
    adx_min=22, adx_choppy=28, dd_lo=0.03, dd_lo_risk=0.006,
    dd_hi=0.05, dd_hi_risk=0.003))

SYMS = ["BTCUSDT", "DOGEUSDT", "AVAXUSDT"]


def slice_2y(d):
    return d[(d.index >= "2024-07-01") & (d.index <= "2026-06-11")].copy()


if __name__ == "__main__":
    print("=" * 78)
    print("  TEST: estrategia CON vs SIN sentimiento (funding + Fear&Greed)")
    print("  Relevante para crypto-CFD en ADN/MT5 (no tienen esos datos)")
    print("=" * 78)

    full = {s: bp.prepare(s) for s in SYMS}

    # ── CON sentimiento (baseline actual) ────────────────────────────────────
    dfs_con = {s: slice_2y(d) for s, d in full.items()}
    bp.report(bp.run_portfolio(dfs_con, "single"),
              "PORTAFOLIO 3 PARES | CON sentimiento (baseline) | 2y SINGLE")

    # ── SIN sentimiento (funding=0, fg=50 -> filtros siempre pasan) ──────────
    dfs_sin = {}
    for s, d in full.items():
        d2 = slice_2y(d)
        d2["funding_rate"] = 0.0
        d2["fg_value"] = 50.0
        dfs_sin[s] = d2
    bp.report(bp.run_portfolio(dfs_sin, "single"),
              "PORTAFOLIO 3 PARES | SIN sentimiento (MT5/ADN) | 2y SINGLE")

    # Por par individual, sin sentimiento
    print("\n\n" + "#" * 78)
    print("  POR PAR | SIN sentimiento | 2 anos SINGLE")
    print("#" * 78)
    for s in SYMS:
        d2 = slice_2y(full[s])
        d2["funding_rate"] = 0.0; d2["fg_value"] = 50.0
        bp.report(bp.run_portfolio({s: d2}, "single"), f"{s} | SIN sentimiento")
    print("=" * 78)
