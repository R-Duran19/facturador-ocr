"""PDFs servidos al vuelo por URL: se generan al momento y no se guardan en disco."""

from urllib.parse import quote

import pdf_reportes
from nicegui import app
from starlette.responses import Response
from starlette.routing import Route

try:
    from nicegui import run as _run
except ImportError:
    _run = None

__all__ = ["registrar", "url_empresa", "url_resumen"]


def _respuesta(datos: bytes, nombre: str) -> Response:
    return Response(
        datos,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(nombre)}",
            "Cache-Control": "no-store",
        },
    )


async def _empresa(request):
    mes = request.path_params["mes"]
    cliente = request.path_params["cliente"]
    if _run is not None:
        datos = await _run.io_bound(pdf_reportes.pdf_empresa, cliente, mes)
    else:
        datos = pdf_reportes.pdf_empresa(cliente, mes)
    return _respuesta(datos, f"ventas {cliente} - {mes}.pdf")


async def _resumen(request):
    mes = request.path_params["mes"]
    if _run is not None:
        datos = await _run.io_bound(pdf_reportes.pdf_resumen_mes, mes)
    else:
        datos = pdf_reportes.pdf_resumen_mes(mes)
    return _respuesta(datos, f"control {mes}.pdf")


def registrar() -> None:
    if not any(getattr(r, "path", "") == "/pdf/empresa/{mes}/{cliente}" for r in app.router.routes):
        app.router.routes.append(Route("/pdf/empresa/{mes}/{cliente}", _empresa))
        app.router.routes.append(Route("/pdf/resumen/{mes}", _resumen))


def url_empresa(mes: str, cliente: str) -> str:
    return f"/pdf/empresa/{quote(str(mes), safe='')}/{quote(str(cliente), safe='')}"


def url_resumen(mes: str) -> str:
    return f"/pdf/resumen/{quote(str(mes), safe='')}"
