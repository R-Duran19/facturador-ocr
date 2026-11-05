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
from webui import nav, pdf_url
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
    meses = sorted(set(db.listar_meses()), reverse=True)

    estado = {"mes": meses[0] if meses else mes_hoy, "vista": "mes", "proveedor": None, "cliente": None}

    sel_mes = ui.select(
        meses,
        value=estado["mes"],
        label="Carpeta del mes",
        on_change=lambda e: (estado.update({"mes": e.value, "vista": "mes", "proveedor": None, "cliente": None}), pintar()),
    ).classes("w-56")
    breadcrumb = ui.row().classes("w-full items-center gap-1 text-sm")
    cont = ui.column().classes("w-full gap-4")

    nav.registrar("/gestion", mes=estado["mes"], vista="mes")
    _rest = nav.restaurar("/gestion")
    if _rest:
        if _rest.get("mes") and _rest["mes"] in meses:
            estado["mes"] = _rest["mes"]
            sel_mes.set_value(_rest["mes"])
        estado["vista"] = _rest.get("vista") or "mes"
        estado["proveedor"] = _rest.get("proveedor")
        estado["cliente"] = _rest.get("cliente")

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
            return round(v["Precio_Cobrado"] / v["Monto_Nominal"] * 100.0, 2)
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
        nav.registrar(
            "/gestion", mes=estado["mes"], vista=vista, proveedor=estado["proveedor"], cliente=estado["cliente"]
        )
        pintar()

    def _ir_cliente(cliente):
        estado["vista"] = "cliente"
        estado["cliente"] = cliente
        nav.registrar("/gestion", mes=estado["mes"], vista="cliente", proveedor=None, cliente=cliente)
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

            COLUMNAS_DETALLE = [
                ("nro", "#", "center"),
                ("fecha", "Fecha", "left"),
                ("nit", "NIT", "left"),
                ("factura", "Factura N", "left"),
                ("destino", "Cliente", "left"),
                ("pct_c", "% Comp", "right"),
                ("pct_v", "% Vta", "right"),
                ("monto", "Monto", "right"),
                ("apagar", "A pagar", "right"),
                ("acobrar", "A cobrar", "right"),
                ("utilidad", "Utilidad", "right"),
                ("estado", "Estado pago", "center"),
                ("venta", "Venta", "center"),
            ]
            COLUMNAS_COMPACTO = [
                ("cliente", "Cliente", "left"),
                ("n", "Facturas", "center"),
                ("pct_c", "% Comp", "right"),
                ("pct_v", "% Vta", "right"),
                ("monto", "Monto", "right"),
                ("apagar", "A pagar", "right"),
                ("acobrar", "A cobrar", "right"),
                ("utilidad", "Utilidad", "right"),
                ("estado", "Estado pago", "center"),
                ("venta", "Venta", "center"),
            ]

            def _datos_factura(f):
                v = _venta_de(f, ventas)
                destino = v["Cliente_Razon_Social"] if v else (f.get("Razon_Social_Cliente") or "—")
                pct_c = float(f.get("Porcentaje_Compra") or 0)
                pct_v = _pct_venta_de(f, ventas)
                a_pagar = f["Monto_Total"] * pct_c / 100.0
                a_cobrar = f["Monto_Total"] * pct_v / 100.0
                return {
                    "ID": f["ID"],
                    "fecha": f["Fecha_Emision"] or "-",
                    "nit": f["NIT_Emisor"] or "-",
                    "factura": f["Nro_Factura"] or "-",
                    "destino": destino,
                    "pct_c": pct_c,
                    "pct_v": pct_v,
                    "monto": f["Monto_Total"],
                    "apagar": a_pagar,
                    "acobrar": a_cobrar,
                    "utilidad": a_cobrar - a_pagar,
                    "estado": f["Estado_Pago"],
                    "venta": (v["Estado_Cobro"] if v else "sin venta"),
                }

            datos = [_datos_factura(f) for f in facturas]
            tot_monto = sum(d["monto"] for d in datos)
            tot_pagar = sum(d["apagar"] for d in datos)
            tot_cobrar = sum(d["acobrar"] for d in datos)
            tot_util = tot_cobrar - tot_pagar
            tot = {"monto": tot_monto, "apagar": tot_pagar, "acobrar": tot_cobrar, "utilidad": tot_util}

            def _fmt_num(x):
                return f"{x:,.2f}"

            def _fmt_pct(x):
                return f"{round(x, 4):g}%"

            def _valor_uniforme(valores):
                unicos = set(valores)
                return next(iter(unicos)) if len(unicos) == 1 else "MIXTO"

            def _fila_totales(columnas, n):
                fila = {clave: "" for clave, _, _ in columnas}
                fila[columnas[0][0]] = "TOTALES"
                fila["n"] = str(n)
                for clave in ("monto", "apagar", "acobrar", "utilidad"):
                    fila[clave] = _fmt_num(tot[clave])
                return fila

            def _armar_columnas(columnas):
                return [
                    {"name": clave, "label": etiqueta, "field": clave, "align": alineacion}
                    for clave, etiqueta, alineacion in columnas
                ]

            modo = {"valor": "Compacto"}
            cont_tabla = ui.column().classes("w-full")

            def _pintar_tabla():
                cont_tabla.clear()
                with cont_tabla:
                    if modo["valor"] == "Compacto":
                        grupos = {}
                        for d in datos:
                            grupos.setdefault(d["destino"], []).append(d)
                        filas = []
                        for cliente, grupo in sorted(grupos.items(), key=lambda kv: kv[0].lower()):
                            monto = sum(g["monto"] for g in grupo)
                            pagar = sum(g["apagar"] for g in grupo)
                            cobrar = sum(g["acobrar"] for g in grupo)
                            filas.append(
                                {
                                    "cliente": cliente,
                                    "n": str(len(grupo)),
                                    "pct_c": _fmt_pct(pagar / monto * 100 if monto else 0),
                                    "pct_v": _fmt_pct(cobrar / monto * 100 if monto else 0),
                                    "monto": _fmt_num(monto),
                                    "apagar": _fmt_num(pagar),
                                    "acobrar": _fmt_num(cobrar),
                                    "utilidad": _fmt_num(cobrar - pagar),
                                    "estado": _valor_uniforme(g["estado"] for g in grupo),
                                    "venta": _valor_uniforme(g["venta"] for g in grupo),
                                }
                            )
                        fila_tot = _fila_totales(COLUMNAS_COMPACTO, len(datos))
                        fila_tot["pct_c"] = _fmt_pct(tot_pagar / tot_monto * 100 if tot_monto else 0)
                        fila_tot["pct_v"] = _fmt_pct(tot_cobrar / tot_monto * 100 if tot_monto else 0)
                        filas.append(fila_tot)
                        ui.table(
                            columns=_armar_columnas(COLUMNAS_COMPACTO),
                            rows=filas,
                            row_key="cliente",
                            pagination={"rowsPerPage": 0},
                        ).classes("w-full").props("flat dense bordered")
                    else:
                        filas = []
                        for i, d in enumerate(datos, 1):
                            filas.append(
                            {
                                "nro": str(i),
                                "ID": d["ID"],
                                "fecha": d["fecha"],
                                "nit": d["nit"],
                                "factura": d["factura"],
                                "destino": d["destino"],
                                "pct_c": _fmt_pct(d["pct_c"]),
                                "pct_v": _fmt_pct(d["pct_v"]),
                                "monto": _fmt_num(d["monto"]),
                                "apagar": _fmt_num(d["apagar"]),
                                "acobrar": _fmt_num(d["acobrar"]),
                                "utilidad": _fmt_num(d["utilidad"]),
                                "estado": d["estado"],
                                "venta": d["venta"],
                            }
                            )
                        fila_tot = _fila_totales(COLUMNAS_DETALLE, len(datos))
                        fila_tot["pct_c"] = _fmt_pct(tot_pagar / tot_monto * 100 if tot_monto else 0)
                        fila_tot["pct_v"] = _fmt_pct(tot_cobrar / tot_monto * 100 if tot_monto else 0)
                        filas.append(fila_tot)
                        ui.table(
                            columns=_armar_columnas(COLUMNAS_DETALLE),
                            rows=filas,
                            row_key="ID",
                            selection="single",
                            pagination={"rowsPerPage": 0},
                            on_select=lambda e: _abrir_factura(
                                next(
                                    (f for f in facturas if f["ID"] == (e.selection[0]["ID"] if e.selection else None)),
                                    None,
                                ),
                                proveedor,
                            ),
                        ).classes("w-full").props("flat dense bordered")

            with ui.row().classes("w-full items-center gap-2"):
                ui.label("Vista:").classes("text-sm opacity-60")
                ui.toggle(
                    ["Compacto", "Detallado"],
                    value="Compacto",
                    on_change=lambda e: (modo.update({"valor": e.value}), _pintar_tabla()),
                ).props("dense outline")
            _pintar_tabla()

            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                ui.label(f"Facturado: Bs {tot_monto:,.2f}")
                ui.label(f"A pagarle: Bs {tot_pagar:,.2f}").classes("text-negative font-semibold")
                ui.label(f"A cobrar: Bs {tot_cobrar:,.2f}").classes("text-primary font-semibold")
                ui.label(f"Utilidad: Bs {tot_util:,.2f}").classes("font-bold")

            with ui.row().classes("w-full items-end gap-2 q-mt-sm"):
                pct_nuevo = ui.number("Corregir % compra de TODAS sus facturas del mes", value=0.0, format="%.2f").classes("w-80")

                def _aplicar_pct():
                    if not pct_nuevo.value or pct_nuevo.value <= 0:
                        ui.notify("Poné el % correcto primero.", type="warning")
                        return
                    n = db.aplicar_pct_compra(_mes(), proveedor, pct_nuevo.value)
                    ui.notify(f"% compra de {proveedor} actualizado a {pct_nuevo.value:g}% en {n} factura(s). Todo recalculado.", type="positive")
                    pintar()

                ui.button(
                    "Aplicar y recalcular",
                    icon="percent",
                    on_click=_aplicar_pct,
                ).props("unelevated dense no-caps color=primary").tooltip(
                    "Corrige el % de compra de todas las facturas de este proveedor en el mes. "
                    "Lo que se le paga y la utilidad se recalculan en todos los reportes al instante."
                )

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
                pagination=0,
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
                    pagination=0,
                ).classes("w-full").props("flat dense bordered")

            with ui.row().classes("w-full gap-2 q-mt-sm"):
                with ui.link(target=pdf_url.url_empresa(_mes(), cliente), new_tab=True).classes(
                    "row items-center gap-1 text-primary text-sm font-semibold no-underline"
                ):
                    ui.icon("picture_as_pdf", size="xs")
                    ui.label("PDF de la empresa (pestaña nueva)")

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
                        pagination=0,
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

    def _seccion_reportes():
        ui.label("📊 Reportes finales del mes").classes("font-semibold text-lg")
        with ui.row().classes("w-full flex-wrap gap-2"):
            ui.button("Excel de control", icon="table_view", on_click=lambda: _excel()).props("flat")
            with ui.link(target=pdf_url.url_resumen(_mes()), new_tab=True).classes(
                "row items-center gap-1 text-primary text-sm font-semibold no-underline"
            ):
                ui.icon("picture_as_pdf", size="xs")
                ui.label("PDF resumen (pestaña nueva)")
            ui.button("PDFs por empresa (.zip)", icon="folder_zip", on_click=lambda: _pdf_zip()).props("unelevated")

        def _excel():
            datos, nombre = exportador.exportar_reportes_mes(_mes())
            ui.download(datos, filename=nombre)
            ui.notify("Excel generado.", type="positive")

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
                pagination=0,
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
                pagination=0,
            ).classes("w-full").props("flat dense bordered")

    pintar()
