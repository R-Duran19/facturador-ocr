"""Reportes mensuales: réplica de los Excel de control del cliente."""

from nicegui import ui

import db
import exportador
import pdf_reportes
import reportes
from webui.componentes import tarjeta_metrica
from webui.plantilla import pagina

COLUMNAS_COSTOS = [
    {"name": "proveedor", "label": "Proveedor", "field": "Proveedor", "align": "left"},
    {"name": "cliente", "label": "Cliente", "field": "Cliente", "align": "left"},
    {"name": "facturado", "label": "Total Facturado", "field": "facturado", "align": "right"},
    {"name": "pct_c", "label": "% Compra", "field": "pct_c", "align": "right"},
    {"name": "compra", "label": "Compra", "field": "compra", "align": "right"},
    {"name": "pct_v", "label": "% Venta", "field": "pct_v", "align": "right"},
    {"name": "venta", "label": "Venta", "field": "venta", "align": "right"},
    {"name": "utilidad", "label": "Utilidad", "field": "utilidad", "align": "right"},
]

COLUMNAS_VENTAS = [
    {"name": "nro", "label": "#", "field": "Nro", "align": "center"},
    {"name": "cliente", "label": "Nombre", "field": "Cliente", "align": "left"},
    {"name": "rubro", "label": "Rubro", "field": "Rubro", "align": "center"},
    {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
    {"name": "cobrar", "label": "Cobrar", "field": "cobrar", "align": "right"},
    {"name": "pct", "label": "%", "field": "Pct", "align": "right"},
    {"name": "proveedor", "label": "Prov.", "field": "Proveedor", "align": "left"},
    {"name": "entregado", "label": "Entregado", "field": "Entregado", "align": "center"},
    {"name": "cobrado", "label": "Cobrado", "field": "cobrado", "align": "right"},
    {"name": "saldo", "label": "Saldo", "field": "saldo", "align": "right"},
    {"name": "estado", "label": "Estado", "field": "Estado", "align": "center"},
]


@pagina("/reportes")
def pagina_reportes():
    meses = sorted(set(db.listar_meses()), reverse=True) or ["—"]
    cont = ui.column().classes("w-full gap-4")

    ver_todo = {"valor": False}

    with ui.row().classes("w-full items-end gap-3"):
        sel_mes = ui.select(meses, value=meses[0], label="Mes del reporte", on_change=lambda: pintar()).classes("w-56")
        ui.checkbox("Incluir catálogo completo de clientes (con ceros)", on_change=lambda: pintar()).bind_value(
            ver_todo, "valor"
        )
        ui.space()
        ui.button("Actualizar", icon="refresh", on_click=lambda: pintar()).props("flat")
        ui.button("Excel de control", icon="table_view", on_click=lambda: _exportar()).props("flat")
        ui.button("PDF resumen", icon="picture_as_pdf", on_click=lambda: _pdf_resumen()).props("flat")
        ui.button("PDFs por empresa (.zip)", icon="folder_zip", on_click=lambda: _pdf_empresas()).props("unelevated")

    def _pdf_resumen():
        datos = pdf_reportes.pdf_resumen_mes(sel_mes.value)
        ui.download(datos, filename=f"control {sel_mes.value}.pdf")
        ui.notify("PDF generado.", type="positive")

    def _pdf_empresas():
        datos, nombre = pdf_reportes.pdfs_por_empresa_zip(sel_mes.value)
        ui.download(datos, filename=nombre)
        ui.notify(f"{nombre} generado.", type="positive")

    def _exportar():
        datos, nombre = exportador.exportar_reportes_mes(sel_mes.value, incluir_todos=ver_todo["valor"])
        ui.download(datos, filename=nombre)
        ui.notify("Excel de control generado.", type="positive")

    def pintar():
        cont.clear()
        with cont:
            costos = reportes.resumen_costos_ganancia(sel_mes.value)
            filas_v = reportes.resumen_ventas_cliente(sel_mes.value, incluir_todos=ver_todo["valor"])

            if costos:
                tot_fac = sum(f["Total_Facturado"] for f in costos)
                tot_compra = sum(f["Compra"] for f in costos)
                tot_venta = sum(f["Venta"] for f in costos)
                tot_util = sum(f["Utilidad"] for f in costos)
                pagos_prov = {d["Proveedor"]: d for d in db.resumen_pagos_proveedores(sel_mes.value)}
                pagado_prov = sum(d["Pagado"] for d in pagos_prov.values())
                falta_prov = sum(d["Saldo"] for d in pagos_prov.values())
                with ui.row().classes("w-full flex-wrap gap-3"):
                    tarjeta_metrica("Total Facturado", f"Bs {tot_fac:,.0f}", "receipt_long", "blue")
                    tarjeta_metrica("Compra del mes", f"Bs {tot_compra:,.0f}", "shopping_cart", "orange")
                    tarjeta_metrica("Venta a clientes", f"Bs {tot_venta:,.0f}", "sell", "teal")
                    tarjeta_metrica("Utilidad del mes", f"Bs {tot_util:,.0f}", "trending_up", "green")
                with ui.row().classes("w-full flex-wrap gap-3"):
                    tarjeta_metrica("Pagado a proveedores", f"Bs {pagado_prov:,.0f}", "payments", "blue-8")
                    tarjeta_metrica("Falta pagar a proveedores", f"Bs {falta_prov:,.0f}", "money_off", "red")
                    if filas_v:
                        tarjeta_metrica(
                            "Por cobrar a clientes", f"Bs {sum(f['Saldo'] for f in filas_v):,.0f}", "hourglass_top", "red"
                        )

                por_proveedor = {}
                for f in costos:
                    por_proveedor[f["Proveedor"]] = por_proveedor.get(f["Proveedor"], 0.0) + f["Utilidad"]
                ui.echart(
                    {
                        "tooltip": {"trigger": "axis"},
                        "grid": {"left": 70, "right": 20, "top": 20, "bottom": 50},
                        "xAxis": {
                            "type": "value",
                            "axisLabel": {"formatter": "{value} Bs"},
                        },
                        "yAxis": {"type": "category", "data": list(por_proveedor.keys())},
                        "series": [
                            {
                                "type": "bar",
                                "name": "Utilidad (Bs)",
                                "data": [round(v, 2) for v in por_proveedor.values()],
                                "itemStyle": {"color": "#175E3B", "borderRadius": [0, 4, 4, 0]},
                                "label": {"show": True, "position": "right", "formatter": "{c}"},
                            }
                        ],
                    }
                ).classes("w-full h-64")

            ui.label(f"📊 Resumen de costos y ganancia — {sel_mes.value}").classes("text-lg font-semibold")
            if costos:
                filas = [
                    {
                        **f,
                        "proveedor": f["Proveedor"],
                        "cliente": f["Cliente"],
                        "facturado": f"{f['Total_Facturado']:,.2f}",
                        "pct_c": f"{f['Pct_Compra']:g}%",
                        "compra": f"{f['Compra']:,.2f}",
                        "pct_v": f"{f['Pct_Venta']:g}%",
                        "venta": f"{f['Venta']:,.2f}",
                        "utilidad": f"{f['Utilidad']:,.2f}",
                    }
                    for f in costos
                ]
                filas.append(
                    {
                        "proveedor": "TOTALES",
                        "cliente": "",
                        "facturado": f"{sum(f['Total_Facturado'] for f in costos):,.2f}",
                        "pct_c": "",
                        "compra": f"{sum(f['Compra'] for f in costos):,.2f}",
                        "pct_v": "",
                        "venta": f"{sum(f['Venta'] for f in costos):,.2f}",
                        "utilidad": f"{sum(f['Utilidad'] for f in costos):,.2f}",
                    }
                )
                ui.table(columns=COLUMNAS_COSTOS, rows=filas, row_key="Cliente", pagination=30).classes(
                    "w-full"
                ).props("flat dense bordered")
            else:
                ui.label("Sin ventas en este mes.").classes("opacity-50")

            ui.separator()
            ui.label(f"💰 Ventas resumen — {sel_mes.value}").classes("text-lg font-semibold")
            if filas_v:
                filas = [
                    {
                        **f,
                        "nro": str(f["Nro"]),
                        "cliente": f["Cliente"],
                        "rubro": f["Rubro"],
                        "proveedor": f["Proveedor"],
                        "entregado": f["Entregado"] or "—",
                        "estado": f["Estado"],
                        "monto": f"{f['Monto']:,.2f}",
                        "cobrar": f"{f['Cobrar']:,.2f}",
                        "cobrado": f"{f['Cobrado']:,.2f}",
                        "saldo": f"{f['Saldo']:,.2f}",
                    }
                    for f in filas_v
                ]
                filas.append(
                    {
                        "nro": "",
                        "cliente": "TOTALES",
                        "rubro": "",
                        "monto": f"{sum(f['Monto'] for f in filas_v):,.2f}",
                        "cobrar": f"{sum(f['Cobrar'] for f in filas_v):,.2f}",
                        "pct": "",
                        "cobrado": f"{sum(f['Cobrado'] for f in filas_v):,.2f}",
                        "saldo": f"{sum(f['Saldo'] for f in filas_v):,.2f}",
                    }
                )
                ui.table(columns=COLUMNAS_VENTAS, rows=filas, row_key="Nro", pagination=30).classes(
                    "w-full"
                ).props("flat dense bordered")
            else:
                ui.label("Sin ventas en este mes.").classes("opacity-50")

            ui.separator()
            todas = db.leer_todas_compras()
            if todas:
                import pandas as pd

                df_anual = pd.DataFrame(todas)
                df_anual["Monto_Total"] = pd.to_numeric(df_anual["Monto_Total"], errors="coerce").fillna(0.0)
                serie = df_anual.groupby("Mes")["Monto_Total"].sum().round(2).tail(12).to_dict()
                ui.label("Compras por mes (histórico)").classes("text-md font-semibold")
                ui.echart(
                    {
                        "tooltip": {"trigger": "axis"},
                        "grid": {"left": 60, "right": 20, "top": 20, "bottom": 40},
                        "xAxis": {"type": "category", "data": list(serie.keys())},
                        "yAxis": {"type": "value"},
                        "series": [
                            {
                                "type": "bar",
                                "name": "Bs comprados",
                                "data": list(serie.values()),
                                "itemStyle": {"color": "#175E3B", "borderRadius": [4, 4, 0, 0]},
                            }
                        ],
                    }
                ).classes("w-full h-64")

    pintar()
