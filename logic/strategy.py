"""
Estrategia ORB + MACD/RSI + Supertrend H4 + Choppiness Index
BTCUSD H1 | Crypto Fund Trader | v5b

Logica de regimen:
  1. Supertrend H4 define la DIRECCION: GREEN=solo longs, RED=solo shorts
  2. Choppiness Index H4 define el RIESGO: trend=1.8%, neutral=1.0%, choppy=0.5%
  3. En regimen choppy/neutral, solo se opera en la direccion del Supertrend
  4. Sentimiento externo (funding rate + F&G) filtra entradas de baja calidad
"""
import pandas as pd
import numpy as np


# ── Supertrend ────────────────────────────────────────────────────────────────

def compute_supertrend(df: pd.DataFrame, period: int, mult: float):
    """Retorna columnas st_val y st_dir (+1 alcista, -1 bajista)."""
    hl2 = (df["high"] + df["low"]) / 2
    tr  = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    bu = hl2 + mult * atr
    bl = hl2 - mult * atr
    fu = bu.copy()
    fl = bl.copy()
    st  = pd.Series(np.nan, index=df.index)
    di  = pd.Series(0,      index=df.index, dtype=int)

    for i in range(1, len(df)):
        fu.iloc[i] = (bu.iloc[i] if bu.iloc[i] < fu.iloc[i-1]
                      or df["close"].iloc[i-1] > fu.iloc[i-1] else fu.iloc[i-1])
        fl.iloc[i] = (bl.iloc[i] if bl.iloc[i] > fl.iloc[i-1]
                      or df["close"].iloc[i-1] < fl.iloc[i-1] else fl.iloc[i-1])

        prev_st = st.iloc[i-1]
        c = df["close"].iloc[i]

        if pd.isna(prev_st):
            di.iloc[i] = 1
        elif prev_st == fu.iloc[i-1]:
            di.iloc[i] = 1  if c > fu.iloc[i] else -1
        else:
            di.iloc[i] = -1 if c < fl.iloc[i] else  1

        st.iloc[i] = fl.iloc[i] if di.iloc[i] == 1 else fu.iloc[i]

    df["st_val"] = st
    df["st_dir"] = di
    return df


# ── Choppiness Index ──────────────────────────────────────────────────────────

def compute_choppiness(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Choppiness Index: 0-100
      < 38.2 -> tendencia muy fuerte
      > 61.8 -> choppy / lateral
    Umbrales operativos: < 48 trend, > 57 choppy
    """
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)

    atr_sum = tr.rolling(period).sum()
    hh      = df["high"].rolling(period).max()
    ll      = df["low"].rolling(period).min()
    chop    = 100 * np.log10(atr_sum / (hh - ll).replace(0, np.nan)) / np.log10(period)
    return chop.clip(0, 100)


# ── Indicadores principales ───────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula todos los indicadores sobre el DataFrame H1.
    Tambien resamplea a H4 para Supertrend y Choppiness.
    """
    from config import (EMA_FAST, EMA_SLOW, MACD_FAST, MACD_SLOW, MACD_SIGNAL,
                        RSI_PERIOD, ATR_PERIOD, ADX_PERIOD,
                        ORB_HOUR_START, ORB_HOUR_END,
                        ST_PERIOD, ST_MULT, CHOP_PERIOD)

    c, h, l = df["close"], df["high"], df["low"]

    # EMAs H1
    df["ema20"] = c.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema50"] = c.ewm(span=EMA_SLOW, adjust=False).mean()

    # ATR H1
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"]       = tr.rolling(ATR_PERIOD).mean()
    df["atr_avg20"] = df["atr"].rolling(20).mean()

    # RSI H1
    delta       = c.diff()
    gain        = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss        = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    df["rsi"]   = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    # MACD H1
    ema_f           = c.ewm(span=MACD_FAST,   adjust=False).mean()
    ema_s           = c.ewm(span=MACD_SLOW,   adjust=False).mean()
    df["macd"]      = ema_f - ema_s
    df["macd_sig"]  = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]

    # ADX H1
    df["adx"] = _compute_adx(h, l, c, ADX_PERIOD)

    # ORB (Opening Range 00:00-04:00 UTC)
    df["hour"] = df.index.hour
    df["date"] = df.index.date
    orb_hi, orb_lo = {}, {}
    for dt, grp in df.groupby("date"):
        rng = grp[(grp["hour"] >= ORB_HOUR_START) & (grp["hour"] < ORB_HOUR_END)]
        if len(rng) >= 2:
            orb_hi[dt] = rng["high"].max()
            orb_lo[dt] = rng["low"].min()
    df["orb_high"] = df["date"].map(orb_hi)
    df["orb_low"]  = df["date"].map(orb_lo)
    df["orb_mid"]  = (df["orb_high"] + df["orb_low"]) / 2

    # Supertrend H4 + Choppiness H4
    df_h4 = df.resample("4h").agg(
        open=("open","first"), high=("high","max"),
        low=("low","min"),  close=("close","last"), volume=("volume","sum")
    ).dropna()

    df_h4 = compute_supertrend(df_h4, ST_PERIOD, ST_MULT)
    df_h4["chop"] = compute_choppiness(df_h4, CHOP_PERIOD)

    # Mapear H4 a H1 via forward-fill
    df["h4_st_dir"] = df_h4["st_dir"].reindex(df.index, method="ffill").fillna(0).astype(int)
    df["h4_chop"]   = df_h4["chop"].reindex(df.index, method="ffill")

    return df


