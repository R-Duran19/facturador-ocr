"""Maestros: proveedores y clientes — CRUD con diálogos, buscador y cero tipeo innecesario."""

from nicegui import ui

import db
from webui.componentes import confirmar, selector_porcentaje, tabla_con_busqueda

__all__ = ["seccion_proveedores", "seccion_clientes"]

PRESETS_COMPRA = (1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)
PRESETS_VENTA = (3.5, 3.75, 4, 4.5, 5)


def _campo_numerico(label: str, valor: str = "") -> ui.input:
    return ui.input(label, value=str(valor or "")).props("type=number outlined dense")


def seccion_proveedores():
    seleccion = {"fila": None}
    cont = ui.column().classes("w-full gap-2")

    COLUMNAS = [
        {"name": "nombre", "label": "Proveedor", "field": "Nombre_Proveedor", "align": "left"},
        {"name": "nit", "label": "NIT", "field": "NIT", "align": "left"},
        {"name": "tel", "label": "Teléfono", "field": "Telefono", "align": "left"},
        {"name": "com", "label": "% Compra", "field": "com", "align": "right"},
    ]

    def pintar():
        cont.clear()
        with cont:
            datos = db.leer_proveedores_full()
            if not datos:
                ui.label("Sin proveedores. Agregá el primero con el botón de arriba.").classes("opacity-50")
            else:
                filas = [{**d, "com": f"{d['Comision_Pactada_Pct']:g}"} for d in datos]
                tabla_con_busqueda(
                    COLUMNAS,
                    filas,
                    "Nombre_Proveedor",
                    seleccion_handler=lambda e: seleccion.update({"fila": e.selection[0] if e.selection else None}),
                )
            with ui.row().classes("w-full gap-2"):
                ui.button(
                    "➕ Nuevo proveedor",
                    icon="person_add",
                    on_click=lambda: _dialogo_proveedor(None, pintar),
                ).props("unelevated")
                ui.button("Editar seleccionado", icon="edit", on_click=lambda: _editar_guardia_prov(seleccion, pintar)).props("flat")
                ui.button(
                    "Eliminar seleccionado",
                    icon="delete",
                    on_click=lambda: _eliminar_prov(seleccion["fila"], pintar),
                ).props("flat color=negative")

    def _editar_guardia_prov(seleccion, refrescar):
        if not seleccion["fila"]:
            ui.notify("Seleccioná una fila de la tabla.", type="warning")
            return
        _dialogo_proveedor(seleccion["fila"], refrescar)

    def _dialogo_proveedor(fila, refrescar):
        alta = fila is None
        valor_pct = float((fila or {}).get("Comision_Pactada_Pct") or 3.5)
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[520px]"):
            ui.label(
                f"Editar {fila['Nombre_Proveedor']}" if not alta else "Nuevo proveedor"
            ).classes("text-lg font-bold")
            with ui.grid(columns=2).classes("w-full gap-3"):
                e_nombre = ui.input("Proveedor", value=(fila or {}).get("Nombre_Proveedor", "")).props("outlined dense autofocus")
                e_nit = _campo_numerico("NIT", (fila or {}).get("NIT", ""))
                e_tel = _campo_numerico("Teléfono", (fila or {}).get("Telefono", ""))
                e_pct = selector_porcentaje("% Compra", valor_pct, PRESETS_COMPRA)
            ui.label("El % de compra se aplica por defecto a cada lote que cargues de este proveedor.").classes(
                "text-xs opacity-50"
            )
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Guardar", icon="save", on_click=lambda: _guardar()).props("unelevated dense")

            def _guardar():
                if not (e_nombre.value or "").strip():
                    ui.notify("El nombre del proveedor es obligatorio.", type="warning")
                    return
                try:
                    pct = float(e_pct.value)
                except (TypeError, ValueError):
                    pct = 3.5
                if alta:
                    db.agregar_proveedor(e_nit.value or "", e_nombre.value, e_tel.value or "", pct)
                    ui.notify(f"Proveedor '{e_nombre.value}' creado.", type="positive")
                else:
                    db.actualizar_proveedor(
                        fila["Nombre_Proveedor"],
                        nit=e_nit.value or "",
                        nombre=e_nombre.value or "",
                        telefono=e_tel.value or "",
                        comision_pct=pct,
                    )
                    ui.notify("Proveedor actualizado.", type="positive")
                dialogo.close()
                refrescar()

            e_nombre.on("keydown.enter", _guardar)
        dialogo.open()

    def _eliminar_prov(fila, refrescar):
        if not fila:
            ui.notify("Seleccioná una fila de la tabla.", type="warning")
            return

        def accion():
            db.eliminar_proveedor(fila["Nombre_Proveedor"])
            ui.notify("Proveedor eliminado.", type="positive")
            refrescar()

        confirmar(f"¿Eliminar el proveedor '{fila['Nombre_Proveedor']}'?", accion, "Eliminar")

    with ui.row().classes("w-full justify-between items-center"):
        ui.label("Proveedores (personas que traen las facturas)").classes("font-semibold")
    pintar()


