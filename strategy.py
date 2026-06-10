import pandas as pd
import numpy as np


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula indicadores sobre el DataFrame de velas H1 para BTCUSD."""
    from config import (EMA_FAST, EMA_SLOW, EMA_TREND, MACD_FAST, MACD_SLOW,
                        MACD_SIGNAL, RSI_PERIOD, ATR_PERIOD, ADX_PERIOD,
                        ORB_CANDLES, ORB_HOUR_START, ORB_HOUR_END)

    c = df["close"]
    h = df["high"]
    l = df["low"]

    # --- EMAs ---
    df["ema20"]  = c.ewm(span=EMA_FAST,  adjust=False).mean()
    df["ema50"]  = c.ewm(span=EMA_SLOW,  adjust=False).mean()
    df["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()

    # --- ATR ---
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    # --- RSI ---
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(RSI_PERIOD).mean()
    loss  = (-delta.clip(upper=0)).rolling(RSI_PERIOD).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    # --- MACD ---
    ema_fast        = c.ewm(span=MACD_FAST,   adjust=False).mean()
    ema_slow        = c.ewm(span=MACD_SLOW,   adjust=False).mean()
    df["macd"]      = ema_fast - ema_slow
    df["macd_sig"]  = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]

    # --- ADX ---
    df["adx"] = _compute_adx(h, l, c, ADX_PERIOD)

    # --- Opening Range Breakout (ORB) ---
    # Para cada vela, calcula el max/min del rango definido en UTC 00:00-04:00
    # Se propaga hacia adelante durante el resto del dia
    df["hour"] = df.index.hour
    df["date"] = df.index.date

    orb_high = {}
    orb_low  = {}

    for date, group in df.groupby("date"):
        range_candles = group[
            (group["hour"] >= ORB_HOUR_START) & (group["hour"] < ORB_HOUR_END)
        ]
        if len(range_candles) >= 2:
            orb_high[date] = range_candles["high"].max()
            orb_low[date]  = range_candles["low"].min()

    df["orb_high"] = df["date"].map(orb_high)
    df["orb_low"]  = df["date"].map(orb_low)
    df["orb_mid"]  = (df["orb_high"] + df["orb_low"]) / 2

    return df


def _compute_adx(high, low, close, period):
    up   = high.diff()
    down = -low.diff()

    plus_dm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr      = tr.rolling(period).mean()
    plus_di  = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()


def check_entry(df: pd.DataFrame):
    """
    Estrategia ORB + MACD/RSI para BTCUSD H1.

    LONG:
      - Precio cierra por encima de orb_high (breakout alcista)
      - EMA50 > EMA200 (tendencia diaria alcista) O EMA20 > EMA50 (momentum)
      - MACD hist positivo (momentum confirmado)
      - RSI entre 40-70 (no sobrecomprado)
      - ADX >= 20 (tendencia con fuerza)
      - Hora UTC >= 04:00 y <= 20:00 (no operar overnight ni en rango)

    SHORT: espejo inverso
    """
    from config import (ADX_MIN, RSI_LONG_MIN, RSI_LONG_MAX,
                        RSI_SHORT_MIN, RSI_SHORT_MAX,
                        ORB_HOUR_END, ORB_HOUR_CLOSE)

    if len(df) < 210:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    hour = curr.name.hour if hasattr(curr.name, 'hour') else curr["hour"]

    # Solo operar en ventana activa
    if not (ORB_HOUR_END <= hour < ORB_HOUR_CLOSE):
        return None

    # ORB valido
    if pd.isna(curr["orb_high"]) or pd.isna(curr["orb_low"]):
        return None

    adx_ok     = curr["adx"] >= ADX_MIN
    trend_up   = curr["ema50"] > curr["ema200"]
    trend_dn   = curr["ema50"] < curr["ema200"]
    mom_up     = curr["ema20"] > curr["ema50"]
    mom_dn     = curr["ema20"] < curr["ema50"]
    macd_bull  = curr["macd_hist"] > 0
    macd_bear  = curr["macd_hist"] < 0
    orb_break_up   = prev["close"] <= curr["orb_high"] and curr["close"] > curr["orb_high"]
    orb_break_dn   = prev["close"] >= curr["orb_low"]  and curr["close"] < curr["orb_low"]

    # LONG
    if (orb_break_up
            and (trend_up or mom_up)
            and macd_bull
            and adx_ok
            and RSI_LONG_MIN <= curr["rsi"] <= RSI_LONG_MAX):
        return "long"

    # SHORT
    if (orb_break_dn
            and (trend_dn or mom_dn)
            and macd_bear
            and adx_ok
            and RSI_SHORT_MIN <= curr["rsi"] <= RSI_SHORT_MAX):
        return "short"

    return None


def calc_lot_size(capital: float, atr: float, risk_pct: float) -> float:
    """
    Calcula el lotaje para arriesgar exactamente risk_pct del capital.
    BTCUSD: 1 lote = 1 BTC. lot = (capital * risk) / (atr_sl * 1)
    """
    from config import ATR_SL_MULT
    risk_usd  = capital * risk_pct
    sl_points = atr * ATR_SL_MULT
    lot = risk_usd / sl_points
    lot = max(0.001, round(lot, 3))   # min 0.001 BTC
    return lot


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
