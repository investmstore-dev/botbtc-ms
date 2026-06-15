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
from utils import bybit_connector as bybit
from utils import state_manager as sm
from utils import notifier
from logic.strategy import (compute_indicators, check_entry,
                            get_risk_pct, calc_lot_size, calc_sl_tp, calc_trailing_sl)

INITIAL_BALANCE        = 10_000
LOOP_INTERVAL          = 60
SENTIMENT_REFRESH_SECS = 8 * 3600   # refrescar funding + F&G cada 8h
active_trade           = None      # modo SINGLE: 1 trade a la vez (incluye "symbol")
peak_equity            = INITIAL_BALANCE
_last_sentiment_update = 0.0
_last_status_log       = 0.0
STATUS_LOG_SECS        = 30 * 60   # resumen "sin senal" cada 30 min
_last_report_date      = None      # fecha del ultimo reporte diario enviado
_trades_today          = []        # trades cerrados hoy (para el reporte)
_regime_by_symbol      = {}        # ultimo regimen conocido por par (para el reporte)


def _refresh_sentiment():
    """Descarga funding rate y Fear&Greed si los datos tienen mas de 8h."""
    global _last_sentiment_update
    if time.time() - _last_sentiment_update < SENTIMENT_REFRESH_SECS:
        return

    logger.info("Actualizando datos de sentimiento (funding rate + F&G)...")
    try:
        import requests
        import pandas as pd
        from datetime import datetime, timezone as tz

        end_ms = int(datetime.now(tz.utc).timestamp() * 1000)

        # ── Funding rate POR PAR: ultimas 200 entradas (cubre 66 dias) ───────
        fund_counts = {}
        for sym in config.SYMBOLS:
            r = requests.get(
                "https://api.bybit.com/v5/market/funding/history",
                params={"category": "linear", "symbol": sym,
                        "endTime": end_ms, "limit": 200},
                timeout=10
            )
            rows = r.json()["result"]["list"]
            new_fund = pd.DataFrame([{
                "datetime": datetime.fromtimestamp(int(x["fundingRateTimestamp"]) / 1000,
                                                   tz=tz.utc).replace(tzinfo=None),
                "funding_rate": float(x["fundingRate"])
            } for x in rows])
            new_fund.set_index("datetime", inplace=True)
            new_fund.sort_index(inplace=True)

            csv_path = config.funding_csv(sym)
            if os.path.exists(csv_path):
                old = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
                new_fund = pd.concat([old, new_fund])
                new_fund = new_fund[~new_fund.index.duplicated(keep="last")]
                new_fund.sort_index(inplace=True)
            new_fund.to_csv(csv_path)
            fund_counts[sym] = len(new_fund)

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
        fund_summary = " ".join(f"{s}={n}" for s, n in fund_counts.items())
        logger.info("Sentimiento actualizado: funding[%s]  F&G=%d dias",
                    fund_summary, len(fg_rows))
    except Exception as e:
        logger.warning("Error actualizando sentimiento: %s", e)


def run():
    global active_trade, peak_equity

    logger.info("=" * 60)
    logger.info("  BOT Mining Store | Crypto Fund Trader v6 multi-par")
    logger.info("  Estrategia: ORB + Supertrend H4 + Choppiness + Sentimiento")
    logger.info("  Pares: %s | Modo: %s", ", ".join(config.SYMBOLS), config.RISK_MODE.upper())
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


def _handle_closed_trade(balance: float, reason: str):
    """Registra y notifica el cierre del trade activo usando el PnL real de Bybit."""
    global active_trade
    if not active_trade:
        return

    symbol = active_trade.get("symbol", config.SYMBOLS[0])
    exit_price, pnl = 0.0, 0.0
    closed = bybit.get_closed_pnl(symbol, limit=1)
    if closed:
        exit_price = closed[0]["exit"]
        pnl        = closed[0]["pnl"]

    trade_record = {**active_trade, "exit": exit_price, "pnl": pnl,
                    "exit_reason": reason}
    sm.append_trade(trade_record)
    _trades_today.append(trade_record)
    notifier.notify_trade_close(active_trade, exit_price, pnl, balance, reason)
    logger.info("Trade cerrado %s (%s): exit=%.6f pnl=%+.2f", symbol, reason, exit_price, pnl)
    active_trade = None


_REPORT_MARKER = os.path.join(config.DATA_DIR, "last_report.txt")


