"""
Lanzador unico — BOT Mining Store (bot + dashboard + setup) en un solo proceso.
Pensado para empaquetar con PyInstaller en un .exe que corre en segundo plano.

Arranca en hilos:
  - Servidor de datos      (http://localhost:8091)
  - Dashboard              (http://localhost:8090)
  - Control / setup        (http://localhost:8092)  <- abre el navegador aqui
  - Bot de trading         (lee la cuenta activa; espera si no hay)

Uso (dev):  python app.py
Uso (.exe): BotMiningStore.exe
"""
import os
import sys
import time
import threading
import webbrowser


def app_dir() -> str:
    """Carpeta base (junto al .exe si esta empaquetado, o la del proyecto)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# Todas las rutas relativas (data/, *.csv, .env) cuelgan de aqui
os.chdir(app_dir())
sys.path.insert(0, app_dir())

from utils import data_server, dashboard_server, control_server   # noqa: E402
from logic import bot                                             # noqa: E402


def main():
    print("=" * 56)
    print("  BOT Mining Store — iniciando servicios...")
    print("=" * 56)

    services = [
        ("Datos      (8091)", data_server.serve),
        ("Dashboard  (8090)", dashboard_server.serve),
        ("Setup      (8092)", control_server.serve),
        ("Bot        ", bot.run),
    ]
    for name, target in services:
        threading.Thread(target=target, daemon=True, name=name.strip()).start()
        print(f"  [OK] {name}")

    time.sleep(2)
    print("\n  Setup:     http://localhost:8092")
    print("  Dashboard: http://localhost:8090")
    print("  (Ctrl+C para detener)\n")
    try:
        webbrowser.open("http://localhost:8092/")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Deteniendo bot...")
        bot.stop()
        time.sleep(1)


if __name__ == "__main__":
    main()
