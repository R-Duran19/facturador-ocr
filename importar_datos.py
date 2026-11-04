"""Importa un paquete .zip generado con exportar_datos.py.
Uso: venv/Scripts/python.exe importar_datos.py paquete_datos_XXXX.zip
Crea un backup de la base antes de importar. No borra nada: solo agrega/actualiza.
"""

import sys
from pathlib import Path

import paquete_datos

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: venv/Scripts/python.exe importar_datos.py <paquete_datos_XXXX.zip>")
        raise SystemExit(1)
    contenido = Path(sys.argv[1]).read_bytes()
    resumen = paquete_datos.importar(contenido)
    print("Importacion completa (backup creado antes). Resumen:")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
