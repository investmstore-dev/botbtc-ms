"""Servidor HTTP con CORS para servir los archivos data/ del bot al dashboard."""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def log_message(self, *args):
        pass  # silenciar logs

os.chdir(os.path.join(os.path.dirname(__file__), "data"))
server = HTTPServer(("127.0.0.1", 8091), CORSHandler)
print("Data server corriendo en http://localhost:8091/")
server.serve_forever()
