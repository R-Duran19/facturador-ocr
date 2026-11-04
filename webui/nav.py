"""Historial de navegación interno: permite volver atrás (botón y Alt+←) incluso
entre vistas internas que no cambian la ruta (ej: Ventas › Pagos › Anahi)."""

import time

from nicegui import app, ui

_CLAVE_PILA = "nav_hist"
_CLAVE_IR = "nav_ir"
_MAX = 80

restore_data: dict = {}

__all__ = ["registrar", "restaurar", "atras"]


def _pila() -> list:
    return app.storage.user.setdefault(_CLAVE_PILA, [])


def _igual(a: dict, b: dict) -> bool:
    return all(str(a.get(k) or "") == str(b.get(k) or "") for k in ("ruta", "vista", "cliente", "proveedor"))


def registrar(ruta: str, **estado) -> None:
    """Registra la vista actual en el historial. Si venimos de 'atras', restaura."""
    global restore_data
    ir = app.storage.user.get(_CLAVE_IR)
    if ir:
        app.storage.user.pop(_CLAVE_IR, None)
        if ir.get("ruta") == ruta:
            restore_data = ir
            return
    entrada = {"ruta": ruta}
    entrada.update({k: v for k, v in estado.items() if v})
    pila = _pila()
    if estado and pila and pila[-1].get("ruta") == ruta and not pila[-1].get("vista"):
        pila.pop()
    if pila and _igual(pila[-1], entrada):
        return
    pila.append(entrada)
    del pila[:-_MAX]


def restaurar(ruta: str) -> dict:
    """Devuelve (y limpia) el estado guardado si se llegó acá con 'atras'."""
    global restore_data
    if restore_data.get("ruta") == ruta:
        data = dict(restore_data)
        restore_data = {}
        return data
    restore_data = {}
    return {}


def atras() -> None:
    """Vuelve una entrada atrás en el historial."""
    pila = _pila()
    if len(pila) < 2:
        ui.notify("No hay nada más atrás.", type="info", timeout=1)
        return
    pila.pop()
    destino = dict(pila[-1])
    app.storage.user[_CLAVE_IR] = destino
    ui.navigate.to(destino["ruta"])
