"""Almacenamiento de archivos originales: imágenes se convierten a PDF."""

import io
import re
from pathlib import Path

from PIL import Image
from pymupdf import open as pymupdf_open

from config import CARPETA_ARCHIVOS

__all__ = ["guardar_archivo_original", "ruta_absoluta"]

_RAIZ = Path(CARPETA_ARCHIVOS)
_SEGURO = re.compile(r"[^\w\-. ]+")


def _seguro(texto: str) -> str:
    return _SEGURO.sub("-", str(texto)).strip()[:80] or "archivo"


def _a_pdf(data: bytes, tipo: str) -> bytes:
    if tipo == "pdf":
        return data
    if tipo in ("jpeg", "png"):
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, "PDF", resolution=150)
        return buffer.getvalue()
    raise ValueError(f"Tipo no convertible: {tipo}")


def guardar_archivo_original(mes: str, proveedor: str, nombre_original: str, data: bytes, tipo: str, factura_nro: str = "") -> str:
    """Guarda el original como PDF en archivos/{mes}/{proveedor}/ y devuelve la ruta relativa."""
    try:
        contenido = _a_pdf(data, tipo)
    except Exception:
        return ""
    carpeta = _RAIZ / _seguro(mes) / _seguro(proveedor)
    carpeta.mkdir(parents=True, exist_ok=True)
    base = _seguro(f"{factura_nro or Path(nombre_original).stem}")
    ruta = carpeta / f"{base}.pdf"
    n = 2
    while ruta.exists():
        ruta = carpeta / f"{base}_{n}.pdf"
        n += 1
    ruta.write_bytes(contenido)
    return str(ruta.relative_to(_RAIZ))


def ruta_absoluta(ruta_relativa: str) -> Path:
    return _RAIZ / ruta_relativa
