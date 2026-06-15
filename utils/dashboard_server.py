"""Sirve el dashboard (botbtc-dashboard-ms) en el puerto 8090, sin logs (compatible con pythonw)."""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

DASHBOARD_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "..", "botbtc-dashboard-ms"))


class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def log_message(self, *args):
        pass  # silenciar logs (pythonw no tiene stdout)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8090), QuietHandler)
    print(f"Dashboard en http://localhost:8090/ (sirviendo {DASHBOARD_DIR})")
    server.serve_forever()