def _compute_adx(high, low, close, period):
    up   = high.diff()
    down = -low.diff()
    pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr   = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr  = tr.rolling(period).mean()
    pdi  = 100 * pdm.rolling(period).mean() / atr
    mdi  = 100 * mdm.rolling(period).mean() / atr
    dx   = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(period).mean()


# ── Carga de sentimiento ──────────────────────────────────────────────────────

def load_sentiment(symbol: str):
    """
    Carga el funding rate del par y el Fear & Greed (macro) del CSV local.
    Retorna (funding_rate_actual, fg_value_actual).
    El bot actualiza estos CSV cada 8h.
    """
    import os
    from config import funding_csv, FG_CSV

    funding = None
    fg      = None

    fund_path = funding_csv(symbol)
    if os.path.exists(fund_path):
        df_f = pd.read_csv(fund_path, parse_dates=["datetime"], index_col="datetime")
        df_f.sort_index(inplace=True)
        if not df_f.empty:
            funding = float(df_f["funding_rate"].iloc[-1])

    if os.path.exists(FG_CSV):
        df_g = pd.read_csv(FG_CSV, index_col=0)
        df_g.sort_index(inplace=True)
        if not df_g.empty:
            fg = float(df_g["fg_value"].iloc[-1])

    return funding, fg


# ── Logica de entrada ─────────────────────────────────────────────────────────

