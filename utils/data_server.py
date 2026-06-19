"""Servidor HTTP con CORS para servir los archivos data/ del bot al dashboard (puerto 8091)."""
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import config

DATA_DIR = os.path.abspath(config.DATA_DIR)
PORT = config.PORT_DATA


class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


def serve():
    os.makedirs(DATA_DIR, exist_ok=True)
    handler = partial(CORSHandler, directory=DATA_DIR)   # sin os.chdir (apto para hilos)
    HTTPServer(("127.0.0.1", PORT), handler).serve_forever()


if __name__ == "__main__":
    print(f"Data server en http://localhost:{PORT}/  ({DATA_DIR})")
    serve()