def _maybe_daily_report(account: dict, cft: dict):
    """Envía el reporte diario una vez al dia, despues del cierre de sesion (20:00 UTC).
    La fecha del ultimo reporte se persiste en disco para no duplicar tras reinicios."""
    global _last_report_date, _trades_today
    now = datetime.now(timezone.utc)
    if now.hour < config.ORB_HOUR_CLOSE:
        return
    if _last_report_date is None and os.path.exists(_REPORT_MARKER):
        with open(_REPORT_MARKER) as f:
            _last_report_date = f.read().strip()
    if _last_report_date == str(now.date()):
        return
    _last_report_date = str(now.date())
    with open(_REPORT_MARKER, "w") as f:
        f.write(_last_report_date)
    notifier.notify_daily_report(account, cft, _trades_today, _regime_by_symbol)
    logger.info("Reporte diario enviado (%d trades hoy)", len(_trades_today))
    _trades_today = []


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
        notifier.send(f"🚨 <b>ALERTA: DRAWDOWN MÁXIMO VIOLADO</b>\n"
                      f"DD: {cft['max_dd_pct']:.2f}% — cerrando todas las posiciones.")
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
        notifier.send(f"🏆 <b>¡OBJETIVO CFT ALCANZADO!</b>\n"
                      f"Profit: +{cft['profit_pct']:.2f}% — solicitar siguiente fase/fondeo.")
        _close_all()
        sm.save_state(account, "TARGET_REACHED", active_trade, cft)
        return

    # Calcular indicadores de cada par y detectar posicion abierta (cualquiera)
    global _regime_by_symbol
    dfs, open_sym, open_pos = {}, None, None
    for sym in config.SYMBOLS:
        df = bybit.get_candles(sym, config.TIMEFRAME, count=400)
        if df is None or len(df) < 150:
            logger.warning("Datos insuficientes %s (%d velas).", sym,
                           len(df) if df is not None else 0)
            continue
        df = compute_indicators(df)
        dfs[sym] = df
        curr = df.iloc[-1]
        _regime_by_symbol[sym] = {
            "regime": ("TREND" if curr.get("h4_chop", 50) < config.CHOP_TREND_MAX
                       else "CHOPPY" if curr.get("h4_chop", 50) > config.CHOP_CHOPPY_MIN
                       else "NEUTRAL"),
            "chop":   float(curr.get("h4_chop", 0)),
            "st_dir": int(curr.get("h4_st_dir", 0)),
        }
        positions = bybit.get_open_positions(sym)
        if positions:
            open_sym, open_pos = sym, positions[0]

    if not dfs:
        return

    # Detectar cierre por SL/TP (teniamos trade activo pero Bybit ya no lo muestra)
    if active_trade and open_sym is None:
        _handle_closed_trade(balance, "SL/TP alcanzado")

    _maybe_daily_report(account, cft)

    # ── Hay una posicion abierta: gestionarla (trailing + EOD) ───────────────
    if open_sym is not None:
        curr     = dfs[open_sym].iloc[-1]
        pos_type = open_pos.get("type")

        new_sl     = calc_trailing_sl(pos_type, curr["ema20"], curr["atr"])
        current_sl = open_pos.get("sl", 0)
        if pos_type == "long" and new_sl > current_sl:
            bybit.modify_sl(open_sym, pos_type, new_sl)
            logger.info("Trailing SL LONG %s: %.6f", open_sym, new_sl)
        elif pos_type == "short" and new_sl < current_sl:
            bybit.modify_sl(open_sym, pos_type, new_sl)
            logger.info("Trailing SL SHORT %s: %.6f", open_sym, new_sl)

        hour = datetime.now(timezone.utc).hour
        if hour >= config.ORB_HOUR_CLOSE:
            logger.info("Cierre EOD forzado %s (hora UTC: %d)", open_sym, hour)
            bybit.close_position(open_pos)
            time.sleep(2)
            _handle_closed_trade(balance, "Cierre EOD (20:00 UTC)")

        sm.save_state(account, "holding", active_trade, cft)
        return

    # ── Sin posiciones (modo SINGLE): buscar entrada en orden de prioridad ───
    for sym in config.SYMBOLS:
        if sym not in dfs:
            continue
        df  = dfs[sym]
        cfg = config.SYMBOL_CONFIGS.get(sym, {})
        signal, regime = check_entry(df, sym, cfg)
        if not signal:
            continue

        curr     = df.iloc[-1]
        risk_pct = get_risk_pct(regime, dd_pct, cfg)
        sl, tp   = calc_sl_tp(signal, curr["close"], curr["atr"])
        lot      = calc_lot_size(balance, curr["atr"], risk_pct)
        chop_val = curr.get("h4_chop", 0)
        st_dir   = curr.get("h4_st_dir", 0)

        logger.info("SENAL %s: %s | Regimen: %s (CHOP=%.0f ST=%+d) | Risk=%.1f%%",
                    sym, signal.upper(), regime, chop_val, st_dir, risk_pct * 100)

        result = bybit.open_order(symbol=sym, order_type=signal, lot=lot, sl=sl, tp=tp,
                                  comment=f"Bot_{sym[:3]}_{regime[:3].upper()}")

        if "error" not in result:
            active_trade = {
                "symbol":     sym,
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
            logger.info("ORDEN ABIERTA: %s %s  entry=%.6f  sl=%.6f  tp=%.6f  lot=%s",
                        signal.upper(), sym, curr["close"], sl, tp, lot)
            notifier.notify_trade_open(active_trade)
        else:
            logger.error("Error al abrir orden %s: %s", sym, result["error"])
        sm.save_state(account, signal, active_trade, cft)
        return   # modo SINGLE: una sola entrada por ciclo

    # ── Sin senal en ningun par ──────────────────────────────────────────────
    global _last_status_log
    if time.time() - _last_status_log >= STATUS_LOG_SECS:
        _last_status_log = time.time()
        parts = []
        for sym in config.SYMBOLS:
            if sym in dfs:
                c = dfs[sym].iloc[-1]
                parts.append(f"{sym}[RSI={c.get('rsi',0):.0f} ADX={c.get('adx',0):.0f} "
                             f"CHOP={c.get('h4_chop',0):.0f} ST={int(c.get('h4_st_dir',0)):+d}]")
        logger.info("Sin senal | %s | DD=%.1f%% equity=$%.2f",
                    " ".join(parts), dd_pct * 100, equity)
    sm.save_state(account, "no_signal", active_trade, cft)


def _close_all():
    global active_trade
    for sym in config.SYMBOLS:
        for pos in bybit.get_open_positions(sym):
            bybit.close_position(pos)
            logger.info("Posicion cerrada forzada %s: %s size=%.6f",
                        sym, pos.get("type"), pos.get("size", 0))
    active_trade = None


if __name__ == "__main__":
    run()
