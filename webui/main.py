"""Punto de entrada de la interfaz NiceGUI."""

import asyncio
import os

from nicegui import app, ui

import config
import db
import respaldos
from webui import (
    pag_carga,
    pag_configuracion,
    pag_facturas,
    pag_gestion,
    pag_pagos,
    pag_reportes,
    pag_ventas,
)

__all__ = ["main"]


@app.middleware("http")
async def _cabeceras_seguridad(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def _backup_diario():
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            respaldos.crear_backup("diario")
        except Exception:
            pass


@app.on_startup
async def _arranque():
    db.inicializar()
    try:
        respaldos.crear_backup("inicio")
    except Exception:
        pass
    asyncio.create_task(_backup_diario())


def main() -> None:
    ui.run(
        title="Facturador OCR",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
        reload=False,
        show=False,
        favicon="📄",
        storage_secret=config.APP_PASSWORD or "facturador-ocr-secret-local",
        reconnect_timeout=120,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