def seccion_clientes():
    seleccion = {"fila": None}
    cont = ui.column().classes("w-full gap-2")

    COLUMNAS = [
        {"name": "nombre", "label": "Cliente", "field": "Nombre_Razon_Social", "align": "left"},
        {"name": "nit", "label": "NIT", "field": "NIT", "align": "left"},
        {"name": "rubro", "label": "Rubro", "field": "Rubro", "align": "center"},
        {"name": "pct", "label": "% Venta", "field": "pct", "align": "right"},
        {"name": "whats", "label": "WhatsApp (contacto)", "field": "whats", "align": "left"},
        {"name": "banc", "label": "Bancarizado", "field": "banc", "align": "center"},
    ]

    def pintar():
        cont.clear()
        with cont:
            clientes = db.leer_clientes()

            def _faltantes(c):
                faltan = []
                try:
                    pct = float(c.get("Pct_Venta") or 0)
                except (TypeError, ValueError):
                    pct = 0.0
                if pct <= 0:
                    faltan.append("% Venta")
                if not str(c.get("Contacto", "")).strip():
                    faltan.append("WhatsApp (contacto)")
                return faltan

            incompletos = [c for c in clientes if _faltantes(c)]
            if incompletos:
                with ui.card().classes("w-full border-2").style("border-color: #F2C037; background: #FFFBEB;"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("error_outline", color="amber-8")
                        ui.label(
                            f"⚠ {len(incompletos)} cliente(s) con DATOS FALTANTES (% Venta o WhatsApp contacto) — tocá uno para completarlo:"
                        ).classes("font-semibold text-sm")
                    with ui.row().classes("w-full flex-wrap gap-2 q-px-sm"):
                        for c in incompletos[:12]:
                            ui.button(
                                f"{c['Nombre_Razon_Social']} (falta: {', '.join(_faltantes(c))})",
                                icon="edit",
                                on_click=lambda c=c: _dialogo_cliente(c, pintar),
                            ).props("flat dense no-caps text-color=amber-9").classes(
                                "bg-amber-1 rounded-borders text-xs"
                            )
                        if len(incompletos) > 12:
                            ui.label(f"… y {len(incompletos) - 12} más (filas resaltadas en la tabla)").classes(
                                "text-xs opacity-60 self-center"
                            )

            if not clientes:
                ui.label("Sin clientes. Agregá el primero con el botón de arriba.").classes("opacity-50")
            else:
                filas = [
                    {
                        **c,
                        "_inc": bool(_faltantes(c)),
                        "pct": f"{c['Pct_Venta']:g}",
                        "whats": " - ".join(p for p in (str(c.get("Contacto", "") or "").strip(), str(c.get("Telefono", "") or "").strip()) if p) or "—",
                        "banc": c.get("Bancarizado", "¿?"),
                    }
                    for c in clientes
                ]
                tabla_con_busqueda(
                    COLUMNAS,
                    filas,
                    "ID_Cliente",
                    seleccion_handler=lambda e: seleccion.update({"fila": e.selection[0] if e.selection else None}),
                    resaltar_si="_inc",
                )
            with ui.row().classes("w-full gap-2"):
                ui.button("➕ Nuevo cliente", icon="person_add", on_click=lambda: _dialogo_cliente(None, pintar)).props("unelevated")
                ui.button("Editar seleccionado", icon="edit", on_click=lambda: _editar_guardia_cli(seleccion, pintar)).props("flat")
                ui.button(
                    "Eliminar seleccionado",
                    icon="delete",
                    on_click=lambda: _eliminar_cli(seleccion["fila"], pintar),
                ).props("flat color=negative")

    def _editar_guardia_cli(seleccion, refrescar):
        if not seleccion["fila"]:
            ui.notify("Seleccioná una fila de la tabla.", type="warning")
            return
        _dialogo_cliente(seleccion["fila"], refrescar)

    def _dialogo_cliente(fila, refrescar):
        alta = fila is None
        valor_pct = float((fila or {}).get("Pct_Venta") or 5.0)
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[560px]"):
            ui.label(f"Editar {fila['Nombre_Razon_Social']}" if not alta else "Nuevo cliente").classes(
                "text-lg font-bold"
            )
            with ui.grid(columns=2).classes("w-full gap-3"):
                e_nombre = ui.input("Cliente", value=(fila or {}).get("Nombre_Razon_Social", "")).props("outlined dense autofocus")
                e_rubro = ui.select(
                    ["CONST", "MERCA", "CONST-MERCA", "OTRO"],
                    value=(fila or {}).get("Rubro") or "CONST",
                    label="Rubro",
                    new_value_mode="add",
                ).props("outlined dense")
                e_pct = selector_porcentaje("% Venta (tarifa del cliente)", valor_pct, PRESETS_VENTA)
                e_contacto = ui.input("Contacto WhatsApp (como lo tenés guardado)", value=(fila or {}).get("Contacto", "")).props("outlined dense")
                e_banc = ui.select(
                    ["¿?", "SI", "NO"],
                    value=(fila or {}).get("Bancarizado") or "¿?",
                    label="Bancarizado (QR)",
                    new_value_mode="add",
                ).props("outlined dense")
                e_nit = _campo_numerico("NIT", (fila or {}).get("NIT", ""))
                e_tel = _campo_numerico("WhatsApp / Teléfono", (fila or {}).get("Telefono", ""))
            e_notas = ui.input("Notas", value=(fila or {}).get("Notas", "")).props("outlined dense").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Guardar", icon="save", on_click=lambda: _guardar()).props("unelevated dense")

            def _guardar():
                if not (e_nombre.value or "").strip():
                    ui.notify("El nombre del cliente es obligatorio.", type="warning")
                    return
                try:
                    pct = float(e_pct.value)
                except (TypeError, ValueError):
                    pct = 5.0
                if alta:
                    db.agregar_cliente(
                        e_nombre.value,
                        e_nit.value or "",
                        e_tel.value or "",
                        e_notas.value or "",
                        e_rubro.value or "",
                        pct,
                        e_banc.value or "¿?",
                        e_contacto.value or "",
                    )
                    ui.notify(f"Cliente '{e_nombre.value}' creado.", type="positive")
                else:
                    db.actualizar_cliente(
                        fila["ID_Cliente"],
                        nombre=e_nombre.value or "",
                        nit=e_nit.value or "",
                        telefono=e_tel.value or "",
                        notas=e_notas.value or "",
                        rubro=e_rubro.value or "",
                        pct_venta=pct,
                        bancarizado=e_banc.value or "¿?",
                        contacto=e_contacto.value or "",
                    )
                    ui.notify("Cliente actualizado.", type="positive")
                dialogo.close()
                refrescar()

            e_nombre.on("keydown.enter", _guardar)
        dialogo.open()

    def _eliminar_cli(fila, refrescar):
        if not fila:
            ui.notify("Seleccioná una fila de la tabla.", type="warning")
            return

        def accion():
            db.eliminar_cliente(fila["Nombre_Razon_Social"])
            ui.notify("Cliente eliminado.", type="positive")
            refrescar()

        confirmar(f"¿Eliminar el cliente '{fila['Nombre_Razon_Social']}'?", accion, "Eliminar")

    with ui.row().classes("w-full items-center"):
        ui.label("Clientes (a quienes se les vende el crédito)").classes("font-semibold")
    pintar()
