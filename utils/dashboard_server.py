"""Sirve el dashboard en el puerto 8090 (sin logs, apto para hilos / pythonw).

Busca el dashboard en este orden:
  1) web/dashboard/  (copia empaquetada para el .exe)
  2) ../botbtc-dashboard-ms/  (repo hermano, desarrollo local)
"""
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import config
from utils.paths import resource_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUNDLED = resource_path("web", "dashboard")            # copia empaquetada (.exe)
_SIBLING = os.path.normpath(os.path.join(ROOT, "..", "botbtc-dashboard-ms"))  # dev
DASHBOARD_DIR = _BUNDLED if os.path.isdir(_BUNDLED) else _SIBLING
PORT = config.PORT_DASHBOARD


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = partial(QuietHandler, directory=DASHBOARD_DIR)
    HTTPServer(("127.0.0.1", PORT), handler).serve_forever()


if __name__ == "__main__":
    print(f"Dashboard en http://localhost:{PORT}/  ({DASHBOARD_DIR})")
    serve()
