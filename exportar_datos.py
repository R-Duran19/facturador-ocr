"""Exporta un paquete .zip con catalogo + meses (+ PDFs).
Uso: venv/Scripts/python.exe exportar_datos.py [MES ...]   (sin argumentos = todos)
"""

import sys
from pathlib import Path

import paquete_datos

if __name__ == "__main__":
    meses = sys.argv[1:] or None
    datos, nombre = paquete_datos.exportar(meses)
    Path(nombre).write_bytes(datos)
    print(f"Paquete generado: {nombre} ({len(datos) / 1e6:.1f} MB)")
