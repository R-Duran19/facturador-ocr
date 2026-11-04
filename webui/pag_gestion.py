"""Gestión del mes: el explorador que replica la estructura de carpetas.

Mes › Proveedor › (Facturas con % compra y venta + Pagos)
Mes › Ventas completas › Cliente › (facturas de todos los proveedores + cobros + PDF)
Mes › Reportes finales (costos y ganancia / ventas completas)
"""

from datetime import date

from nicegui import ui

import db
import exportador
import pdf_reportes
import reportes
from webui.componentes import confirmar, input_fecha, tarjeta_metrica
from webui.plantilla import pagina

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

ESTADO_COLOR = {"PAGADO": "green", "COBRADO": "green", "PARCIAL": "orange", "PENDIENTE": "red"}


def _legible(nombre_mes: str) -> str:
    try:
        anio, num, _ = str(nombre_mes).split("_", 2)
        return f"{MESES_ES[int(num) - 1]} {anio}"
    except (ValueError, IndexError):
        return str(nombre_mes)


@pagina("/gestion")
def pagina_gestion():
    hoy = date.today()
    mes_hoy = f"{hoy.year}_{hoy.month:02d}_{MESES_ES[hoy.month - 1]}"
    meses = sorted(set(db.listar_meses()) | {mes_hoy}, reverse=True)

    estado = {"mes": mes_hoy if mes_hoy in meses else (meses[0] if meses else mes_hoy), "vista": "mes", "proveedor": None, "cliente": None}

    sel_mes = ui.select(
        meses,
        value=estado["mes"],
        label="Carpeta del mes",
        on_change=lambda e: (estado.update({"mes": e.value, "vista": "mes", "proveedor": None, "cliente": None}), pintar()),
    ).classes("w-56")
    breadcrumb = ui.row().classes("w-full items-center gap-1 text-sm")
    cont = ui.column().classes("w-full gap-4")

    def _mes():
        return estado["mes"]

    def _facturas():
        return db.leer_facturas_mes(_mes())

    def _ventas():
        return db.leer_ventas_mes(_mes())

    def _venta_de(factura: dict, ventas: list):
        vid = factura.get("Venta_ID") or ""
        return next((v for v in ventas if v["ID_Venta"] == vid), None)

    def _pct_venta_de(factura: dict, ventas: list) -> float:
        v = _venta_de(factura, ventas)
        if v and v["Monto_Nominal"]:
            return v["Precio_Cobrado"] / v["Monto_Nominal"] * 100.0
        return 5.0

    def pintar():
        breadcrumb.clear()
        cont.clear()
        with breadcrumb:
            ui.button(_legible(_mes()), on_click=lambda: _ir("mes")).props("flat dense no-caps")
            if estado["vista"] == "proveedor":
                ui.label("›")
                ui.button(estado["proveedor"], on_click=lambda: _ir("proveedor", estado["proveedor"])).props(
                    "flat dense no-caps color=primary"
                )
                ui.label("›")
                ui.label({"compra": "Facturas (compra y venta)", "pagos": "Pagos"}[estado.get("tab", "compra")]).classes("opacity-60")
            elif estado["vista"] == "cliente":
                ui.label("› Ventas completas ›")
                ui.label(estado["cliente"]).classes("text-primary font-semibold")
        with cont:
            if estado["vista"] == "mes":
                _vista_mes()
            elif estado["vista"] == "proveedor":
                _vista_proveedor(estado["proveedor"])
            elif estado["vista"] == "cliente":
                _vista_cliente(estado["cliente"])

    def _ir(vista, clave=None):
        estado["vista"] = vista
        estado["proveedor"] = clave if vista == "proveedor" else None
        estado["cliente"] = clave if vista == "cliente" else None
        pintar()

    def _ir_cliente(cliente):
        estado["vista"] = "cliente"
        estado["cliente"] = cliente
        pintar()

    # ============ VISTA MES: tarjetas de proveedores ============

    def _vista_mes():
        facturas = _facturas()
        ventas = _ventas()
        pagos = {d["Proveedor"]: d for d in db.resumen_pagos_proveedores(_mes())}

        if not facturas:
            ui.label("Este mes no tiene facturas todavía. Cargalas desde la portada.").classes("opacity-50")
        else:
            ui.label("📁 Proveedores (quién trajo las facturas)").classes("font-semibold text-lg")
            with ui.row().classes("w-full flex-wrap gap-3"):
                por_prov = {}
                for f in facturas:
                    p = por_prov.setdefault(f["Proveedor_Asignado"] or "Sin Asignar", {"facturas": [], "nominal": 0.0})
                    p["facturas"].append(f)
                    p["nominal"] += f["Monto_Total"]
                for proveedor in sorted(por_prov):
                    d = por_prov[proveedor]
                    pg = pagos.get(proveedor, {"A_Pagar": 0.0, "Pagado": 0.0, "Saldo": 0.0, "Estado": "PENDIENTE"})
                    with ui.card().classes("cursor-pointer min-w-[230px] flex-1 border-2").style(
                        "border-color: var(--q-primary);"
                    ).on("click", lambda p=proveedor: _ir("proveedor", p)):
                        with ui.row().classes("items-center gap-2 w-full"):
                            ui.icon("folder", color="primary").classes("text-3xl")
                            ui.label(proveedor).classes("font-bold text-md")
                            ui.space()
                            ui.badge(pg["Estado"], color=ESTADO_COLOR.get(pg["Estado"], "grey")).props("text-color=white")
                        ui.label(f"{len(d['facturas'])} facturas · Bs {d['nominal']:,.0f} facturado").classes("text-xs opacity-60")
                        ui.label(f"A pagarle: Bs {pg['A_Pagar']:,.2f}").classes("text-xs")
                        ui.label(f"Pagado: Bs {pg['Pagado']:,.2f} · Saldo: Bs {pg['Saldo']:,.2f}").classes(
                            "text-xs opacity-70"
                        )

        ui.separator()
        ui.label("📁 Ventas completas (por cliente — para gestionar cobros)").classes("font-semibold text-lg")
        con_saldo = sorted({v["Cliente_Razon_Social"] for v in ventas}, key=str.lower)
        if not con_saldo:
            ui.label("Sin ventas este mes.").classes("opacity-50")
        else:
            with ui.row().classes("w-full flex-wrap gap-3"):
                for cliente in con_saldo:
                    sus = [v for v in ventas if v["Cliente_Razon_Social"] == cliente]
                    nominal = sum(v["Monto_Nominal"] for v in sus)
                    cobrar = sum(v["Precio_Cobrado"] for v in sus)
                    saldo = sum(v["Saldo"] for v in sus)
                    est = next((v["Estado_Cobro"] for v in sus if v["Saldo"] > 0.005), "COBRADO")
                    with ui.card().classes("cursor-pointer min-w-[230px] flex-1 border-2").style(
                        "border-color: var(--q-primary);"
                    ).on("click", lambda c=cliente: _ir_cliente(c)):
                        with ui.row().classes("items-center gap-2 w-full"):
                            ui.icon("business", color="primary").classes("text-3xl")
                            ui.label(cliente).classes("font-bold text-md")
                            ui.space()
                            ui.badge(est, color=ESTADO_COLOR.get(est, "grey")).props("text-color=white")
                        ui.label(f"{len(sus)} venta(s) · Bs {nominal:,.0f} facturado").classes("text-xs opacity-60")
                        ui.label(f"A cobrar: Bs {cobrar:,.2f} · Saldo: Bs {saldo:,.2f}").classes("text-xs opacity-70")

        ui.separator()
        _seccion_reportes()

    # ============ VISTA PROVEEDOR: UNA tabla con ambos % ============

    def _vista_proveedor(proveedor: str):
        facturas = [f for f in _facturas() if f["Proveedor_Asignado"] == proveedor]
        ventas = _ventas()

        with ui.card().classes("w-full"):
            ui.label(f"📄 Facturas que trajo {proveedor} — compra y venta en una sola tabla").classes(
                "font-semibold"
            )
            ui.label(
                "Monto × % compra = lo que se le PAGA al proveedor · Monto × % venta = lo que se le COBRA al cliente/comprador"
            ).classes("text-xs opacity-50")
            if not facturas:
                ui.label("Sin facturas de este proveedor en el mes.").classes("opacity-50")
                return

            anchos = [12, 12, 14, 14, 10, 10, 16, 10, 10, 16, 16, 14]
            encabezado = ["Fecha", "NIT", "Factura N", "Destino", "%Comp", "%Vta", "Monto", "A pagar", "A cobrar", "Utilidad", "Estado pago", "Venta"]
            pdf = ui.table(
                columns=[
                    {"name": c[0], "label": c[1], "field": c[0], "align": "left" if i < 3 else "right"}
                    for i, c in enumerate(
                        [
                            ("fecha", "Fecha"),
                            ("nit", "NIT"),
                            ("factura", "Factura N"),
                            ("destino", "Cliente"),
                            ("pct_c", "% Comp"),
                            ("pct_v", "% Vta"),
                            ("monto", "Monto"),
                            ("apagar", "A pagar"),
                            ("acobrar", "A cobrar"),
                            ("utilidad", "Utilidad"),
                            ("estado", "Estado pago"),
                            ("venta", "Venta"),
                        ]
                    )
                ],
                rows=[],
                row_key="ID",
                selection="single",
                pagination={"rowsPerPage": 0},
                on_select=lambda e: _abrir_factura(
                    next((f for f in facturas if f["ID"] == (e.selection[0]["ID"] if e.selection else None)), None),
                    proveedor,
                ),
            ).classes("w-full").props("flat dense bordered")

            filas = []
            tot_monto = tot_pagar = tot_cobrar = tot_util = 0.0
            for f in facturas:
                v = _venta_de(f, ventas)
                destino = v["Cliente_Razon_Social"] if v else "—"
                pct_c = float(f.get("Porcentaje_Compra") or 0)
                pct_v = _pct_venta_de(f, ventas)
                a_pagar = f["Monto_Total"] * pct_c / 100.0
                a_cobrar = f["Monto_Total"] * pct_v / 100.0
                tot_monto += f["Monto_Total"]
                tot_pagar += a_pagar
                tot_cobrar += a_cobrar
                tot_util += a_cobrar - a_pagar
                filas.append(
                    {
                        "ID": f["ID"],
                        "fecha": f["Fecha_Emision"] or "-",
                        "nit": f["NIT_Emisor"] or "-",
                        "factura": f["Nro_Factura"] or "-",
                        "destino": destino,
                        "pct_c": f"{pct_c:g}%",
                        "pct_v": f"{pct_v:g}%",
                        "monto": f"{f['Monto_Total']:,.2f}",
                        "apagar": f"{a_pagar:,.2f}",
                        "acobrar": f"{a_cobrar:,.2f}",
                        "utilidad": f"{a_cobrar - a_pagar:,.2f}",
                        "estado": f["Estado_Pago"],
                        "venta": (v["Estado_Cobro"] if v else "sin venta"),
                    }
                )
            filas.append(
                {
                    "ID": "__tot__",
                    "fecha": "TOTALES",
                    "nit": "",
                    "factura": "",
                    "destino": "",
                    "pct_c": "",
                    "pct_v": "",
                    "monto": f"{tot_monto:,.2f}",
                    "apagar": f"{tot_pagar:,.2f}",
                    "acobrar": f"{tot_cobrar:,.2f}",
                    "utilidad": f"{tot_util:,.2f}",
                    "estado": "",
                    "venta": "",
                }
            )
            pdf.update_rows(filas)
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                ui.label(f"Facturado: Bs {tot_monto:,.2f}")
                ui.label(f"A pagarle: Bs {tot_pagar:,.2f}").classes("text-negative font-semibold")
                ui.label(f"A cobrar: Bs {tot_cobrar:,.2f}").classes("text-primary font-semibold")
                ui.label(f"Utilidad: Bs {tot_util:,.2f}").classes("font-bold")

        pg = next((d for d in db.resumen_pagos_proveedores(_mes()) if d["Proveedor"] == proveedor), None)
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-2 w-full"):
                ui.icon("payments")
                ui.label(f"Pagos a {proveedor}").classes("font-semibold")
                ui.space()
                if pg:
                    ui.badge(pg["Estado"], color=ESTADO_COLOR.get(pg["Estado"], "grey")).props("text-color=white")
            if pg:
                with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                    ui.label(f"A pagar: Bs {pg['A_Pagar']:,.2f}")
                    ui.label(f"Pagado: Bs {pg['Pagado']:,.2f}")
                    ui.label(f"Saldo: Bs {pg['Saldo']:,.2f}").classes("font-bold")
            _seccion_pagos_proveedor(proveedor)

    def _seccion_pagos_proveedor(proveedor: str):
        pagos = db.leer_pagos_proveedor(proveedor=proveedor, mes=_mes())
        resumen = next((d for d in db.resumen_pagos_proveedores(_mes()) if d["Proveedor"] == proveedor), None)
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
                pagination=5,
                on_select=lambda e: sel_pago.update({"id": e.selection[0]["ID_Pago"] if e.selection else None}),
            ).props("flat dense bordered")
        else:
            ui.label("Sin pagos registrados.").classes("text-sm opacity-50")
        sel_pago = {"id": None}

        def _eliminar_pago():
            if not sel_pago["id"]:
                ui.notify("Seleccioná un pago.", type="warning")
                return
            db.eliminar_pago_proveedor(sel_pago["id"])
            ui.notify("Pago eliminado.", type="positive")
            pintar()

        ui.button("Eliminar pago seleccionado", icon="delete", on_click=_eliminar_pago).props("flat color=negative dense")

        with ui.row().classes("w-full flex-wrap items-end gap-2"):
            f_pago = input_fecha("Fecha del pago")
            m_pago = ui.number("Monto", value=(resumen["Saldo"] if resumen else 0.0), format="%.2f")
            met_pago = ui.select(["Efectivo", "QR", "Transferencia", "Otro"], value="Efectivo", label="Método", new_value_mode="add").classes("w-40")
            n_pago = ui.input("Nota")
            ui.button(
                "Registrar pago",
                icon="payments",
                on_click=lambda: _registrar_pago(proveedor, f_pago, m_pago, met_pago, n_pago),
            ).props("unelevated dense")

    def _registrar_pago(proveedor, f_pago, m_pago, met_pago, n_pago):
        if not m_pago.value or m_pago.value <= 0:
            ui.notify("Monto inválido.", type="warning")
            return
        db.registrar_pago_proveedor(proveedor, _mes(), m_pago.value, (f_pago.value or "").strip() or None, met_pago.value or "", n_pago.value or "")
        ui.notify("Pago registrado.", type="positive")
        pintar()

    def _abrir_factura(registro, proveedor):
        if not registro:
            ui.notify("Seleccioná una fila.", type="warning")
            return
        from webui.pag_facturas import dialogo_factura

        dialogo_factura(registro, lambda: pintar())

    # ============ VISTA CLIENTE (ventas completas) ============

    def _vista_cliente(cliente: str):
        ventas = [v for v in _ventas() if v["Cliente_Razon_Social"] == cliente]
        ids = set()
        for v in ventas:
            ids |= {i.strip() for i in v["Facturas_IDs"].split(",") if i.strip()}
        facturas = [f for f in _facturas() if f["ID"] in ids]
        facturas.sort(key=lambda f: (f["Fecha_Emision"], f["Nro_Factura"]))

        nominal = sum(f["Monto_Total"] for f in facturas)
        cobrar = sum(v["Precio_Cobrado"] for v in ventas)
        cobrado = sum(v["Total_Cobrado"] for v in ventas)
        saldo = round(cobrar - cobrado, 2)
        est = next((v["Estado_Cobro"] for v in ventas if v["Saldo"] > 0.005), "COBRADO")

        with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("business", color="primary").classes("text-3xl")
                ui.label(cliente).classes("text-lg font-bold")
                ui.space()
                ui.badge(est, color=ESTADO_COLOR.get(est, "grey")).props("text-color=white")
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                ui.label(f"Facturas: {len(facturas)}")
                ui.label(f"Facturado: Bs {nominal:,.2f}")
                ui.label(f"A cobrar: Bs {cobrar:,.2f}").classes("font-semibold")
                ui.label(f"Cobrado: Bs {cobrado:,.2f}")
                ui.label(f"Saldo: Bs {saldo:,.2f}").classes("font-bold")

            if facturas:
                anchos = [16, 16, 16, 14, 14, 16]
                ui.table(
                    columns=[
                        {"name": c[0], "label": c[1], "field": c[0], "align": "left" if i < 3 else "right"}
                        for i, c in enumerate(
                            [("fecha", "Fecha"), ("proveedor", "Proveedor"), ("factura", "Factura N"), ("monto", "Monto"), ("pct", "%"), ("acobrar", "A cobrar")]
                        )
                    ],
                    rows=[
                        {
                            "fecha": f["Fecha_Emision"] or "-",
                            "proveedor": f["Proveedor_Asignado"],
                            "factura": f["Nro_Factura"] or "-",
                            "monto": f"{f['Monto_Total']:,.2f}",
                            "pct": f"{(_pct_venta_de(f, ventas)):g}%",
                            "acobrar": f"{f['Monto_Total'] * _pct_venta_de(f, ventas) / 100:,.2f}",
                        }
                        for f in facturas
                    ],
                    row_key="factura",
                    pagination=12,
                ).classes("w-full").props("flat dense bordered")

            with ui.row().classes("w-full gap-2 q-mt-sm"):
                ui.button(
                    "📄 PDF de la empresa",
                    icon="picture_as_pdf",
                    on_click=lambda: _descargar_pdf_empresa(cliente),
                ).props("unelevated dense")

        ui.label("Cobros registrados").classes("font-semibold text-sm q-mt-sm")
        cont_cobros = ui.column().classes("w-full gap-2")
        sel_cobro = {"id": None}

        def pintar_cobros():
            cont_cobros.clear()
            with cont_cobros:
                cobros = [c for v in ventas for c in db.leer_cobros(v["ID_Venta"])]
                if cobros:
                    ui.table(
                        columns=[
                            {"name": "fecha", "label": "Fecha", "field": "Fecha", "align": "left"},
                            {"name": "venta", "label": "Venta", "field": "Venta", "align": "left"},
                            {"name": "monto", "label": "Monto", "field": "Monto", "align": "right"},
                            {"name": "metodo", "label": "Método", "field": "Metodo", "align": "center"},
                        ],
                        rows=[
                            {
                                "ID_Cobro": c["ID_Cobro"],
                                "Fecha": c["Fecha"],
                                "Venta": c["Venta_ID"],
                                "Monto": f"{c['Monto']:,.2f}",
                                "Metodo": c.get("Metodo", "") or "—",
                            }
                            for c in cobros
                        ],
                        row_key="ID_Cobro",
                        selection="single",
                        pagination=8,
                        on_select=lambda e: sel_cobro.update({"id": e.selection[0]["ID_Cobro"] if e.selection else None}),
                    ).props("flat dense bordered")
                    ui.button("Eliminar cobro seleccionado", icon="delete", on_click=lambda: _eliminar_cobro(ventas)).props(
                        "flat color=negative dense"
                    )
                else:
                    ui.label("Sin cobros registrados.").classes("text-sm opacity-50")

        def _eliminar_cobro(ventas):
            if not sel_cobro["id"]:
                ui.notify("Seleccioná un cobro.", type="warning")
                return
            db.eliminar_cobro(sel_cobro["id"])
            ui.notify("Cobro eliminado.", type="positive")
            pintar()

        pintar_cobros()

        with ui.card().classes("w-full bg-gray-100 dark:bg-gray-800"):
            ui.label("Registrar cobro").classes("font-semibold")
            with ui.row().classes("w-full flex-wrap items-end gap-2"):
                f_c = input_fecha("Fecha")
                m_c = ui.number("Monto", value=saldo, format="%.2f")
                met_c = ui.select(["QR", "Efectivo", "Transferencia", "Otro"], value="QR", label="Método", new_value_mode="add").classes("w-36")
                n_c = ui.input("Nota")
                venta_sel_ui = ui.select(
                    {v["ID_Venta"]: f"Venta {v['ID_Venta']} (Bs {v['Saldo']:,.2f})" for v in ventas if v["Saldo"] > 0.005}
                    or {"": "Todas cobradas"},
                    value=(next((v["ID_Venta"] for v in ventas if v["Saldo"] > 0.005), "")),
                    label="Aplicar a venta",
                ).classes("w-56")
                ui.button("Registrar cobro", icon="payments", on_click=lambda: _registrar()).props("unelevated dense")

        def _registrar():
            if not venta_sel_ui.value:
                ui.notify("Todas las ventas de este cliente están cobradas.", type="info")
                return
            if not m_c.value or m_c.value <= 0:
                ui.notify("Monto inválido.", type="warning")
                return
            db.registrar_cobro(venta_sel_ui.value, m_c.value, (f_c.value or "").strip() or None, n_c.value or "", met_c.value or "")
            ui.notify("Cobro registrado.", type="positive")
            pintar()

    def _descargar_pdf_empresa(cliente: str):
        datos = pdf_reportes.pdf_empresa(cliente, _mes())
        ui.download(datos, filename=f"{cliente} - {_mes()}.pdf")
        ui.notify("PDF generado.", type="positive")

    # ============ REPORTES FINALES (al pie, siempre) ============

    def _seccion_reportes():
        ui.label("📊 Reportes finales del mes").classes("font-semibold text-lg")
        with ui.row().classes("w-full flex-wrap gap-2"):
            ui.button("Excel de control", icon="table_view", on_click=lambda: _excel()).props("flat")
            ui.button("PDF resumen", icon="picture_as_pdf", on_click=lambda: _pdf_res()).props("flat")
            ui.button("PDFs por empresa (.zip)", icon="folder_zip", on_click=lambda: _pdf_zip()).props("unelevated")

        def _excel():
            datos, nombre = exportador.exportar_reportes_mes(_mes())
            ui.download(datos, filename=nombre)
            ui.notify("Excel generado.", type="positive")

        def _pdf_res():
            ui.download(pdf_reportes.pdf_resumen_mes(_mes()), filename=f"control {_mes()}.pdf")
            ui.notify("PDF generado.", type="positive")

        def _pdf_zip():
            datos, nombre = pdf_reportes.pdfs_por_empresa_zip(_mes())
            ui.download(datos, filename=nombre)
            ui.notify(f"{nombre} generado.", type="positive")

        costos = reportes.resumen_costos_ganancia(_mes())
        anchos = [38, 60, 32, 18, 30, 18, 32, 32]
        if costos:
            ui.table(
                columns=[
                    {"name": c[0], "label": c[1], "field": c[0], "align": "left" if i < 2 else "right"}
                    for i, c in enumerate(
                        [
                            ("proveedor", "Proveedor"),
                            ("cliente", "Cliente"),
                            ("facturado", "Total Facturado"),
                            ("pctc", "% Comp"),
                            ("compra", "Compra"),
                            ("pctv", "% Venta"),
                            ("venta", "Venta"),
                            ("utilidad", "Utilidad"),
                        ]
                    )
                ],
                rows=[
                    {
                        **f,
                        "proveedor": f["Proveedor"],
                        "cliente": f["Cliente"],
                        "facturado": f"{f['Total_Facturado']:,.2f}",
                        "pctc": f"{f['Pct_Compra']:g}%",
                        "compra": f"{f['Compra']:,.2f}",
                        "pctv": f"{f['Pct_Venta']:g}%",
                        "venta": f"{f['Venta']:,.2f}",
                        "utilidad": f"{f['Utilidad']:,.2f}",
                    }
                    for f in costos
                ]
                + [
                    {
                        "proveedor": "TOTALES",
                        "cliente": "",
                        "facturado": f"{sum(f['Total_Facturado'] for f in costos):,.2f}",
                        "pctc": "",
                        "compra": f"{sum(f['Compra'] for f in costos):,.2f}",
                        "pctv": "",
                        "venta": f"{sum(f['Venta'] for f in costos):,.2f}",
                        "utilidad": f"{sum(f['Utilidad'] for f in costos):,.2f}",
                    }
                ],
                row_key="Cliente",
                pagination=20,
            ).classes("w-full").props("flat dense bordered")
        else:
            ui.label("Sin datos para el reporte de costos.").classes("opacity-50")

        filas_v = reportes.resumen_ventas_cliente(_mes())
        if filas_v:
            ui.table(
                columns=[
                    {"name": c[0], "label": c[1], "field": c[0], "align": "left" if i < 2 else "right"}
                    for i, c in enumerate(
                        [
                            ("nro", "#"),
                            ("cliente", "Cliente"),
                            ("rubro", "Rubro"),
                            ("monto", "Monto"),
                            ("cobrar", "Cobrar"),
                            ("pct", "%"),
                            ("saldo", "Saldo"),
                            ("estado", "Estado"),
                        ]
                    )
                ],
                rows=[
                    {
                        **f,
                        "nro": str(f["Nro"]),
                        "cliente": f["Cliente"],
                        "rubro": f["Rubro"],
                        "monto": f"{f['Monto']:,.2f}",
                        "cobrar": f"{f['Cobrar']:,.2f}",
                        "pct": f"{f['Pct']:g}%",
                        "saldo": f"{f['Saldo']:,.2f}",
                        "estado": f["Estado"],
                    }
                    for f in filas_v
                ]
                + [
                    {
                        "nro": "",
                        "cliente": "TOTALES",
                        "rubro": "",
                        "monto": f"{sum(f['Monto'] for f in filas_v):,.2f}",
                        "cobrar": f"{sum(f['Cobrar'] for f in filas_v):,.2f}",
                        "pct": "",
                        "saldo": f"{sum(f['Saldo'] for f in filas_v):,.2f}",
                        "estado": "",
                    }
                ],
                row_key="Cliente",
                pagination=20,
            ).classes("w-full").props("flat dense bordered")

    pintar()
