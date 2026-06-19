"""
Bot BTC -- Mining Store
Estrategia: ORB + MACD/RSI + Supertrend H4 + Choppiness Index | BTCUSD H1
Cuenta: Crypto Fund Trader | v5b
Broker: Bybit API directa (sin MT5)
"""
import os
import time
import logging
import threading
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.environ.get("MS_LOG_FILE", "botbtc.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

import os
import config
from utils import account_manager
from utils import state_manager as sm
from utils import notifier
from logic.strategy import (compute_indicators, check_entry,
                            get_risk_pct, calc_lot_size, calc_sl_tp, calc_trailing_sl)

INITIAL_BALANCE        = 10_000
LOOP_INTERVAL          = 60
SENTIMENT_REFRESH_SECS = 8 * 3600   # refrescar funding + F&G cada 8h

# ── Estado de la cuenta/broker activos (se setean en run()) ───────────────────
broker        = None    # instancia Broker (BybitBroker / MT5Broker)
SYMBOLS       = []      # simbolos de la cuenta activa
USE_SENTIMENT = True    # False si el broker no tiene funding (MT5/ADN)
ACCOUNT       = None    # dict de la cuenta activa
PROP_RULES    = True    # True: reglas prop (stop +8%/-10%). False: libre/compounding
MAX_LOSS_PCT  = 0.50    # tope de seguridad en modo libre (cierra y para)

active_trade           = None      # modo SINGLE: 1 trade a la vez (incluye "symbol")
peak_equity            = INITIAL_BALANCE

# Control de hilo (para correr en segundo plano dentro del .exe)
_stop_event    = threading.Event()
_restart_event = threading.Event()


def stop():
    """Detiene el loop del bot."""
    _stop_event.set()


def request_restart():
    """Pide reinicializar la cuenta/broker (tras cambiar la cuenta activa)."""
    _restart_event.set()


def is_running() -> bool:
    return not _stop_event.is_set() and broker is not None
_last_sentiment_update = 0.0
_last_status_log       = 0.0
STATUS_LOG_SECS        = 30 * 60   # resumen "sin senal" cada 30 min
_last_report_date      = None      # fecha del ultimo reporte diario enviado
_trades_today          = []        # trades cerrados hoy (para el reporte)
_regime_by_symbol      = {}        # ultimo regimen conocido por par (para el reporte)


def _refresh_sentiment():
    """Descarga funding rate y Fear&Greed si los datos tienen mas de 8h."""
    global _last_sentiment_update
    if not USE_SENTIMENT:
        return   # broker sin funding (MT5/ADN): la estrategia opera sin sentimiento
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
        for sym in SYMBOLS:
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


def _init_account() -> bool:
    """Carga la cuenta activa y construye el broker. Retorna True si quedo listo."""
    global active_trade, peak_equity, broker, SYMBOLS, USE_SENTIMENT, ACCOUNT, INITIAL_BALANCE
    global PROP_RULES, MAX_LOSS_PCT

    ACCOUNT = account_manager.get_active_account()
    if not ACCOUNT:
        return False

    broker = account_manager.get_active_broker()
    if not broker:
        logger.error("No se pudo construir el broker de la cuenta activa.")
        return False

    SYMBOLS = ACCOUNT.get("symbols", [])
    # Sentimiento: override por cuenta; si no se especifica, depende del broker
    USE_SENTIMENT = ACCOUNT.get("use_sentiment", broker.has_funding())
    PROP_RULES = ACCOUNT.get("prop_rules", True)
    MAX_LOSS_PCT = ACCOUNT.get("max_loss_pct", 0.50)

    # Apalancamiento (cuentas Bybit personales: x10). No-op en MT5.
    lev = ACCOUNT.get("leverage")
    if lev:
        for s in SYMBOLS:
            broker.set_leverage(s, int(lev))

    account = broker.get_account()
    if not account:
        logger.error("No se pudo conectar con el broker. Verificar credenciales.")
        broker = None
        return False

    # Balance inicial REAL de la cuenta (ej. $500 ADN, $10k CFT) — no hardcode.
    stored = ACCOUNT.get("initial_balance")
    if stored:
        INITIAL_BALANCE = stored
    else:
        INITIAL_BALANCE = account.get("balance", 10_000)
        account_manager.set_field(ACCOUNT.get("id", ""), "initial_balance", INITIAL_BALANCE)

    logger.info("=" * 60)
    logger.info("  BOT Mining Store | v6 multi-broker")
    logger.info("  Cuenta: %s (%s) | Broker: %s %s",
                ACCOUNT.get("name", ACCOUNT.get("id")), ACCOUNT.get("type"),
                broker.name.upper(), "DEMO" if broker.is_demo else "LIVE")
    logger.info("  Pares: %s | Modo: %s | Sentimiento: %s",
                ", ".join(SYMBOLS), config.RISK_MODE.upper(),
                "ON" if USE_SENTIMENT else "OFF")
    logger.info("  balance=$%.2f  equity=$%.2f",
                account.get("balance", 0), account.get("equity", 0))
    logger.info("=" * 60)

    active_trade = None
    peak_equity = account.get("equity", INITIAL_BALANCE)
    return True


def run():
    """Loop principal. Reinicializa la cuenta si se pide restart; espera si no hay
    cuenta configurada (para que el usuario la cargue en la pantalla de setup)."""
    while not _stop_event.is_set():
        _restart_event.clear()
        if not _init_account():
            logger.info("Sin cuenta activa valida. Esperando configuracion (setup)...")
            _stop_event.wait(10)
            continue

        _refresh_sentiment()
        while not _stop_event.is_set() and not _restart_event.is_set():
            try:
                _refresh_sentiment()   # no-op si los datos tienen menos de 8h
                _cycle()
            except Exception as e:
                logger.exception("Error en ciclo: %s", e)
            _stop_event.wait(LOOP_INTERVAL)   # sleep interrumpible

        if _restart_event.is_set():
            logger.info("Reiniciando con la nueva cuenta activa...")

    logger.info("Bot detenido.")


def _handle_closed_trade(balance: float, reason: str):
    """Registra y notifica el cierre del trade activo usando el PnL real de Bybit."""
    global active_trade
    if not active_trade:
        return

    symbol = active_trade.get("symbol", SYMBOLS[0])
    exit_price, pnl = 0.0, 0.0

    # Fuente primaria: PnL realizado de Bybit (con reintentos por latencia de settle)
    for _ in range(3):
        closed = broker.get_closed_pnl(symbol, limit=1)
        if closed and closed[0].get("pnl"):
            exit_price = closed[0]["exit"]
            pnl        = closed[0]["pnl"]
            break
        time.sleep(1)

    # Fallback robusto: PnL = delta del balance de la cuenta desde la entrada
    if pnl == 0.0 and active_trade.get("balance_at_entry"):
        pnl = round(balance - active_trade["balance_at_entry"], 2)
    if exit_price == 0.0:
        exit_price = broker.get_ticker(symbol)

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

    account = broker.get_account()
    if not account:
        logger.warning("Sin respuesta de Bybit API. Reintentando en el proximo ciclo.")
        return

    balance = account.get("balance", INITIAL_BALANCE)
    equity  = account.get("equity",  balance)
    peak_equity = max(peak_equity, equity)

    sm.append_equity(equity, balance)

    cft    = sm.calc_cft_status(account, INITIAL_BALANCE)
    dd_pct = abs((equity - peak_equity) / peak_equity) if peak_equity > 0 else 0.0

    # Guardas segun el modo de la cuenta
    if PROP_RULES:
        # Reglas prop firm (CFT / ADN): stop a -10% DD, pausa diaria -5%, objetivo +8%
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
    else:
        # Modo libre / compounding: sin objetivo, solo tope de seguridad
        loss_pct = (balance - INITIAL_BALANCE) / INITIAL_BALANCE if INITIAL_BALANCE > 0 else 0.0
        if loss_pct <= -MAX_LOSS_PCT:
            logger.error("TOPE DE PERDIDA personal (%.0f%%) alcanzado. Cerrando y parando.",
                         MAX_LOSS_PCT * 100)
            notifier.send(f"🛑 <b>TOPE DE PÉRDIDA ALCANZADO</b>\n"
                          f"Cuenta personal en {loss_pct*100:.1f}% — bot detenido por seguridad.")
            _close_all()
            sm.save_state(account, "MAX_LOSS_STOP", active_trade, cft)
            _stop_event.set()
            return

    # Calcular indicadores de cada par y detectar posicion abierta (cualquiera)
    global _regime_by_symbol
    dfs, open_sym, open_pos = {}, None, None
    for sym in SYMBOLS:
        df = broker.get_candles(sym, config.TIMEFRAME, count=400)
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
        positions = broker.get_open_positions(sym)
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
            broker.modify_sl(open_sym, pos_type, new_sl)
            logger.info("Trailing SL LONG %s: %.6f", open_sym, new_sl)
        elif pos_type == "short" and new_sl < current_sl:
            broker.modify_sl(open_sym, pos_type, new_sl)
            logger.info("Trailing SL SHORT %s: %.6f", open_sym, new_sl)

        # MODO OVERNIGHT: no se cierra por fin de sesion. El trade corre hasta
        # tocar SL o TP (ambos puestos en Bybit server-side). El trailing stop
        # se sigue ajustando cada ciclo, tambien fuera de la ventana de trading.
        sm.save_state(account, "holding", active_trade, cft)
        return

    # ── Sin posiciones (modo SINGLE): buscar entrada en orden de prioridad ───
    for sym in SYMBOLS:
        if sym not in dfs:
            continue
        df  = dfs[sym]
        cfg = config.symbol_config(sym)
        signal, regime = check_entry(df, sym, cfg, USE_SENTIMENT)
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

        result = broker.open_order(symbol=sym, order_type=signal, lot=lot, sl=sl, tp=tp,
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
                "balance_at_entry": balance,
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
        for sym in SYMBOLS:
            if sym in dfs:
                c = dfs[sym].iloc[-1]
                parts.append(f"{sym}[RSI={c.get('rsi',0):.0f} ADX={c.get('adx',0):.0f} "
                             f"CHOP={c.get('h4_chop',0):.0f} ST={int(c.get('h4_st_dir',0)):+d}]")
        logger.info("Sin senal | %s | DD=%.1f%% equity=$%.2f",
                    " ".join(parts), dd_pct * 100, equity)
    sm.save_state(account, "no_signal", active_trade, cft)


def _close_all():
    global active_trade
    for sym in SYMBOLS:
        for pos in broker.get_open_positions(sym):
            broker.close_position(pos)
            logger.info("Posicion cerrada forzada %s: %s size=%.6f",
                        sym, pos.get("type"), pos.get("size", 0))
    active_trade = None


if __name__ == "__main__":
    run()
