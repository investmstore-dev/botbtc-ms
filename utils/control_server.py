"""
Servidor de control + pantalla de setup (puerto 8092, solo localhost).
Permite elegir el tipo de cuenta (CFT / ADN), ingresar credenciales, validar la
conexion y guardar. Al guardar/activar una cuenta, reinicia el bot para que la tome.

Endpoints:
  GET  /                 -> web/setup.html
  GET  /api/state        -> cuentas (sin secretos), activa, tipos, bot corriendo
  POST /api/test         -> prueba conexion de una config
  POST /api/save         -> valida + guarda + activa una cuenta
  POST /api/activate     -> cambia la cuenta activa
"""
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

import config
from utils import account_manager as am
from utils.paths import resource_path

SETUP_HTML = resource_path("web", "setup.html")

PORT = config.PORT_CONTROL


def _mask(cfg: dict) -> dict:
    """Oculta secretos antes de enviar al frontend."""
    safe = dict(cfg)
    for k in ("api_secret", "password"):
        if safe.get(k):
            safe[k] = "••••••••"
    return safe


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except json.JSONDecodeError:
            return {}

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path in ("/", "/index.html", "/setup", "/setup.html"):
            if os.path.exists(SETUP_HTML):
                with open(SETUP_HTML, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"setup.html no encontrado", "text/plain")
            return
        if self.path == "/api/state":
            data = am.load_accounts()
            try:
                from logic import bot
                running = bot.is_running()
            except Exception:
                running = False
            self._send(200, {
                "active": data.get("active"),
                "accounts": {k: _mask(v) for k, v in data.get("accounts", {}).items()},
                "types": am.ACCOUNT_TYPES,
                "bot_running": running,
            })
            return
        self._send(404, {"error": "not found"})

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        body = self._body()
        if self.path == "/api/test":
            ok, msg = am.test_connection(body)
            self._send(200, {"ok": ok, "message": msg})
            return
        if self.path == "/api/save":
            acc_id = body.get("id") or f"{body.get('type', 'acc').lower()}_{body.get('login', body.get('api_key', ''))[:6] if isinstance(body.get('login', body.get('api_key', '')), str) else body.get('login')}"
            ok, msg = am.add_account(str(acc_id), body)
            if ok:
                am.set_active(str(acc_id))
                self._restart_bot()
            self._send(200, {"ok": ok, "message": msg, "id": str(acc_id)})
            return
        if self.path == "/api/activate":
            ok, msg = am.set_active(body.get("id", ""))
            if ok:
                self._restart_bot()
            self._send(200, {"ok": ok, "message": msg})
            return
        self._send(404, {"error": "not found"})

    @staticmethod
    def _restart_bot():
        try:
            from logic import bot
            bot.request_restart()
        except Exception:
            pass


def serve():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Control/setup en http://localhost:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    serve()
