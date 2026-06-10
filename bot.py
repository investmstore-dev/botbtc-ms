"""
Bot BTC -- Mining Store
Estrategia: ORB + MACD/RSI | BTCUSD H1
Cuenta: Crypto Fund Trader
"""
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("botbtc.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

import config
import mt5_connector as mt5
import state_manager as sm
from strategy import compute_indicators, check_entry, calc_lot_size, calc_sl_tp, calc_trailing_sl

INITIAL_BALANCE = 10_000
LOOP_INTERVAL   = 60          # segundos entre ciclos
active_trade    = None


def run():
    global active_trade

    logger.info("=" * 55)
    logger.info("  BOT BTC -- Mining Store | Crypto Fund Trader")
    logger.info("  Estrategia: ORB + MACD/RSI | BTCUSD H1")
    logger.info("=" * 55)

    if not mt5.connect():
        logger.error("No se pudo conectar al EA Bridge. Abortando.")
        return

    account = mt5.get_account()
    logger.info("Cuenta: login=%s balance=$%.2f", account.get("login"), account.get("balance", 0))

    while True:
        try:
            _cycle()
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario.")
            break
        except Exception as e:
            logger.exception("Error en ciclo: %s", e)

        time.sleep(LOOP_INTERVAL)


def _cycle():
    global active_trade

    account = mt5.get_account()
    if not account:
        logger.warning("Sin datos de cuenta — MT5 EA no responde.")
        return

    balance = account.get("balance", INITIAL_BALANCE)
    equity  = account.get("equity",  balance)
    sm.append_equity(equity, balance)

    cft = sm.calc_cft_status(account, INITIAL_BALANCE)

    # Guardia: si se viola drawdown, cerrar posicion y pausar
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
        logger.info("OBJETIVO ALCANZADO (%.2f%%)! Solicitar fondeo.", cft["profit_pct"])
        _close_all()
        sm.save_state(account, "TARGET_REACHED", active_trade, cft)
        return

    # Obtener velas
    df = mt5.get_candles(config.SYMBOL, config.TIMEFRAME, count=300)
    if df is None or len(df) < 220:
        logger.warning("Datos insuficientes (%d velas). Esperando.", len(df) if df is not None else 0)
        return

    df = compute_indicators(df)
    curr = df.iloc[-1]

    # Gestion de posicion abierta
    open_positions = mt5.get_open_positions(config.SYMBOL)

    if open_positions:
        pos = open_positions[0]
        ticket      = pos.get("ticket")
        pos_type    = pos.get("type")

        # Trailing stop
        new_sl = calc_trailing_sl(pos_type, curr["ema20"], curr["atr"])
        current_sl = pos.get("sl", 0)

        if pos_type == "long"  and new_sl > current_sl:
            mt5.modify_sl(ticket, new_sl)
            logger.info("Trailing SL actualizado LONG: %.2f", new_sl)
        elif pos_type == "short" and new_sl < current_sl:
            mt5.modify_sl(ticket, new_sl)
            logger.info("Trailing SL actualizado SHORT: %.2f", new_sl)

        # Cierre forzado EOD
        hour = datetime.utcnow().hour
        if hour >= config.ORB_HOUR_CLOSE:
            logger.info("Cierre EOD forzado (hora UTC: %d)", hour)
            mt5.close_position(pos)
            if active_trade:
                sm.append_trade({**active_trade, "exit": curr["close"], "exit_reason": "EOD"})
            active_trade = None

        sm.save_state(account, "holding", active_trade, cft)
        return

    # Buscar entrada
    signal = check_entry(df)

    if signal and len(open_positions) == 0:
        sl, tp   = calc_sl_tp(signal, curr["close"], curr["atr"])
        lot      = calc_lot_size(balance, curr["atr"], config.RISK_PCT)

        result = mt5.open_order(
            symbol=config.SYMBOL,
            order_type=signal,
            lot=lot,
            sl=sl,
            tp=tp,
            comment="BotBTC_ORB"
        )

        if "error" not in result:
            active_trade = {
                "type":   signal,
                "entry":  curr["close"],
                "sl":     sl,
                "tp":     tp,
                "lot":    lot,
                "ticket": result.get("ticket"),
                "entry_time": datetime.utcnow().isoformat(),
            }
            logger.info("ORDEN ABIERTA: %s BTCUSD entry=%.2f sl=%.2f tp=%.2f lot=%.3f",
                        signal.upper(), curr["close"], sl, tp, lot)
        else:
            logger.error("Error al abrir orden: %s", result["error"])
    else:
        logger.debug("Sin señal. RSI=%.1f MACD_hist=%.1f ADX=%.1f",
                     curr.get("rsi", 0), curr.get("macd_hist", 0), curr.get("adx", 0))

    sm.save_state(account, signal or "no_signal", active_trade, cft)


def _close_all():
    global active_trade
    positions = mt5.get_open_positions(config.SYMBOL)
    for pos in positions:
        mt5.close_position(pos)
        logger.info("Posicion cerrada forzada: ticket=%s", pos.get("ticket"))
    active_trade = None


if __name__ == "__main__":
    run()