def check_entry(df: pd.DataFrame, symbol: str, cfg: dict | None = None,
                use_sentiment: bool = True):
    """
    Evalua la ultima vela cerrada H1 y retorna ('long'|'short'|None, regime).

    symbol: par operado (para cargar su funding rate).
    cfg:    config del par (adx_min, adx_choppy). Si None, usa defaults globales.

    Filtros en cascada:
      1. Ventana horaria activa (04:00-20:00 UTC)
      2. ORB valido y rango minimo
      3. Volatilidad normal (ATR < 1.8x promedio)
      4. Supertrend H4 define la direccion permitida
      5. Choppiness H4 define el regimen (ADX mas exigente en choppy)
      6. Momentum H1: EMA20>EMA50, MACD hist, ADX
      7. RSI en rango
      8. Sentimiento: funding rate del par + Fear & Greed macro
      9. En choppy/neutral: solo en direccion del Supertrend H4
    """
    from config import (ADX_MIN, ADX_CHOPPY_MIN, ATR_VOL_MULT,
                        RSI_LONG_MIN, RSI_LONG_MAX, RSI_SHORT_MIN, RSI_SHORT_MAX,
                        ORB_HOUR_END, ENTRY_HOUR_END, ORB_MIN_RANGE_PCT,
                        CHOP_TREND_MAX, CHOP_CHOPPY_MIN,
                        FUND_LONG_MIN, FUND_SHORT_MIN, FUND_SHORT_MAX,
                        FG_LONG_MIN, FG_SHORT_MIN, FG_SHORT_MAX)

    cfg = cfg or {}
    adx_min_req    = cfg.get("adx_min", ADX_MIN)
    adx_choppy_req = cfg.get("adx_choppy", ADX_CHOPPY_MIN)

    if len(df) < 100:
        return None, None

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    hour = curr.name.hour if hasattr(curr.name, "hour") else int(curr.get("hour", 0))

    # 1. Ventana horaria de entrada (ENTRY_HOUR_END configurable por instancia)
    if not (ORB_HOUR_END <= hour < ENTRY_HOUR_END):
        return None, None

    # 2. ORB valido
    if pd.isna(curr["orb_high"]) or pd.isna(curr["orb_low"]):
        return None, None
    if curr["orb_high"] - curr["orb_low"] < curr["close"] * ORB_MIN_RANGE_PCT:
        return None, None

    # 3. Volatilidad normal
    if not pd.isna(curr.get("atr_avg20")) and curr["atr"] > ATR_VOL_MULT * curr["atr_avg20"]:
        return None, None

    # 4. Regimen de mercado (Choppiness H4)
    chop   = curr.get("h4_chop", 50)
    st_dir = int(curr.get("h4_st_dir", 0))

    if chop < CHOP_TREND_MAX:
        regime = "trend"
    elif chop > CHOP_CHOPPY_MIN:
        regime = "choppy"
    else:
        regime = "neutral"

    # ADX mas exigente en mercado choppy (umbral por par)
    adx_req = adx_choppy_req if regime == "choppy" else adx_min_req

    # 5. Supertrend H4 (si no hay datos, no operar)
    if st_dir == 0:
        return None, None

    # 6. Momentum H1
    mom_up    = curr["ema20"] > curr["ema50"]
    mom_dn    = curr["ema20"] < curr["ema50"]
    macd_bull = curr["macd_hist"] > 0
    macd_bear = curr["macd_hist"] < 0
    adx_ok    = curr["adx"] >= adx_req

    # 7. ORB breakout
    orb_up = prev["close"] <= curr["orb_high"] and curr["close"] > curr["orb_high"]
    orb_dn = prev["close"] >= curr["orb_low"]  and curr["close"] < curr["orb_low"]

    # 8. Sentimiento (funding del par + F&G macro)
    # Brokers sin funding (MT5/ADN CFD) operan sin este filtro.
    if use_sentiment:
        funding, fg = load_sentiment(symbol)
        if funding is None or fg is None:
            return None, None   # sin datos de sentimiento, no operar
        long_ok_sent  = (funding >= FUND_LONG_MIN and fg >= FG_LONG_MIN)
        short_ok_sent = (FUND_SHORT_MIN <= funding <= FUND_SHORT_MAX
                         and FG_SHORT_MIN <= fg <= FG_SHORT_MAX)
    else:
        long_ok_sent = short_ok_sent = True

    # 9. En choppy/neutral: solo en direccion del Supertrend H4
    st_allows_long  = (regime == "trend") or (st_dir == 1)
    st_allows_short = (regime == "trend") or (st_dir == -1)

    # ── LONG ──────────────────────────────────────────────────────────────────
    if (st_dir == 1
            and long_ok_sent
            and orb_up
            and mom_up
            and macd_bull
            and adx_ok
            and RSI_LONG_MIN <= curr["rsi"] <= RSI_LONG_MAX
            and st_allows_long):
        return "long", regime

    # ── SHORT ─────────────────────────────────────────────────────────────────
    if (st_dir == -1
            and short_ok_sent
            and orb_dn
            and mom_dn
            and macd_bear
            and adx_ok
            and RSI_SHORT_MIN <= curr["rsi"] <= RSI_SHORT_MAX
            and st_allows_short):
        return "short", regime

    return None, None


# ── Sizing ────────────────────────────────────────────────────────────────────

def get_risk_pct(regime: str, dd_pct: float, cfg: dict) -> float:
    """
    Determina el riesgo por operacion segun el regimen, el DD actual y la
    config del par. El DD acumulado de la cuenta puede reducir aun mas el riesgo.
    """
    if   regime == "trend":   risk = cfg["risk_trend"]
    elif regime == "neutral": risk = cfg["risk_neutral"]
    else:                     risk = cfg["risk_choppy"]

    # Reduccion adicional por drawdown de la cuenta (umbrales por par)
    if   dd_pct >= cfg["dd_hi"]: risk = min(risk, cfg["dd_hi_risk"])
    elif dd_pct >= cfg["dd_lo"]: risk = min(risk, cfg["dd_lo_risk"])

    return risk


def calc_lot_size(capital: float, atr: float, risk_pct: float) -> float:
    """
    Calcula el lotaje para arriesgar exactamente risk_pct del capital.
    BTCUSD: 1 lote = 1 BTC. lot = (capital * risk) / (atr * sl_mult)
    """
    from config import ATR_SL_MULT
    sl_dist = atr * ATR_SL_MULT
    lot     = (capital * risk_pct) / sl_dist
    return max(0.001, round(lot, 4))


def calc_sl_tp(position_type: str, entry: float, atr: float):
    """Calcula SL y TP fijos basados en ATR."""
    from config import ATR_SL_MULT, TP_RR
    sl_dist = atr * ATR_SL_MULT
    tp_dist = sl_dist * TP_RR
    if position_type == "long":
        return entry - sl_dist, entry + tp_dist
    return entry + sl_dist, entry - tp_dist


def calc_trailing_sl(position_type: str, ema20: float, atr: float) -> float:
    """Trailing stop = EMA20 +/- 1x ATR."""
    from config import ATR_TRAIL_MULT
    if position_type == "long":
        return ema20 - ATR_TRAIL_MULT * atr
    return ema20 + ATR_TRAIL_MULT * atr
