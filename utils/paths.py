"""Rutas a recursos empaquetados (compatible con PyInstaller)."""
import os
import sys


def resource_path(*parts) -> str:
    """Ruta a un recurso de solo-lectura empaquetado (setup.html, dashboard).
    Bajo PyInstaller los datos viven en sys._MEIPASS; en dev, en la raiz del proyecto."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
