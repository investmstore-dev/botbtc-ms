"""
BACKTEST PORTAFOLIO 3 PARES | BTC + DOGE + AVAX en UNA cuenta (modo SINGLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reutiliza TODA la logica validada de backtest_portfolio.py (prepare, run_portfolio,
report). Solo agrega AVAXUSDT a la canasta. No toca el codigo de produccion.

AVAX usa los parametros v5b base (en el escaneo dio +51.3% / DD -7.6% / 4 challenges,
CFT-seguro), igual que BTC.

Uso: python model/backtest_portfolio3.py
"""
import warnings
warnings.filterwarnings("ignore")

import backtest_portfolio as bp

# Agregar AVAX a la config (params v5b base, ya CFT-seguros para AVAX)
bp.PARAMS["AVAXUSDT"] = dict(
    risk_trend=0.018, risk_neutral=0.010, risk_choppy=0.005,
    adx_min=22, adx_choppy=28, dd_lo=0.04, dd_lo_risk=0.008,
    dd_hi=0.06, dd_hi_risk=0.005,
)

SYMBOLS = ["BTCUSDT", "DOGEUSDT", "AVAXUSDT"]


if __name__ == "__main__":
    print("=" * 78)
    print("  BACKTEST PORTAFOLIO 3 PARES | BTC + DOGE + AVAX | cuenta unica SINGLE")
    print("  Periodo: Jul 2024 - Jun 2026 (2 anos)")
    print("=" * 78)
    print("\n  Preparando datos...")
    dfs_full = {s: bp.prepare(s) for s in SYMBOLS}
    dfs = {s: d[(d.index >= "2024-07-01") & (d.index <= "2026-06-11")].copy()
           for s, d in dfs_full.items()}

    # Solo modo SINGLE (el elegido en produccion)
    bp.report(bp.run_portfolio(dfs, "single"),
              "3 PARES SINGLE (BTC + DOGE + AVAX) | 2 anos")

    # 2026 (mercado choppy)
    print("\n\n" + "#" * 78)
    print("  SOLO 2026 (Ene-Jun, mercado choppy)")
    print("#" * 78)
    dfs26 = {s: d[(d.index >= "2026-01-01") & (d.index <= "2026-06-11")].copy()
             for s, d in dfs_full.items()}
    bp.report(bp.run_portfolio(dfs26, "single"), "3 PARES SINGLE | 2026")

    # Referencia: 2 pares (BTC+DOGE) para comparar el aporte de AVAX
    print("\n\n" + "#" * 78)
    print("  REFERENCIA: 2 PARES (BTC + DOGE) mismo periodo")
    print("#" * 78)
    dfs2 = {s: dfs[s] for s in ["BTCUSDT", "DOGEUSDT"]}
    bp.report(bp.run_portfolio(dfs2, "single"), "2 PARES SINGLE (BTC + DOGE) | 2 anos")
    print("=" * 78)
