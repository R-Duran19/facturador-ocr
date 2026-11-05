"""Componentes UI reutilizables."""

from datetime import date
from typing import Callable

import config
import db
import reportes
from nicegui import ui

__all__ = [
    "tarjeta_metrica",
    "chips_estado",
    "confirmar",
    "strip_metricas",
    "selector_porcentaje",
    "input_fecha",
    "tabla_con_busqueda",
    "tarjeta_gasto_ia",
]


def tarjeta_gasto_ia() -> None:
    """Tarjeta destacada con el gasto real de IA (tokens registrados por la API)."""
    gasto = db.leer_gasto_ia()
    with ui.card().classes("min-w-[260px] border-2").style(
        "border-color: var(--q-primary);" if not config.BILLING_ACTIVO else "border-color: #F2C037;"
    ):
        with ui.row().classes("items-center gap-2 w-full"):
            ui.icon("bolt", color="amber-8").classes("text-2xl")
            ui.label("Gasto IA (tokens reales)").classes("font-bold")
            ui.badge(
                "SIN BILLING · gratis (free tier)" if not config.BILLING_ACTIVO else "CON BILLING · se cobra real",
                color="grey-7" if not config.BILLING_ACTIVO else "orange",
            ).props("text-color=white")
        with ui.row().classes("w-full justify-between gap-4 q-px-sm"):
            with ui.column().classes("gap-0 items-center"):
                ui.label(f"${gasto['hoy']:,.4f}").classes("text-lg font-bold text-amber-8")
                ui.label("hoy").classes("text-[11px] opacity-50")
            with ui.column().classes("gap-0 items-center"):
                ui.label(f"${gasto['mes']:,.2f}").classes("text-lg font-bold text-amber-8")
                ui.label("este mes").classes("text-[11px] opacity-50")
            with ui.column().classes("gap-0 items-center"):
                ui.label(f"${gasto['total']:,.2f}").classes("text-lg font-bold")
                ui.label("histórico").classes("text-[11px] opacity-50")
        ui.label(
            "Valor de referencia: con billing activo, este monto es lo que cobra Google."
            if config.BILLING_ACTIVO
            else "No se cobra nada todavía. Al activar billing, este monto pasa a ser el cargo real."
        ).classes("text-[10px] opacity-40")


def selector_porcentaje(label: str, valor: float = 5.0, presets: tuple = (3.5, 3.75, 4, 4.5, 5)) -> ui.select:
    """% elegible con valores comunes; también acepta uno escrito a mano."""
    opciones = sorted({*(float(p) for p in presets), float(valor or 0)})
    opciones = [o for o in opciones if o > 0]
    return ui.select(
        opciones,
        value=float(valor or 0),
        label=label,
        new_value_mode="add",
    ).classes("w-full")


def input_fecha(label: str, valor: str = None) -> ui.input:
    """Campo de fecha de solo lectura; el calendario se abre SOLO desde el icono
    (el menu queda anclado al icono, no al input, para no abrirse al hacer click en el campo)."""
    inp = ui.input(label, value=valor or date.today().isoformat()).props("readonly")
    with inp.add_slot("append"):
        icono = ui.icon("event").classes("cursor-pointer opacity-70")
        with icono:
            with ui.menu().props("auto-close") as menu:
                ui.date(value=inp.value, on_change=lambda e: inp.set_value(e.value))
    icono.on("click", menu.open)
    return inp


def tabla_con_busqueda(
    columnas: list, filas: list, clave: str, seleccion_handler=None, paginacion=15, resaltar_si: str = ""
) -> tuple:
    """Tabla con buscador integrado. resaltar_si: clave booleana por fila para pintarla en amarillo suave."""
    with ui.row().classes("w-full justify-end"):
        buscador = ui.input("Buscar...", placeholder="filtrar por cualquier columna").props(
            "outlined dense clearable"
        ).classes("w-64")
    tabla = ui.table(
        columns=columnas,
        rows=filas,
        row_key=clave,
        selection="single" if seleccion_handler else None,
        pagination={"rowsPerPage": paginacion},
        on_select=seleccion_handler,
    ).classes("w-full").props("flat dense bordered")
    if resaltar_si and any(fila.get(resaltar_si) for fila in filas):
        tabla.add_slot(
            "body-cell",
            '<q-td :props="props" :class="props.row.%s ? \'bg-amber-1\' : \'\'">{{ props.value }}</q-td>' % resaltar_si,
        )
    buscador.on(
        "update:model-value",
        lambda e: tabla.props(f'filter="{str(e.args or "").replace(chr(34), chr(39))}"'),
    )
    return tabla, buscador


def strip_metricas(mes: str) -> None:
    """Fila compacta de números clave del mes (usa la capa de reportes)."""
    facturas = db.leer_facturas_mes(mes)
    ventas = db.leer_ventas_mes(mes)
    costos = reportes.resumen_costos_ganancia(mes)
    utilidad = sum(f["Utilidad"] for f in costos)
    with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 items-baseline q-px-sm"):
        _dato(len(facturas), "facturas")
        _dato(sum(f["Monto_Total"] for f in facturas), "comprado (Bs)")
        _dato(sum(v["Precio_Cobrado"] for v in ventas), "vendido (Bs)")
        _dato(sum(v["Saldo"] for v in ventas), "por cobrar (Bs)")
        _dato(utilidad, "utilidad (Bs)", destacado=True)


def _dato(valor, etiqueta: str, destacado: bool = False) -> None:
    with ui.column().classes("gap-0 min-w-[120px]"):
        ui.label(f"{valor:,.2f}" if isinstance(valor, float) else str(valor)).classes(
            "text-xl font-bold" + (" text-primary" if destacado else "")
        )
        ui.label(etiqueta).classes("text-xs opacity-50")


def tarjeta_metrica(etiqueta: str, valor: str, icono: str = "receipt_long", color: str = "primary") -> None:
    with ui.card().classes("min-w-[170px] flex-1"):
        with ui.row().classes("items-center gap-3 w-full"):
            ui.icon(icono, color=color).classes("text-3xl opacity-80")
            with ui.column().classes("gap-0"):
                ui.label(etiqueta).classes("text-xs opacity-60")
                ui.label(valor).classes("text-xl font-bold")


def chips_estado(ok: int, duplicados: int, errores: int) -> None:
    with ui.row().classes("gap-2"):
        ui.badge(f"{ok} OK", color="green")
        if duplicados:
            ui.badge(f"{duplicados} duplicadas", color="orange")
        if errores:
            ui.badge(f"{errores} errores", color="red")


def confirmar(mensaje: str, al_confirmar: Callable, texto_boton: str = "Confirmar") -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label(mensaje)
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=dialog.close).props("flat")
            ui.button(
                texto_boton,
                on_click=lambda: (dialog.close(), al_confirmar()),
            ).props("color=negative")
    dialog.open()
