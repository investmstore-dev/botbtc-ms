"""
Módulo de notificaciones Telegram — BOT BTC Mining Store
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Envía a un chat/grupo de Telegram:
  - Apertura de trades (entrada, SL, TP, lote, régimen)
  - Cierre de trades (PnL en $ y %, razón del cierre)
  - Reporte diario al cierre de sesión (20:00 UTC)

Configuración en .env:
  TELEGRAM_BOT_TOKEN=123456:ABC-DEF...   (de @BotFather)
  TELEGRAM_CHAT_ID=-100123456789         (id del chat o grupo)

Si no están configurados, las funciones son no-op (el bot sigue normal).

Para obtener el chat_id: envía un mensaje al bot y corre
  python notifier.py --get-chat-id
Para probar: python notifier.py --test
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

# Reutiliza el cargador de .env del conector
from bybit_connector import _load_env
_load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"

ENABLED = bool(BOT_TOKEN and CHAT_ID)


def send(text: str) -> bool:
    """Envía un mensaje al chat configurado. HTML básico soportado."""
    if not ENABLED:
        return False
    try:
        r = requests.post(f"{API_URL}/sendMessage", json={
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=10)
        ok = r.json().get("ok", False)
        if not ok:
            logger.warning("Telegram error: %s", r.text)
        return ok
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


# ── Notificaciones de trades ──────────────────────────────────────────────────

def notify_trade_open(trade: dict):
    """trade: dict con type, entry, sl, tp, lot, regime, risk_pct."""
    emoji = "🟢" if trade["type"] == "long" else "🔴"
    send(
        f"{emoji} <b>TRADE ABIERTO — {trade['type'].upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 Entrada: <b>${trade['entry']:,.2f}</b>\n"
        f"🛑 Stop Loss: ${trade['sl']:,.2f}\n"
        f"🎯 Take Profit: ${trade['tp']:,.2f}\n"
        f"📦 Lote: {trade['lot']:.4f} BTC\n"
        f"📊 Régimen: {trade.get('regime', '?').upper()} "
        f"(riesgo {trade.get('risk_pct', 0) * 100:.1f}%)"
    )


def notify_trade_close(trade: dict, exit_price: float, pnl: float,
                       balance: float, reason: str):
    """Notifica cierre con PnL en $ y % sobre el balance."""
    pnl_pct = pnl / balance * 100 if balance else 0.0
    emoji   = "✅" if pnl >= 0 else "❌"
    word    = "GANANCIA" if pnl >= 0 else "PÉRDIDA"
    send(
        f"{emoji} <b>TRADE CERRADO — {word}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 Tipo: {trade.get('type', '?').upper()}\n"
        f"💵 Entrada: ${trade.get('entry', 0):,.2f}\n"
        f"🚪 Salida: ${exit_price:,.2f}\n"
        f"💰 Resultado: <b>${pnl:+,.2f} ({pnl_pct:+.2f}%)</b>\n"
        f"📝 Razón: {reason}"
    )


# ── Reporte diario ────────────────────────────────────────────────────────────

def notify_daily_report(account: dict, cft: dict, trades_today: list,
                        regime_info: dict | None = None):
    """Resumen al cierre de sesión (20:00 UTC)."""
    balance = account.get("balance", 0)
    equity  = account.get("equity", 0)

    n      = len(trades_today)
    wins   = sum(1 for t in trades_today if t.get("pnl", 0) > 0)
    pnl_day = sum(t.get("pnl", 0) for t in trades_today)

    lines = [
        "📋 <b>REPORTE DIARIO — BOT BTC</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"💼 Balance: <b>${balance:,.2f}</b>",
        f"📊 Equity: ${equity:,.2f}",
        f"📈 Progreso CFT: {cft.get('profit_pct', 0):+.2f}% / "
        f"{cft.get('target_pct', 8):.0f}% objetivo",
        f"🔻 DD máximo: {cft.get('max_dd_pct', 0):.2f}% "
        f"(límite -{cft.get('dd_limit_pct', 10):.0f}%)",
        "",
        f"🎯 Trades hoy: {n}" + (f" ({wins} ganados, {n - wins} perdidos)" if n else ""),
    ]
    if n:
        lines.append(f"💰 PnL del día: <b>${pnl_day:+,.2f}</b>")
        for t in trades_today:
            e = "✅" if t.get("pnl", 0) >= 0 else "❌"
            lines.append(
                f"  {e} {t.get('type', '?').upper()} "
                f"${t.get('entry', 0):,.0f} → ${t.get('exit', 0):,.0f} "
                f"= ${t.get('pnl', 0):+,.2f}"
            )
    else:
        lines.append("😴 Sin operaciones (sin señal válida)")

    if regime_info:
        lines += [
            "",
            f"🧭 Régimen: {regime_info.get('regime', '?')} "
            f"(CHOP={regime_info.get('chop', 0):.0f}, "
            f"ST={'🟢 alcista' if regime_info.get('st_dir', 0) > 0 else '🔴 bajista'})",
        ]

    lines += ["", "🤖 Bot activo — próxima sesión 04:00 UTC"]
    send("\n".join(lines))


# ── Utilidades CLI ────────────────────────────────────────────────────────────

def get_chat_id():
    """Muestra los chat_id de los últimos mensajes recibidos por el bot."""
    if not BOT_TOKEN:
        print("Falta TELEGRAM_BOT_TOKEN en .env")
        return
    r = requests.get(f"{API_URL}/getUpdates", timeout=10).json()
    updates = r.get("result", [])
    if not updates:
        print("Sin mensajes. Envía un mensaje al bot (o al grupo) y vuelve a correr esto.")
        return
    seen = set()
    for u in updates:
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            print(f"chat_id: {cid}  ({chat.get('type')}: "
                  f"{chat.get('title') or chat.get('username') or chat.get('first_name')})")


if __name__ == "__main__":
    import sys
    if "--get-chat-id" in sys.argv:
        get_chat_id()
    elif "--test" in sys.argv:
        if not ENABLED:
            print("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
        else:
            ok = send("🤖 <b>Test BOT BTC</b> — notificaciones funcionando correctamente ✅")
            print("Mensaje enviado" if ok else "ERROR al enviar")
    else:
        print(__doc__)
