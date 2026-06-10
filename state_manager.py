"""Persiste el estado del bot BTC en archivos JSON para el dashboard."""
import json
import os
from datetime import datetime, date
from config import DATA_DIR, STATE_FILE, TRADES_FILE, EQUITY_FILE


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def save_state(account: dict, signal: str, active_trade: dict | None,
               cft_status: dict):
    _ensure_dir()
    state = {
        "updated":      _now(),
        "account":      account,
        "signal":       signal,
        "active_trade": active_trade,
        "cft":          cft_status,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def append_trade(trade: dict):
    _ensure_dir()
    trades = load_trades()
    trade["timestamp"] = _now()
    trades.append(trade)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)


def load_trades() -> list:
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE) as f:
        return json.load(f)


def append_equity(equity: float, balance: float):
    _ensure_dir()
    history = load_equity()
    history.append({"time": _now(), "equity": equity, "balance": balance})
    if len(history) > 2000:
        history = history[-2000:]
    with open(EQUITY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def load_equity() -> list:
    if not os.path.exists(EQUITY_FILE):
        return []
    with open(EQUITY_FILE) as f:
        return json.load(f)


def calc_cft_status(account: dict, initial_balance: float) -> dict:
    from config import CFT_TARGET_PCT, CFT_MAX_DD_PCT, CFT_DAILY_DD_PCT

    balance = account.get("balance", initial_balance)
    equity  = account.get("equity",  balance)

    profit_pct = (balance - initial_balance) / initial_balance

    equity_hist = load_equity()
    peak        = max((p["equity"] for p in equity_hist), default=initial_balance)
    max_dd_pct  = (equity - peak) / initial_balance if equity < peak else 0.0

    today_str         = date.today().isoformat()
    today_pts         = [p for p in equity_hist if p["time"].startswith(today_str)]
    day_start_balance = today_pts[0]["balance"] if today_pts else balance
    daily_dd_pct      = (equity - day_start_balance) / initial_balance if equity < day_start_balance else 0.0

    return {
        "initial_balance":    initial_balance,
        "current_balance":    balance,
        "profit_pct":         round(profit_pct * 100, 2),
        "target_pct":         CFT_TARGET_PCT * 100,
        "progress_pct":       round(min(profit_pct / CFT_TARGET_PCT * 100, 100), 1),
        "max_dd_pct":         round(max_dd_pct * 100, 2),
        "daily_dd_pct":       round(daily_dd_pct * 100, 2),
        "dd_limit_pct":       CFT_MAX_DD_PCT * 100,
        "daily_dd_limit_pct": CFT_DAILY_DD_PCT * 100,
        "target_reached":     profit_pct >= CFT_TARGET_PCT,
        "dd_violated":        max_dd_pct <= -CFT_MAX_DD_PCT,
        "daily_dd_violated":  daily_dd_pct <= -CFT_DAILY_DD_PCT,
    }
