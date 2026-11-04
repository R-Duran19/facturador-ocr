"""Pagos a proveedores: cuánto se les debe, qué se pagó y qué falta."""

from nicegui import ui

import db
from webui.componentes import confirmar, input_fecha, tabla_con_busqueda
from webui.plantilla import pagina

METODOS = ["Efectivo", "QR", "Transferencia", "Otro"]

COLUMNAS_RESUMEN = [
    {"name": "proveedor", "label": "Proveedor", "field": "proveedor", "align": "left"},
    {"name": "facturas", "label": "Facturas", "field": "facturas", "align": "center"},
    {"name": "a_pagar", "label": "A Pagar", "field": "a_pagar", "align": "right"},
    {"name": "pagado", "label": "Pagado", "field": "pagado", "align": "right"},
    {"name": "saldo", "label": "Saldo", "field": "saldo", "align": "right"},
    {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
]


@pagina("/pagos")
def pagina_pagos():
    meses = sorted(set(db.listar_meses()), reverse=True) or ["—"]

    with ui.row().classes("w-full items-end gap-3"):
        sel_mes = ui.select(meses, value=meses[0], label="Mes", on_change=lambda: _todo()).classes("w-56")

    cont_resumen = ui.column().classes("w-full gap-2")
    seleccion = {"proveedor": None}
    estado = {"nombre": None}

    def _totales():
        datos = db.resumen_pagos_proveedores(sel_mes.value)
        return (
            sum(d["A_Pagar"] for d in datos),
            sum(d["Pagado"] for d in datos),
            sum(d["Saldo"] for d in datos),
        )

    def _todo():
        a_pagar, pagado, saldo = _totales()
        with cont_resumen:
            pass
        cont_resumen.clear()
        with cont_resumen:
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm"):
                for etiqueta, valor, destacado in [
                    ("A pagar a proveedores", a_pagar, False),
                    ("Pagado", pagado, False),
                    ("Falta pagar", saldo, True),
                ]:
                    with ui.column().classes("gap-0 min-w-[130px]"):
                        ui.label(f"{valor:,.2f}").classes("text-lg font-bold" + (" text-negative" if destacado else ""))
                        ui.label(etiqueta).classes("text-[11px] opacity-50")

            datos = db.resumen_pagos_proveedores(sel_mes.value)
            if not datos:
                ui.label("Sin compras de proveedores en este mes.").classes("opacity-50")
            else:
                filas = [
                    {
                        **d,
                        "proveedor": d["Proveedor"],
                        "a_pagar": f"{d['A_Pagar']:,.2f}",
                        "pagado": f"{d['Pagado']:,.2f}",
                        "saldo": f"{d['Saldo']:,.2f}",
                    }
                    for d in datos
                ]
                tabla_con_busqueda(
                    COLUMNAS_RESUMEN,
                    filas,
                    "Proveedor",
                    seleccion_handler=lambda e: seleccion.update({"proveedor": e.selection[0] if e.selection else None}),
                )
                ui.button(
                    "Ver detalle del seleccionado",
                    icon="receipt_long",
                    on_click=lambda: _detalle_guardia(),
                ).props("unelevated")
        estado["nombre"] = None
        cont_detalle.clear()
        with cont_detalle:
            ui.label("Seleccioná un proveedor de la tabla para ver facturas y registrar pagos.").classes("opacity-50")

    def _detalle_guardia():
        if not seleccion["proveedor"]:
            ui.notify("Seleccioná un proveedor en la tabla.", type="warning")
            return
        _detalle(seleccion["proveedor"])

    cont_detalle = ui.column().classes("w-full gap-3")

    def _detalle(proveedor: str):
        estado["nombre"] = proveedor
        cont_detalle.clear()
        with cont_detalle:
            resumen = next(
                (d for d in db.resumen_pagos_proveedores(sel_mes.value) if d["Proveedor"] == proveedor), None
            )
            facturas = [f for f in db.leer_facturas_mes(sel_mes.value) if f["Proveedor_Asignado"] == proveedor]
            pagos = db.leer_pagos_proveedor(proveedor=proveedor, mes=sel_mes.value)

            with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
                ui.label(f"{proveedor} — {sel_mes.value}").classes("text-lg font-bold")
                with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm"):
                    for etiqueta, valor in [
                        ("Facturas", str(resumen["Facturas"] if resumen else 0)),
                        ("A pagar", resumen["A_Pagar"] if resumen else 0.0),
                        ("Pagado", resumen["Pagado"] if resumen else 0.0),
                        ("Saldo", resumen["Saldo"] if resumen else 0.0),
                    ]:
                        with ui.column().classes("gap-0 min-w-[120px]"):
                            ui.label(f"{valor:,.2f}" if isinstance(valor, float) else valor).classes("text-lg font-bold")
                            ui.label(etiqueta).classes("text-[11px] opacity-50")

                if facturas:
                    ui.label("Facturas del lote").classes("font-semibold text-sm q-mt-sm")
                    ui.table(
                        columns=[
                            {"name": "nro", "label": "N° Factura", "field": "Nro_Factura", "align": "left"},
                            {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
                            {"name": "pct", "label": "% Compra", "field": "pct", "align": "right"},
                            {"name": "apagar", "label": "A pagar", "field": "apagar", "align": "right"},
                        ],
                        rows=[
                            {
                                "Nro_Factura": f["Nro_Factura"] or "-",
                                "monto": f"{f['Monto_Total']:,.2f}",
                                "pct": f"{f.get('Porcentaje_Compra') or 0:g}%",
                                "apagar": f"{f['Monto_Total'] * (f.get('Porcentaje_Compra') or 0) / 100:,.2f}",
                            }
                            for f in facturas
                        ],
                        row_key="Nro_Factura",
                        pagination=10,
                    ).props("flat dense bordered")

            ui.label("Pagos registrados").classes("font-semibold text-sm q-mt-sm")
            cont_pagos = ui.column().classes("w-full gap-2")

            def pintar_pagos():
                cont_pagos.clear()
                with cont_pagos:
                    pagos = db.leer_pagos_proveedor(proveedor=proveedor, mes=sel_mes.value)
                    if pagos:
                        ui.table(
                            columns=[
                                {"name": "fecha", "label": "Fecha", "field": "Fecha", "align": "left"},
                                {"name": "monto", "label": "Monto", "field": "Monto", "align": "right"},
                                {"name": "metodo", "label": "Método", "field": "Metodo", "align": "center"},
                                {"name": "nota", "label": "Nota", "field": "Nota", "align": "left"},
                            ],
                            rows=[
                                {
                                    "ID_Pago": p["ID_Pago"],
                                    "Fecha": p["Fecha"],
                                    "Monto": f"{p['Monto']:,.2f}",
                                    "Metodo": p["Metodo"] or "—",
                                    "Nota": p["Nota"],
                                }
                                for p in pagos
                            ],
                            row_key="ID_Pago",
                            selection="single",
                            pagination=6,
                            on_select=lambda e: sel_pago.update({"id": e.selection[0]["ID_Pago"] if e.selection else None}),
                        ).props("flat dense bordered")
                        ui.button(
                            "Eliminar pago seleccionado",
                            icon="delete",
                            on_click=lambda: _eliminar_pago(),
                        ).props("flat color=negative dense")
                    else:
                        ui.label("Sin pagos registrados a este proveedor en el mes.").classes("text-sm opacity-50")

            sel_pago = {"id": None}

            def _eliminar_pago():
                if not sel_pago["id"]:
                    ui.notify("Seleccioná un pago de la tabla.", type="warning")
                    return
                db.eliminar_pago_proveedor(sel_pago["id"])
                ui.notify("Pago eliminado.", type="positive")
                _todo()
                _detalle(proveedor)

            pintar_pagos()

            with ui.card().classes("w-full bg-gray-100 dark:bg-gray-800"):
                ui.label("Registrar pago").classes("font-semibold")
                with ui.row().classes("w-full flex-wrap items-end gap-2"):
                    f_pago = input_fecha("Fecha del pago")
                    m_pago = ui.number(
                        "Monto", value=(resumen["Saldo"] if resumen else 0.0), format="%.2f"
                    )
                    met_pago = ui.select(METODOS, value="Efectivo", label="Método", new_value_mode="add").classes("w-40")
                    n_pago = ui.input("Nota")
                    ui.button("Registrar pago", icon="payments", on_click=lambda: _registrar_pago()).props("unelevated dense")

            def _registrar_pago():
                if not m_pago.value or m_pago.value <= 0:
                    ui.notify("Monto inválido.", type="warning")
                    return
                db.registrar_pago_proveedor(
                    proveedor, sel_mes.value, m_pago.value, (f_pago.value or "").strip() or None, met_pago.value or "", n_pago.value or ""
                )
                ui.notify("Pago registrado.", type="positive")
                _todo()
                _detalle(proveedor)

    _todo()
