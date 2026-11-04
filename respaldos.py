import re
import sqlite3
from datetime import date as datetime_date
from datetime import datetime as datetime_dt
from pathlib import Path

from config import CARPETA_RESPALDOS, RETENCION_RESPALDOS, RUTA_DB

__all__ = ["crear_backup", "limpiar_backups", "listar_backups"]

_CARPETA = Path(CARPETA_RESPALDOS)


def crear_backup(motivo: str = "auto") -> Path:
    """Copia consistente de la base (API de backup de SQLite) hacia backups/."""
    _CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime_dt.now().strftime("%Y%m%d_%H%M%S")
    destino = _CARPETA / f"facturas_{marca}_{re.sub(r'[^a-z0-9]', '', motivo.lower())[:12]}.db"
    origen = sqlite3.connect(RUTA_DB)
    destino_conn = sqlite3.connect(destino)
    try:
        origen.backup(destino_conn)
        destino_conn.commit()
    finally:
        destino_conn.close()
        origen.close()
    limpiar_backups()
    return destino


def limpiar_backups(maximo: int = RETENCION_RESPALDOS) -> int:
    archivos = sorted(_CARPETA.glob("facturas_*.db"))
    excedentes = archivos[:-maximo] if len(archivos) > maximo else []
    for a in excedentes:
        try:
            a.unlink()
        except OSError:
            pass
    return len(excedentes)


def listar_backups() -> list:
    if not _CARPETA.exists():
        return []
    return sorted(
        (
            {"archivo": a.name, "ruta": str(a), "tamano_kb": round(a.stat().st_size / 1024, 1)}
            for a in _CARPETA.glob("facturas_*.db")
        ),
        key=lambda x: x["archivo"],
        reverse=True,
    )
