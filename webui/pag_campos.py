"""Configuración de campos: activar, pedir a la IA, agregar, eliminar, editar."""

from nicegui import ui

import db
from webui.componentes import confirmar
TIPOS = ["texto", "numero", "fecha", "booleano"]


def seccion_campos():
    ui.label(
        "Define qué datos se guardan de cada factura y cuáles le pide la IA a Gemini. "
        "Desactivar un campo NO borra su historial, solo lo oculta. "
        "Los campos de núcleo no se pueden eliminar (el sistema los usa)."
    ).classes("text-sm opacity-60")

    cont = ui.column().classes("w-full gap-2")

    def pintar():
        cont.clear()
        with cont:
            campos = db.listar_campos()
            ui.table(
                columns=[
                    {"name": "clave", "label": "Clave", "field": "clave", "align": "left"},
                    {"name": "etiqueta", "label": "Etiqueta", "field": "etiqueta", "align": "left"},
                    {"name": "tipo", "label": "Tipo", "field": "tipo", "align": "center"},
                    {"name": "descripcion", "label": "Descripción IA", "field": "descripcion", "align": "left"},
                    {"name": "nucleo", "label": "Núcleo", "field": "nucleo", "align": "center"},
                    {"name": "activo", "label": "Activo", "field": "activo", "align": "center"},
                    {"name": "en_ia", "label": "Pedir a IA", "field": "en_ia", "align": "center"},
                    {"name": "orden", "label": "Orden", "field": "orden", "align": "center"},
                ],
                rows=[
                    {
                        **c,
                        "nucleo": "sí" if c["nucleo"] else "—",
                        "activo": "sí" if c["activo"] else "no",
                        "en_ia": "sí" if c["en_ia"] else "no",
                    }
                    for c in campos
                ],
                row_key="clave",
                selection="single",
                pagination={"rowsPerPage": 0},
                on_select=lambda e: sel.update(
                    {"clave": e.selection[0]["clave"] if e.selection else None}
                ),
            ).classes("w-full").props("flat dense bordered")

            sel_campo = {"clave": None}
            sel = sel_campo

            with ui.row().classes("w-full gap-2"):
                ui.button("Editar seleccionado", icon="edit", on_click=lambda: _editar(sel["clave"], pintar)).props("unelevated")
                ui.button(
                    "Eliminar seleccionado",
                    icon="delete",
                    on_click=lambda: _eliminar(sel["clave"], pintar),
                ).props("flat color=negative")

            ui.separator()
            with ui.card().classes("w-full"):
                ui.label("Agregar nuevo campo").classes("font-semibold")
                with ui.row().classes("w-full flex-wrap items-end gap-3"):
                    n_et = ui.input("Etiqueta visible").classes("w-64")
                    n_tipo = ui.select(TIPOS, value="texto", label="Tipo").classes("w-40")
                    n_desc = ui.input("Descripción para la IA").classes("w-96")
                    n_ia = ui.checkbox("Pedir a la IA", value=True)
                    ui.button("Agregar", icon="add", on_click=lambda: _agregar(n_et, n_tipo, n_desc, n_ia, pintar)).props("unelevated")

    def _editar(clave: str, refrescar):
        if not clave:
            ui.notify("Seleccioná un campo de la tabla.", type="warning")
            return
        campo = next((c for c in db.listar_campos() if c["clave"] == clave), None)
        if not campo:
            return
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[520px]"):
            ui.label(f"Campo: {campo['clave']}").classes("text-lg font-semibold")
            e_et = ui.input("Etiqueta", value=campo["etiqueta"])
            e_tipo = ui.select(TIPOS, value=campo["tipo"], label="Tipo")
            e_desc = ui.input("Descripción para la IA", value=campo["descripcion"]).classes("w-full")
            e_act = ui.checkbox("Activo", value=bool(campo["activo"]))
            e_ia = ui.checkbox("Pedir a la IA", value=bool(campo["en_ia"]))
            e_orden = ui.number("Orden", value=campo["orden"], step=1)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat")
                ui.button(
                    "Guardar",
                    icon="save",
                    on_click=lambda: (
                        db.actualizar_campo(
                            clave,
                            etiqueta=e_et.value,
                            tipo=e_tipo.value,
                            descripcion=e_desc.value or "",
                            activo=bool(e_act.value),
                            en_ia=bool(e_ia.value),
                            orden=int(e_orden.value or 0),
                        ),
                        dialogo.close(),
                        ui.notify("Campo actualizado.", type="positive"),
                        refrescar(),
                    ),
                ).props("unelevated")
        dialogo.open()

    def _eliminar(clave: str, refrescar):
        if not clave:
            ui.notify("Seleccioná un campo de la tabla.", type="warning")
            return
        campo = next((c for c in db.listar_campos() if c["clave"] == clave), None)
        if not campo:
            return
        if campo["nucleo"]:
            ui.notify("Los campos de núcleo no se pueden eliminar.", type="warning")
            return

        def accion():
            db.eliminar_campo(clave)
            ui.notify(f"Campo '{clave}' eliminado.", type="positive")
            refrescar()

        confirmar(f"¿Eliminar el campo '{clave}'?", accion, "Eliminar")

    def _agregar(n_et, n_tipo, n_desc, n_ia, refrescar):
        if not (n_et.value or "").strip():
            ui.notify("La etiqueta es obligatoria.", type="warning")
            return
        clave = db.agregar_campo(n_et.value, n_tipo.value, n_desc.value or "", bool(n_ia.value))
        ui.notify(f"Campo '{clave}' agregado.", type="positive")
        n_et.set_value(None)
        n_desc.set_value(None)
        refrescar()

    pintar()


__all__ = ["seccion_campos"]
