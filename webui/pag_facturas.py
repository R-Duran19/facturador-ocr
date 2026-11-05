"""Búsqueda global de facturas: filtros instantáneos, edición, carga manual, export."""

import datetime as dt

from nicegui import ui

import config
import db
import exportador
from archivos import ruta_absoluta
from webui.componentes import confirmar
from webui.plantilla import pagina

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

CAMPOS_MONTO_UI = {"numero"}


def _mes_sugerido() -> str:
    hoy = dt.date.today()
    return f"{hoy.year}_{hoy.month:02d}_{MESES_ES[hoy.month - 1]}"


def dialogo_factura(registro: dict, refrescar, es_nueva: bool = False, mes_nueva: str = None):
    """Diálogo único de factura: editar existente o carga manual (es_nueva)."""
    proveedores = [p for p in db.leer_proveedores() if p != "Sin Asignar"]
    campos_todos = db.listar_campos()

    with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[760px]"):
        ui.label(
            "Nueva factura (carga manual)" if es_nueva else f"Editar factura {registro.get('ID', '')}"
        ).classes("text-lg font-semibold")
        e_mes = None
        if es_nueva:
            e_mes = ui.select(
                sorted(set(db.listar_meses()) | {mes_nueva or _mes_sugerido()}, reverse=True),
                value=mes_nueva or _mes_sugerido(),
                label="Mes de la factura",
                new_value_mode="add",
            ).classes("w-64")
        entradas = {}
        with ui.grid(columns=2).classes("w-full gap-2"):
            for c in campos_todos:
                k = c["clave"]
                if not c["activo"] or k == "ID":
                    continue
                if k == "Venta_ID":
                    ui.input("Venta", value=str(registro.get("Venta_ID") or "—")).props("disable")
                    continue
                etiqueta = c["etiqueta"]
                if k == "Estado_Pago":
                    entradas[k] = ui.select(
                        config.ESTADOS_PAGO, value=registro.get(k) or "PENDIENTE", label=etiqueta
                    ).classes("w-full")
                elif k == "Proveedor_Asignado":
                    entradas[k] = ui.select(
                        proveedores, value=registro.get(k) or None, label=etiqueta, new_value_mode="add"
                    ).classes("w-full")
                elif k == "Ruta_Archivo":
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.input("PDF", value=str(registro.get(k) or "—")).props("disable").classes("flex-1")
                        ruta = registro.get("Ruta_Archivo") or ""
                        if ruta and ruta_absoluta(ruta).exists():
                            ui.button(
                                icon="download",
                                on_click=lambda r=ruta: ui.download(str(ruta_absoluta(r)), filename=ruta_absoluta(r).name),
                            ).props("flat dense")
                        else:
                            ui.label("sin archivo").classes("text-xs opacity-40")
                elif c["tipo"] in CAMPOS_MONTO_UI:
                    try:
                        valor = float(registro.get(k) or 0)
                    except (TypeError, ValueError):
                        valor = 0.0
                    entradas[k] = ui.number(etiqueta, value=valor, format="%.2f")
                elif c["tipo"] == "booleano":
                    entradas[k] = ui.checkbox(etiqueta, value=bool(registro.get(k)))
                else:
                    entradas[k] = ui.input(etiqueta, value=str(registro.get(k) or ""))

        def _guardar():
            for k, entrada in entradas.items():
                registro[k] = entrada.value
            if es_nueva:
                registro["ID"] = ""
                if not (registro.get("Nro_Factura") or registro.get("Cod_Autorizacion")):
                    ui.notify("Cargá al menos N° de factura o código de autorización.", type="warning")
                    return
                db.registrar_facturas_batch(e_mes.value, [registro])
                ui.notify(f"Factura creada en {e_mes.value}.", type="positive")
            else:
                db.actualizar_factura(registro.get("Mes", ""), registro)
                ui.notify("Factura actualizada.", type="positive")
            dialogo.close()
            refrescar()

        with ui.row().classes("w-full justify-between"):
            if not es_nueva:
                with ui.row().classes("gap-2"):
                    ruta = registro.get("Ruta_Archivo") or ""
                    if ruta and ruta_absoluta(ruta).exists():
                        ui.button(
                            "PDF original",
                            icon="picture_as_pdf",
                            on_click=lambda: ui.download(str(ruta_absoluta(ruta)), filename=ruta_absoluta(ruta).name),
                        ).props("flat dense")
                    ui.button(
                        "Eliminar",
                        icon="delete",
                        on_click=lambda: (
                            dialogo.close(),
                            confirmar(
                                f"¿Eliminar la factura {registro.get('ID', '')}?",
                                lambda: _eliminar(registro, refrescar),
                                "Eliminar",
                            ),
                        ),
                    ).props("flat color=negative")
            else:
                ui.label("Se genera un ID automáticamente.").classes("text-xs opacity-50")
            with ui.row().classes("gap-2"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat")
                ui.button("Guardar", icon="save", on_click=_guardar).props("unelevated")
    dialogo.open()


def _eliminar(registro: dict, refrescar) -> None:
    db.eliminar_factura(registro.get("Mes", ""), registro["ID"])
    ui.notify("Factura eliminada.", type="positive")
    refrescar()


@pagina("/facturas")
def pagina_facturas():
    meses = ["TODOS"] + sorted(db.listar_meses(), reverse=True)
    proveedores = db.leer_proveedores()
    campos_todos = db.listar_campos()
    claves = [c["clave"] for c in campos_todos if c["activo"] and c["clave"] != "ID"]
    info_campos = {c["clave"]: c for c in campos_todos}

    contenedor = ui.column().classes("w-full gap-2")
    seleccion = {"registro": None}

    with ui.row().classes("w-full flex-wrap items-end gap-3"):
        f_mes = ui.select(meses, value="TODOS", label="Mes", on_change=lambda: refrescar()).classes("w-52")
        f_prov = ui.select(
            ["TODOS"] + sorted({p for p in proveedores if p}),
            value="TODOS",
            label="Proveedor",
            on_change=lambda: refrescar(),
        ).classes("w-56")
        f_estado = ui.select(
            ["TODOS"] + config.ESTADOS_PAGO, value="TODOS", label="Estado pago", on_change=lambda: refrescar()
        ).classes("w-44")
        f_texto = ui.input(
            "Buscar...", placeholder="N°, razón social, NIT...", on_change=lambda: refrescar()
        ).classes("w-64").props("clearable")
        ui.button("Exportar mes a Excel", icon="download", on_click=lambda: exportar()).props("flat")

    def filas_actuales():
        return db.leer_facturas_filtro(
            mes=None if f_mes.value == "TODOS" else f_mes.value,
            proveedor=None if f_prov.value == "TODOS" else f_prov.value,
            estado_pago=None if f_estado.value == "TODOS" else f_estado.value,
            texto=f_texto.value or None,
            limite=500,
        )

    def exportar():
        if f_mes.value == "TODOS":
            ui.notify("Elegí un mes concreto para exportar.", type="warning")
            return
        datos, nombre = exportador.exportar_mes_excel(f_mes.value)
        ui.download(datos, filename=nombre)
        ui.notify("Excel generado.", type="positive")

    def refrescar():
        contenedor.clear()
        rows, total = filas_actuales()
        with contenedor:
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm"):
                for etiqueta, valor in [
                    ("Facturas", f"{total}"),
                    ("Σ Monto", f"{sum(r['Monto_Total'] for r in rows):,.2f}"),
                    ("Σ Crédito Fiscal", f"{sum(r['Credito_Fiscal'] for r in rows):,.2f}"),
                    ("Vendidas", f"{len([r for r in rows if r.get('Venta_ID')])}"),
                ]:
                    with ui.column().classes("gap-0 min-w-[110px]"):
                        ui.label(str(valor)).classes("text-base font-bold")
                        ui.label(etiqueta).classes("text-[11px] opacity-50")
            if rows:
                filas = []
                for r in rows:
                    fila = {"ID": r["ID"]}
                    for k in claves:
                        v = r.get(k, "")
                        if info_campos.get(k, {}).get("tipo") == "numero":
                            try:
                                fila[k] = f"{float(v):,.2f}"
                            except (TypeError, ValueError):
                                fila[k] = str(v or "")
                        else:
                            fila[k] = str(v or "")
                    filas.append(fila)
                columnas = [{"name": "ID", "label": "ID", "field": "ID", "align": "left"}]
                for k in claves:
                    columnas.append(
                        {"name": k, "label": info_campos[k]["etiqueta"], "field": k, "align": "left"}
                    )
                ui.table(
                    columns=columnas,
                    rows=filas,
                    row_key="ID",
                    selection="single",
                    pagination={"rowsPerPage": 0},
                    on_select=lambda e: seleccion.update(
                        {"registro": e.selection[0] if e.selection else None}
                    ),
                ).classes("w-full").props("flat dense bordered")
            else:
                ui.label("Sin resultados.").classes("opacity-50")
        seleccion["registro"] = None

    def abrir_edicion():
        r_sel = seleccion["registro"]
        if not r_sel:
            ui.notify("Seleccioná una fila de la tabla.", type="warning")
            return
        registro = next(
            (x for x in db.leer_facturas_filtro(limite=10000)[0] if x["ID"] == r_sel["ID"]), None
        )
        if not registro:
            ui.notify("La factura ya no existe.", type="negative")
            return
        dialogo_factura(registro, refrescar)

    with ui.row().classes("w-full gap-2"):
        ui.button(
            "➕ Nueva factura (carga manual)",
            icon="post_add",
            on_click=lambda: dialogo_factura(
                {c["clave"]: (0.0 if c["tipo"] == "numero" else "") for c in campos_todos}
                | {"ID": "", "Venta_ID": ""},
                refrescar,
                es_nueva=True,
                mes_nueva=_mes_sugerido(),
            ),
        ).props("unelevated")
        ui.button("Editar seleccionada", icon="edit", on_click=abrir_edicion).props("flat")
        ui.button("Actualizar", icon="refresh", on_click=lambda: refrescar()).props("flat")

    refrescar()
