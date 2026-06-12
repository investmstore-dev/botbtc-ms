"""
Bot BTC -- Mining Store
Estrategia: ORB + MACD/RSI + Supertrend H4 + Choppiness Index | BTCUSD H1
Cuenta: Crypto Fund Trader | v5b
Broker: Bybit API directa (sin MT5)
"""
import time
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("botbtc.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

import os
import config
import bybit_connector as bybit
import state_manager as sm
from strategy import (compute_indicators, check_entry,
                      get_risk_pct, calc_lot_size, calc_sl_tp, calc_trailing_sl)

INITIAL_BALANCE        = 10_000
LOOP_INTERVAL          = 60
SENTIMENT_REFRESH_SECS = 8 * 3600   # refrescar funding + F&G cada 8h
active_trade           = None
peak_equity            = INITIAL_BALANCE
_last_sentiment_update = 0.0
_last_status_log       = 0.0
STATUS_LOG_SECS        = 30 * 60   # resumen "sin senal" cada 30 min


def _refresh_sentiment():
    """Descarga funding rate y Fear&Greed si los datos tienen mas de 8h."""
    global _last_sentiment_update
    if time.time() - _last_sentiment_update < SENTIMENT_REFRESH_SECS:
        return

    logger.info("Actualizando datos de sentimiento (funding rate + F&G)...")
    try:
        import requests
        from datetime import datetime, timezone as tz

        # ── Funding rate: ultimas 200 entradas (cubre 66 dias) ───────────────
        end_ms = int(datetime.now(tz.utc).timestamp() * 1000)
        r = requests.get(
            "https://api.bybit.com/v5/market/funding/history",
            params={"category": "linear", "symbol": "BTCUSDT",
                    "endTime": end_ms, "limit": 200},
            timeout=10
        )
        rows = r.json()["result"]["list"]
        import pandas as pd
        new_fund = pd.DataFrame([{
            "datetime": datetime.fromtimestamp(int(x["fundingRateTimestamp"]) / 1000,
                                               tz=tz.utc).replace(tzinfo=None),
            "funding_rate": float(x["fundingRate"])
        } for x in rows])
        new_fund.set_index("datetime", inplace=True)
        new_fund.sort_index(inplace=True)

        # Fusionar con CSV existente
        csv_path = config.FUNDING_CSV
        if os.path.exists(csv_path):
            old = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
            new_fund = pd.concat([old, new_fund])
            new_fund = new_fund[~new_fund.index.duplicated(keep="last")]
            new_fund.sort_index(inplace=True)
        new_fund.to_csv(csv_path)

        # ── Fear & Greed ──────────────────────────────────────────────────────
        r2 = requests.get(
            "https://api.alternative.me/fng/?limit=30&format=json", timeout=10
        )
        fg_rows = pd.DataFrame([{
            "date": datetime.fromtimestamp(int(d["timestamp"])).date(),
            "fg_value": int(d["value"]),
            "fg_class": d["value_classification"]
        } for d in r2.json()["data"]])
        fg_rows.set_index("date", inplace=True)
        fg_rows.sort_index(inplace=True)

        fg_path = config.FG_CSV
        if os.path.exists(fg_path):
            old_fg = pd.read_csv(fg_path, index_col=0)
            old_fg.index = pd.to_datetime(old_fg.index).date
            fg_rows = pd.concat([old_fg, fg_rows])
            fg_rows = fg_rows[~fg_rows.index.duplicated(keep="last")]
            fg_rows.sort_index(inplace=True)
        fg_rows.index.name = "date"
        fg_rows.to_csv(fg_path)

        _last_sentiment_update = time.time()
        logger.info("Sentimiento actualizado: funding=%d entradas  F&G=%d dias",
                    len(new_fund), len(fg_rows))
    except Exception as e:
        logger.warning("Error actualizando sentimiento: %s", e)


def run():
    global active_trade, peak_equity

    logger.info("=" * 60)
    logger.info("  BOT BTC -- Mining Store | Crypto Fund Trader v5b")
    logger.info("  Estrategia: ORB + Supertrend H4 + Choppiness + Sentimiento")
    logger.info("  RISK: TREND=1.8%% | NEUTRAL=1.0%% | CHOPPY=0.5%%")
    logger.info("  Broker: Bybit %s", "DEMO" if bybit.IS_DEMO else "LIVE")
    logger.info("=" * 60)

    # Verificar conexion con Bybit
    account = bybit.get_account()
    if not account:
        logger.error("No se pudo conectar con Bybit. Verificar .env y API Key.")
        return

    logger.info("Cuenta: %s  balance=$%.2f  equity=$%.2f",
                account.get("login"), account.get("balance", 0), account.get("equity", 0))

    peak_equity = account.get("equity", INITIAL_BALANCE)

    # Primera carga de sentimiento al arrancar
    _refresh_sentiment()

    while True:
        try:
            _refresh_sentiment()   # no-op si los datos tienen menos de 8h
            _cycle()
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario.")
            break
        except Exception as e:
            logger.exception("Error en ciclo: %s", e)

        time.sleep(LOOP_INTERVAL)


def _cycle():
    global active_trade, peak_equity

    account = bybit.get_account()
    if not account:
        logger.warning("Sin respuesta de Bybit API. Reintentando en el proximo ciclo.")
        return

    balance = account.get("balance", INITIAL_BALANCE)
    equity  = account.get("equity",  balance)
    peak_equity = max(peak_equity, equity)

    sm.append_equity(equity, balance)

    cft    = sm.calc_cft_status(account, INITIAL_BALANCE)
    dd_pct = abs((equity - peak_equity) / peak_equity) if peak_equity > 0 else 0.0

    # Guardas CFT
    if cft["dd_violated"]:
        logger.error("DRAWDOWN MAXIMO VIOLADO (%.2f%%). Cerrando posiciones.", cft["max_dd_pct"])
        _close_all()
        sm.save_state(account, "DD_VIOLATED", active_trade, cft)
        return

    if cft["daily_dd_violated"]:
        logger.warning("Drawdown diario violado (%.2f%%). Pausando hoy.", cft["daily_dd_pct"])
        _close_all()
        sm.save_state(account, "DAILY_DD_VIOLATED", active_trade, cft)
        return

    if cft["target_reached"]:
        logger.info("OBJETIVO ALCANZADO (%.2f%%)! Solicitar fondeo CFT.", cft["profit_pct"])
        _close_all()
        sm.save_state(account, "TARGET_REACHED", active_trade, cft)
        return

    # Velas H1
    df = bybit.get_candles(config.SYMBOL, config.TIMEFRAME, count=400)
    if df is None or len(df) < 150:
        logger.warning("Datos insuficientes (%d velas).", len(df) if df is not None else 0)
        return

    df = compute_indicators(df)
    curr = df.iloc[-1]

    # Posicion abierta
    open_positions = bybit.get_open_positions(config.SYMBOL)

    if open_positions:
        pos      = open_positions[0]
        pos_type = pos.get("type")

        # Trailing stop
        new_sl     = calc_trailing_sl(pos_type, curr["ema20"], curr["atr"])
        current_sl = pos.get("sl", 0)

        if pos_type == "long"  and new_sl > current_sl:
            bybit.modify_sl(config.SYMBOL, pos_type, new_sl)
            logger.info("Trailing SL LONG: %.2f", new_sl)
        elif pos_type == "short" and new_sl < current_sl:
            bybit.modify_sl(config.SYMBOL, pos_type, new_sl)
            logger.info("Trailing SL SHORT: %.2f", new_sl)

        # Cierre EOD
        hour = datetime.now(timezone.utc).hour
        if hour >= config.ORB_HOUR_CLOSE:
            logger.info("Cierre EOD forzado (hora UTC: %d)", hour)
            bybit.close_position(pos)
            if active_trade:
                sm.append_trade({**active_trade, "exit": curr["close"], "exit_reason": "EOD"})
            active_trade = None

        sm.save_state(account, "holding", active_trade, cft)
        return

    # Buscar entrada
    signal, regime = check_entry(df)

    if signal and not open_positions:
        risk_pct = get_risk_pct(regime, dd_pct)
        sl, tp   = calc_sl_tp(signal, curr["close"], curr["atr"])
        lot      = calc_lot_size(balance, curr["atr"], risk_pct)
        chop_val = curr.get("h4_chop", 0)
        st_dir   = curr.get("h4_st_dir", 0)

        logger.info("SENAL: %s | Regimen: %s (CHOP=%.0f ST=%+d) | Risk=%.1f%%",
                    signal.upper(), regime, chop_val, st_dir, risk_pct * 100)

        result = bybit.open_order(
            symbol=config.SYMBOL,
            order_type=signal,
            lot=lot,
            sl=sl,
            tp=tp,
            comment=f"BotBTC_{regime[:3].upper()}"
        )

        if "error" not in result:
            active_trade = {
                "type":       signal,
                "entry":      curr["close"],
                "sl":         sl,
                "tp":         tp,
                "lot":        lot,
                "ticket":     result.get("ticket"),
                "regime":     regime,
                "risk_pct":   risk_pct,
                "h4_chop":    round(float(chop_val), 1),
                "h4_st_dir":  int(st_dir),
                "entry_time": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("ORDEN ABIERTA: %s %s  entry=%.2f  sl=%.2f  tp=%.2f  lot=%.4f",
                        signal.upper(), config.SYMBOL, curr["close"], sl, tp, lot)
        else:
            logger.error("Error al abrir orden: %s", result["error"])
    else:
        global _last_status_log
        if time.time() - _last_status_log >= STATUS_LOG_SECS:
            _last_status_log = time.time()
            logger.info("Sin senal | RSI=%.1f  MACD=%.1f  ADX=%.1f  CHOP=%.0f  ST=%+d  DD=%.1f%%  equity=$%.2f",
                        curr.get("rsi", 0), curr.get("macd_hist", 0), curr.get("adx", 0),
                        curr.get("h4_chop", 0), curr.get("h4_st_dir", 0), dd_pct * 100, equity)

    sm.save_state(account, signal or "no_signal", active_trade, cft)


def _close_all():
    global active_trade
    for pos in bybit.get_open_positions(config.SYMBOL):
        bybit.close_position(pos)
        logger.info("Posicion cerrada forzada: %s size=%.4f", pos.get("type"), pos.get("size", 0))
    active_trade = None


if __name__ == "__main__":
    run()
