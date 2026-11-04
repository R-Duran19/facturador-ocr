"""Ventas y cobros: hub de dinero del mes.

Seleccionás el mes y entrás a COBROS (empresas a las que se les vendió) o
PAGOS (proveedores que trajeron facturas). Cada uno con su tabla resumen
(estilo Excel: totales, # facturas, empresas/proveedores) y detalle gestionable.
"""

from datetime import date

from nicegui import ui

import db
from webui import nav, pdf_url
from webui.componentes import confirmar, input_fecha
from webui.plantilla import pagina

METODOS = ["QR", "Efectivo", "Transferencia", "Otro"]

ESTADO_COLOR = {"PAGADO": "green", "COBRADO": "green", "PARCIAL": "orange", "PENDIENTE": "red"}

COLUMNAS_FACTURAS = [
    {"name": "nro", "label": "N° Factura", "field": "nro", "align": "left"},
    {"name": "cliente", "label": "Cliente", "field": "cliente", "align": "left"},
    {"name": "prov", "label": "Proveedor", "field": "prov", "align": "left"},
    {"name": "fecha", "label": "Fecha", "field": "fecha", "align": "left"},
    {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
    {"name": "cobrar", "label": "A cobrar", "field": "cobrar", "align": "right"},
]

_CLAVES_SUMA = ("monto", "apagar", "acobrar", "utilidad")


def _tabla_modo(cont, datos, cols_compacto, cols_detalle):
    """Tabla con vista Compacta (agrupada) o Detallada, con fila de TOTALES."""
    clave_grupo = cols_compacto[0][0]

    def _fmt(x):
        return f"{x:,.2f}"

    def _total(cols, n):
        fila = {clave: "" for clave, _, _ in cols}
        fila[cols[0][0]] = "TOTALES"
        if any(c[0] == "n" for c in cols):
            fila["n"] = str(n)
        for clave in _CLAVES_SUMA:
            if any(c[0] == clave for c in cols):
                fila[clave] = _fmt(sum(d.get(clave, 0) or 0 for d in datos))
        return fila

    modo = {"valor": "Compacto"}

    def _pintar():
        cont.clear()
        with cont:
            if modo["valor"] == "Compacto":
                grupos = {}
                for d in datos:
                    grupos.setdefault(str(d.get(clave_grupo) or "—"), []).append(d)
                filas = []
                for nombre, grupo in sorted(grupos.items(), key=lambda kv: kv[0].lower()):
                    fila = {clave: "" for clave, _, _ in cols_compacto}
                    fila[clave_grupo] = nombre
                    fila["n"] = str(len(grupo))
                    for clave in _CLAVES_SUMA:
                        if any(c[0] == clave for c in cols_compacto):
                            fila[clave] = _fmt(sum(x.get(clave, 0) or 0 for x in grupo))
                    numerador = "apagar" if grupo and "apagar" in grupo[0] else "acobrar"
                    total_monto = sum(x.get("monto", 0) or 0 for x in grupo)
                    pct = round(sum(x.get(numerador, 0) or 0 for x in grupo) / total_monto * 100, 4) if total_monto else 0
                    fila["pct"] = f"{pct:g}%"
                    filas.append(fila)
                filas.append(_total(cols_compacto, len(datos)))
                columnas, row_key = cols_compacto, clave_grupo
            else:
                filas = []
                for d in datos:
                    fila = {}
                    for clave, _, _ in cols_detalle:
                        valor = d.get(clave, "")
                        if clave in _CLAVES_SUMA:
                            fila[clave] = _fmt(valor)
                        elif clave == "pct":
                            fila[clave] = f"{valor:g}%"
                        else:
                            fila[clave] = valor
                    filas.append(fila)
                filas.append(_total(cols_detalle, len(datos)))
                columnas, row_key = cols_detalle, "factura"
            ui.table(
                columns=[
                    {"name": clave, "label": etiqueta, "field": clave, "align": alineacion}
                    for clave, etiqueta, alineacion in columnas
                ],
                rows=filas,
                row_key=row_key,
                pagination={"rowsPerPage": 0},
            ).classes("w-full").props("flat dense bordered")

    with ui.row().classes("w-full items-center gap-2"):
        ui.label("Vista:").classes("text-sm opacity-60")
        ui.toggle(
            ["Compacto", "Detallado"],
            value="Compacto",
            on_change=lambda e: (modo.update({"valor": e.value}), _pintar()),
        ).props("dense outline")
    _pintar()


def _texto_whatsapp(ficha: dict) -> str:
    """Contacto de WhatsApp: prioriza el nombre (como lo tiene guardado el usuario) y agrega el telefono."""
    nombre = str(ficha.get("Contacto", "") or "").strip()
    tel = str(ficha.get("Telefono", "") or "").strip()
    partes = [p for p in (nombre, tel) if p]
    return " - ".join(partes) if partes else "—"


@pagina("/ventas")
def pagina_ventas():
    meses = sorted(set(db.listar_meses()), reverse=True) or ["—"]
    mes_ini = date.today().strftime("%Y_%m_")
    mes_default = next((m for m in meses if m.startswith(mes_ini)), meses[0])

    estado = {"vista": "menu", "mes": mes_default, "cliente": None, "proveedor": None}

    sel_mes = ui.select(
        meses,
        value=mes_default,
        label="Mes",
        on_change=lambda e: (estado.update({"mes": e.value, "vista": "menu", "cliente": None, "proveedor": None}), pintar()),
    ).classes("w-52")
    breadcrumb = ui.row().classes("w-full items-center gap-1 text-sm")

    nav.registrar("/ventas", mes=estado["mes"], vista="menu")
    _rest = nav.restaurar("/ventas")
    if _rest:
        if _rest.get("mes") and _rest["mes"] in meses:
            estado["mes"] = _rest["mes"]
            sel_mes.set_value(_rest["mes"])
        estado["vista"] = _rest.get("vista") or "menu"
        estado["cliente"] = _rest.get("cliente")
        estado["proveedor"] = _rest.get("proveedor")
    cont = ui.column().classes("w-full gap-4")

    # ---------- datos ----------

    def _facturas():
        return db.leer_facturas_mes(estado["mes"])

    def _ventas():
        return db.leer_ventas_mes(estado["mes"])

    def _siglas_de(venta, facturas_mes):
        ids = {i.strip() for i in venta["Facturas_IDs"].split(",") if i.strip()}
        completos = sorted({f["Proveedor_Asignado"] for f in facturas_mes if f["ID"] in ids and f["Proveedor_Asignado"]})
        return "/".join(p[:3].upper() for p in completos) if completos else "—"

    def _resumen_cobros():
        """Agregado por EMPRESA (cliente): lo que hay que cobrarle."""
        ventas = _ventas()
        facturas_mes = _facturas()
        clientes = {c["Nombre_Razon_Social"]: c for c in db.leer_clientes()}
        filas = []
        for cliente in sorted({v["Cliente_Razon_Social"] for v in ventas}, key=str.lower):
            sus = [v for v in ventas if v["Cliente_Razon_Social"] == cliente]
            nominal = sum(v["Monto_Nominal"] for v in sus)
            cobrar = sum(v["Precio_Cobrado"] for v in sus)
            cobrado = sum(v["Total_Cobrado"] for v in sus)
            saldo = round(cobrar - cobrado, 2)
            est = next((v["Estado_Cobro"] for v in sus if v["Saldo"] > 0.005), "COBRADO")
            n_fact = sum(len([i for i in v["Facturas_IDs"].split(",") if i.strip()]) for v in sus)
            provs = sorted({_siglas_de(v, facturas_mes) for v in sus})
            entregado = "SI" if all(v.get("Entregado") == "SI" for v in sus) and sus else ""
            filas.append(
                {
                    "cliente": cliente,
                    "rubro": clientes.get(cliente, {}).get("Rubro", ""),
                    "facturas": n_fact,
                    "nominal": nominal,
                    "cobrar": cobrar,
                    "cobrado": cobrado,
                    "saldo": saldo,
                    "estado": est,
                    "proveedores": " / ".join(provs),
                    "entregado": entregado,
                    "whats": _texto_whatsapp(clientes.get(cliente, {})),
                    "bancarizado": clientes.get(cliente, {}).get("Bancarizado", "¿?"),
                }
            )
        return filas

    def _resumen_pagos():
        """Agregado por PROVEEDOR: a pagarle + las EMPRESAS EMISORAS de las facturas que trajo."""
        facturas_mes = _facturas()
        datos = db.resumen_pagos_proveedores(estado["mes"])
        for d in datos:
            sus_fact = [f for f in facturas_mes if f["Proveedor_Asignado"] == d["Proveedor"]]
            d["n_facturas"] = len(sus_fact)
            emisoras = sorted({f["Razon_Social"] for f in sus_fact if f["Razon_Social"]})
            d["empresas"] = " / ".join(emisoras) if emisoras else "—"
        return datos

    def _venta_de(factura: dict, ventas: list):
        vid = factura.get("Venta_ID") or ""
        return next((v for v in ventas if v["ID_Venta"] == vid), None)

    def _deudas_totales(excluir: str = "") -> list:
        """Todas las ventas con saldo de TODOS los meses (para el módulo de deudas)."""
        deudas = []
        for mes in db.listar_meses():
            if mes == excluir:
                continue
            for v in db.leer_ventas_mes(mes):
                if v["Saldo"] > 0.005:
                    v["mes_legible"] = _legible(mes)
                    deudas.append(v)
        return deudas

    def _toggle_entregado(e):
        try:
            venta_id, valor = str(e.args).split("|", 1)
        except (ValueError, AttributeError):
            return
        venta = db.venta_por_id(venta_id)
        if not venta:
            return
        venta["Entregado"] = "SI" if valor == "SI" else ""
        db.actualizar_venta(venta.get("Mes", estado["mes"]), venta)
        ui.notify("Entregado actualizado.", type="positive", timeout=1)
        pintar()

    def _pct_venta_de(factura: dict, ventas: list) -> float:
        v = _venta_de(factura, ventas)
        if v and v["Monto_Nominal"]:
            return v["Precio_Cobrado"] / v["Monto_Nominal"] * 100.0
        return 5.0

    # ---------- render ----------

    def _migas(*niveles):
        with breadcrumb:
            ui.button(_legible(estado["mes"]), on_click=lambda: _ir("menu")).props("flat dense no-caps")
            for i, nivel in enumerate(niveles):
                ui.label("›")
                if i == len(niveles) - 1:
                    ui.label(nivel).classes("text-primary font-semibold")
                else:
                    ui.button(nivel, on_click=lambda: _ir(niveles[0])).props("flat dense no-caps")

    def _legible(nombre_mes):
        try:
            anio, num, _ = str(nombre_mes).split("_", 2)
            MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            return f"{MESES[int(num) - 1]} {anio}"
        except (ValueError, IndexError):
            return str(nombre_mes)

    def _ir(vista, cliente=None, proveedor=None):
        estado["vista"] = vista
        estado["cliente"] = cliente
        estado["proveedor"] = proveedor
        nav.registrar("/ventas", mes=estado["mes"], vista=vista, cliente=cliente, proveedor=proveedor)
        pintar()

    def pintar():
        breadcrumb.clear()
        if estado["vista"] == "menu":
            with breadcrumb:
                ui.label(_legible(estado["mes"])).classes("text-primary font-semibold")
        cont.clear()
        with cont:
            if estado["vista"] == "menu":
                _vista_menu()
            elif estado["vista"] == "cobros":
                _migas("Cobros a empresas")
                _vista_cobros()
            elif estado["vista"] == "pagos":
                _migas("Pagos a proveedores")
                _vista_pagos()
            elif estado["vista"] == "cobros_cliente":
                _migas("Cobros a empresas", estado["cliente"])
                _detalle_cobros_cliente(estado["cliente"])
            elif estado["vista"] == "pagos_proveedor":
                _migas("Pagos a proveedores", estado["proveedor"])
                _detalle_pagos_proveedor(estado["proveedor"])
            elif estado["vista"] == "deudas":
                _migas("Deudas de meses anteriores")
                _vista_deudas()
            elif estado["vista"] == "deuda_detalle":
                _migas("Deudas de meses anteriores", estado.get("cliente", ""))
                _detalle_cobros_cliente(estado.get("cliente", ""), mes_forzado=estado.get("mes_deuda"))

    # ---------- MENÚ: 2 botones grandes ----------

    def _vista_menu():
        cobros = _resumen_cobros()
        pagos = _resumen_pagos()
        a_cobrar = sum(f["cobrar"] for f in cobros)
        por_cobrar = sum(f["saldo"] for f in cobros)
        a_pagar = sum(f["A_Pagar"] for f in pagos)
        por_pagar = sum(f["Saldo"] for f in pagos)

        with ui.row().classes("w-full flex-wrap gap-4"):
            with ui.card().classes("cursor-pointer flex-1 min-w-[300px] border-2").style(
                "border-color: var(--q-primary);"
            ).on("click", lambda: _ir("cobros")):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("arrow_downward", color="green").classes("text-4xl")
                    ui.label("COBROS").classes("text-2xl font-bold")
                ui.label(f"Empresas a las que les vendiste: {len(cobros)}").classes("text-sm opacity-70")
                with ui.row().classes("w-full flex-wrap gap-x-6 gap-y-0 text-sm q-px-sm"):
                    ui.label(f"A cobrar: Bs {a_cobrar:,.2f}")
                    ui.label(f"Cobrado: Bs {a_cobrar - por_cobrar:,.2f}")
                    ui.label(f"Por cobrar: Bs {por_cobrar:,.2f}").classes("font-bold text-negative")
                ui.label("Entrá acá para gestionar los cobros a cada empresa ›").classes("text-xs opacity-50")

            with ui.card().classes("cursor-pointer flex-1 min-w-[300px] border-2").style(
                "border-color: #B45309;"
            ).on("click", lambda: _ir("pagos")):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("arrow_upward", color="orange-8").classes("text-4xl")
                    ui.label("PAGOS").classes("text-2xl font-bold")
                ui.label(f"Proveedores que trajeron facturas: {len(pagos)}").classes("text-sm opacity-70")
                with ui.row().classes("w-full flex-wrap gap-x-6 gap-y-0 text-sm q-px-sm"):
                    ui.label(f"A pagar: Bs {a_pagar:,.2f}")
                    ui.label(f"Pagado: Bs {a_pagar - por_pagar:,.2f}")
                    ui.label(f"Por pagar: Bs {por_pagar:,.2f}").classes("font-bold text-negative")
                ui.label("Entrá acá para gestionar los pagos a cada proveedor ›").classes("text-xs opacity-50")

        deudas = _deudas_totales(excluir=estado["mes"])
        manuales = [d for d in db.leer_deudas_manuales() if d["Saldo"] > 0.005]
        hay_deudas = bool(deudas or manuales)
        empresas_deuda = len({v["Cliente_Razon_Social"] for v in deudas} | {d["Cliente"] for d in manuales})
        total_deuda = sum(v["Saldo"] for v in deudas) + sum(d["Saldo"] for d in manuales)
        with ui.card().classes("cursor-pointer w-full border-2").style("border-color: #B91C1C;").on(
            "click", lambda: _ir("deudas")
        ):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("warning", color="red" if hay_deudas else "grey").classes("text-4xl")
                ui.label("DEUDAS DE MESES ANTERIORES").classes("text-xl font-bold")
                ui.space()
                if hay_deudas:
                    ui.badge(f"{len(deudas) + len(manuales)} deuda(s)", color="red").props("text-color=white")
                else:
                    ui.badge("al día", color="grey").props("text-color=white")
            if hay_deudas:
                ui.label(
                    f"Empresas con saldo pendiente de otros meses: {empresas_deuda} · Por cobrar: Bs {total_deuda:,.2f}"
                ).classes("text-sm")
                if manuales:
                    ui.label(
                        f"Incluye Bs {sum(d['Saldo'] for d in manuales):,.2f} de deudas manuales cargadas a mano"
                    ).classes("text-xs text-negative")
            else:
                ui.label("No hay deudas pendientes. Acá podés cargar deudas manuales de otros meses.").classes(
                    "text-sm opacity-60"
                )
            ui.label("Entrá acá para gestionar esas deudas (registrar cobros, reclamar) ›").classes(
                "text-xs opacity-50"
            )

    # ---------- DEUDAS DE MESES ANTERIORES ----------

    def _vista_deudas():
        deudas = _deudas_totales()
        with ui.row().classes("w-full justify-between items-center"):
            ui.label("Deudas de meses anteriores").classes("font-semibold text-lg")
            ui.button("➕ Agregar deuda manual", icon="post_add", on_click=_dialogo_deuda_manual).props(
                "unelevated dense"
            )
        ui.label("Ventas de otros meses con saldo pendiente").classes("text-sm opacity-60 q-mt-sm")
        if not deudas:
            ui.label("No hay ventas con saldo de meses anteriores. Todo al día. ✔").classes("opacity-50")
        else:
            filas = []
            for i, v in enumerate(sorted(deudas, key=lambda x: (x["Mes"], x["Cliente_Razon_Social"])), 1):
                filas.append(
                    {
                        "nro": str(i),
                        "mes": v.get("mes_legible", v["Mes"]),
                        "cliente": v["Cliente_Razon_Social"],
                        "cobrar": f"{v['Precio_Cobrado']:,.2f}",
                        "cobrado": f"{v['Total_Cobrado']:,.2f}",
                        "saldo": f"{v['Saldo']:,.2f}",
                        "estado": v["Estado_Cobro"],
                        "ID_Venta": v["ID_Venta"],
                    }
                )
            ui.table(
                columns=[
                    {"name": "nro", "label": "#", "field": "nro", "align": "center"},
                    {"name": "mes", "label": "Mes", "field": "mes", "align": "left"},
                    {"name": "cliente", "label": "Empresa", "field": "cliente", "align": "left"},
                    {"name": "cobrar", "label": "A cobrar", "field": "cobrar", "align": "right"},
                    {"name": "cobrado", "label": "Cobrado", "field": "cobrado", "align": "right"},
                    {"name": "saldo", "label": "Saldo", "field": "saldo", "align": "right"},
                    {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
                ],
                rows=filas,
                row_key="ID_Venta",
                selection="single",
                pagination={"rowsPerPage": 15},
                on_select=lambda e: (
                    estado.update(
                        {
                            "vista": "deuda_detalle",
                            "cliente": (e.selection[0]["cliente"] if e.selection else None),
                            "mes_deuda": (next((f["Mes"] for f in deudas if f["ID_Venta"] == (e.selection[0]["ID_Venta"] if e.selection else None)), estado["mes"]) if e.selection else None),
                        }
                    ),
                    nav.registrar(
                        "/ventas",
                        mes=estado["mes"],
                        vista="deuda_detalle",
                        cliente=estado["cliente"],
                        proveedor=None,
                    ),
                    pintar(),
                ),
            ).classes("w-full").props("flat dense bordered")
            ui.label("Seleccioná una fila para gestionar el cobro de esa deuda.").classes("text-xs opacity-50")

        # ---------- DEUDAS MANUALES ----------

        manuales = db.leer_deudas_manuales()
        ui.separator().classes("q-my-sm")
        ui.label("Deudas manuales (cargadas a mano)").classes("font-semibold text-lg")
        if not manuales:
            ui.label(
                "Acá podés cargar deudas de meses anteriores que no están como ventas (ej: 'me debe Bs 500 de enero')."
            ).classes("text-sm opacity-50")
        else:
            sel = {"id": None}
            filas = [
                {
                    "cliente": d["Cliente"],
                    "mes": d["Mes_Origen"] or "—",
                    "concepto": d["Concepto"] or "—",
                    "monto": f"{d['Monto']:,.2f}",
                    "cobrado": f"{d['Cobrado']:,.2f}",
                    "saldo": f"{d['Saldo']:,.2f}",
                    "estado": d["Estado"],
                    "ID_Deuda": d["ID_Deuda"],
                }
                for d in manuales
            ]
            ui.table(
                columns=[
                    {"name": "cliente", "label": "Cliente", "field": "cliente", "align": "left"},
                    {"name": "mes", "label": "Mes deuda", "field": "mes", "align": "left"},
                    {"name": "concepto", "label": "Concepto", "field": "concepto", "align": "left"},
                    {"name": "monto", "label": "Monto", "field": "monto", "align": "right"},
                    {"name": "cobrado", "label": "Cobrado", "field": "cobrado", "align": "right"},
                    {"name": "saldo", "label": "Saldo", "field": "saldo", "align": "right"},
                    {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
                ],
                rows=filas,
                row_key="ID_Deuda",
                selection="single",
                pagination={"rowsPerPage": 15},
                on_select=lambda e: sel.update({"id": e.selection[0]["ID_Deuda"] if e.selection else None}),
            ).classes("w-full").props("flat dense bordered")
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                ui.label(f"Cargado: Bs {sum(d['Monto'] for d in manuales):,.2f}")
                ui.label(f"Cobrado: Bs {sum(d['Cobrado'] for d in manuales):,.2f}")
                ui.label(f"Pendiente: Bs {sum(d['Saldo'] for d in manuales):,.2f}").classes("font-bold text-negative")
            with ui.row().classes("w-full gap-2"):
                ui.button(
                    "Registrar cobro de la seleccionada",
                    icon="payments",
                    on_click=lambda: _cobrar_deuda_manual(sel),
                ).props("unelevated dense no-caps color=primary")
                ui.button(
                    "Eliminar seleccionada",
                    icon="delete",
                    on_click=lambda: _eliminar_deuda_manual(sel),
                ).props("flat dense no-caps color=negative")

    def _dialogo_deuda_manual():
        nombres = [c["Nombre_Razon_Social"] for c in db.leer_clientes() if c["Nombre_Razon_Social"]]
        hoy = date.today()
        nombres_mes = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ]
        opciones_mes = [f"{nombres_mes[m - 1]} {a}" for a in (hoy.year - 1, hoy.year, hoy.year + 1) for m in range(1, 13)]
        mes_actual = f"{nombres_mes[hoy.month - 1]} {hoy.year}"
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[520px]"):
            ui.label("Nueva deuda manual").classes("text-lg font-bold")
            ui.label("Para deudas de meses anteriores que no están cargadas como ventas del sistema.").classes(
                "text-xs opacity-50"
            )
            e_cliente = ui.select(
                nombres + ["➕ Otro..."],
                value=nombres[0] if nombres else "➕ Otro...",
                label="Cliente",
                new_value_mode="add",
            ).classes("w-full")
            e_mes = ui.select(
                opciones_mes,
                value=mes_actual,
                label="Mes de la deuda",
                new_value_mode="add",
            ).classes("w-full")
            e_monto = ui.number("Monto que debe (Bs)", value=0.0, format="%.2f")
            e_concepto = ui.input("Concepto / nota (opcional)").classes("w-full")

            def _guardar():
                cliente = (e_cliente.value or "").strip()
                if not cliente or cliente == "➕ Otro...":
                    ui.notify("Elegí o escribí el cliente.", type="warning")
                    return
                if not e_monto.value or e_monto.value <= 0:
                    ui.notify("Monto inválido.", type="warning")
                    return
                db.agregar_deuda_manual(cliente, e_mes.value or "", "", e_monto.value, e_concepto.value or "")
                ui.notify(f"Deuda de {cliente} agregada.", type="positive")
                dialogo.close()
                pintar()

            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Guardar deuda", icon="save", on_click=_guardar).props("unelevated dense color=primary")
        dialogo.open()

    def _cobrar_deuda_manual(sel):
        deuda = next((d for d in db.leer_deudas_manuales() if d["ID_Deuda"] == sel.get("id")), None)
        if not deuda:
            ui.notify("Seleccioná una deuda de la tabla.", type="warning")
            return
        if deuda["Saldo"] <= 0.005:
            ui.notify("Esa deuda ya está cobrada.", type="info")
            return
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[460px]"):
            ui.label(f"Cobrar deuda · {deuda['Cliente']}").classes("text-lg font-bold")
            ui.label(
                f"{deuda['Concepto'] or 'Deuda manual'} · {deuda['Mes_Origen'] or 'sin mes'} · Saldo: Bs {deuda['Saldo']:,.2f}"
            ).classes("text-sm opacity-70")
            f = input_fecha("Fecha")
            m = ui.number("Monto que está pagando", value=deuda["Saldo"], format="%.2f")
            met = ui.select(METODOS, value="QR", label="Método", new_value_mode="add").classes("w-44")
            n = ui.input("Nota (opcional)")

            def _registrar():
                if not m.value or m.value <= 0:
                    ui.notify("Monto inválido.", type="warning")
                    return
                db.registrar_cobro_deuda(deuda["ID_Deuda"], m.value, (f.value or "").strip() or None, n.value or "", met.value or "")
                ui.notify("Cobro registrado.", type="positive")
                dialogo.close()
                pintar()

            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Registrar cobro", icon="payments", on_click=_registrar).props("unelevated dense color=primary")
        dialogo.open()

    def _eliminar_deuda_manual(sel):
        deuda = next((d for d in db.leer_deudas_manuales() if d["ID_Deuda"] == sel.get("id")), None)
        if not deuda:
            ui.notify("Seleccioná una deuda de la tabla.", type="warning")
            return

        def accion():
            if not db.eliminar_deuda_manual(deuda["ID_Deuda"]):
                ui.notify("No se puede: tiene cobros registrados. Eliminá primero sus cobros.", type="warning")
                return
            ui.notify("Deuda eliminada.", type="positive")
            pintar()

        confirmar(
            f"¿Eliminar la deuda de {deuda['Cliente']} por Bs {deuda['Monto']:,.2f}?",
            accion,
            "Eliminar",
        )

    # ---------- COBROS: lista de empresas ----------

    def _vista_cobros():
        filas = _resumen_cobros()
        clientes_data = {c["Nombre_Razon_Social"]: c for c in db.leer_clientes()}
        with ui.row().classes("w-full justify-between items-center"):
            ui.label("Empresas a las que les vendiste").classes("font-semibold text-lg")
            ui.button("➕ Nueva venta", icon="add_shopping_cart", on_click=lambda: _dialogo_nueva_venta()).props(
                "unelevated"
            )
        if not filas:
            ui.label("Sin ventas este mes.").classes("opacity-50")
            return

        filas_fmt = [
            {
                **f,
                "nro": str(i),
                "entregado": f["entregado"],
                "whats": f["whats"],
                "bancarizado": f["bancarizado"],
                "monto_s": f"{f['nominal']:,.2f}",
                "cobrar_s": f"{f['cobrar']:,.2f}",
                "cobrado_s": f"{f['cobrado']:,.2f}",
                "saldo_s": f"{f['saldo']:,.2f}",
            }
            for i, f in enumerate(filas, 1)
        ]
        filas_fmt.append(
            {
                "nro": "",
                "cliente": "TOTALES",
                "rubro": "",
                "facturas": sum(f["facturas"] for f in filas),
                "monto_s": f"{sum(f['nominal'] for f in filas):,.2f}",
                "cobrar_s": f"{sum(f['cobrar'] for f in filas):,.2f}",
                "pct": "",
                "proveedores": "",
                "entregado": "",
                "cobrado_s": f"{sum(f['cobrado'] for f in filas):,.2f}",
                "saldo_s": f"{sum(f['saldo'] for f in filas):,.2f}",
                "estado": "",
            }
        )
        tabla_cobros = ui.table(
            columns=[
                {"name": "nro", "label": "#", "field": "nro", "align": "center"},
                {"name": "cliente", "label": "Empresa (destino)", "field": "cliente", "align": "left"},
                {"name": "rubro", "label": "Rubro", "field": "rubro", "align": "center"},
                {"name": "whats", "label": "WhatsApp", "field": "whats", "align": "left"},
                {"name": "bancarizado", "label": "Banc.", "field": "bancarizado", "align": "center"},
                {"name": "facturas", "label": "Facturas", "field": "facturas", "align": "center"},
                {"name": "monto_s", "label": "Monto", "field": "monto_s", "align": "right"},
                {"name": "cobrar_s", "label": "A cobrar", "field": "cobrar_s", "align": "right"},
                {"name": "proveedores", "label": "Prov.", "field": "proveedores", "align": "center"},
                {"name": "entregado", "label": "Entregado ✔", "field": "entregado", "align": "center"},
                {"name": "cobrado_s", "label": "Cobrado", "field": "cobrado_s", "align": "right"},
                {"name": "saldo_s", "label": "Saldo", "field": "saldo_s", "align": "right"},
                {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
            ],
            rows=filas_fmt,
            row_key="cliente",
            selection="single",
            pagination={"rowsPerPage": 0},
            on_select=lambda e: _ir("cobros_cliente", (e.selection[0]["cliente"] if e.selection else None)),
        ).classes("w-full").props("flat dense bordered")
        tabla_cobros.add_slot(
            "body-cell-entregado",
            """
            <q-td key="entregado" :props="props">
                <q-checkbox
                    dense
                    :model-value="props.row.entregado === 'SI'"
                    @update:model-value="v => $parent.$emit('toggle_entregado_cliente', props.row.cliente + '|' + (v ? 'SI' : ''))"
                />
            </q-td>
            """,
        )
        tabla_cobros.on("toggle_entregado_cliente", _toggle_entregado_cliente)

    def _toggle_entregado_cliente(e):
        try:
            cliente, valor = str(e.args).split("|", 1)
        except (ValueError, AttributeError):
            return
        for v in db.leer_ventas_mes(estado["mes"]):
            if v["Cliente_Razon_Social"] == cliente:
                v["Entregado"] = valor
                db.actualizar_venta(estado["mes"], v)
        ui.notify("Entregado actualizado para " + cliente + ".", type="positive", timeout=1)
        pintar()
        ui.label("Seleccioná una empresa para ver el detalle de sus facturas y gestionar los cobros.").classes(
            "text-xs opacity-50"
        )

    # ---------- DETALLE COBROS POR EMPRESA ----------

    def _detalle_cobros_cliente(cliente: str, mes_forzado: str = None):
        mes_usado = mes_forzado or estado["mes"]
        ventas = [v for v in db.leer_ventas_mes(mes_usado) if v["Cliente_Razon_Social"] == cliente]
        ids = set()
        for v in ventas:
            ids |= {i.strip() for i in v["Facturas_IDs"].split(",") if i.strip()}
        facturas = sorted(
            [f for f in db.leer_facturas_mes(mes_usado) if f["ID"] in ids],
            key=lambda f: (f["Fecha_Emision"], f["Nro_Factura"]),
        )

        nominal = sum(f["Monto_Total"] for f in facturas)
        cobrar = sum(v["Precio_Cobrado"] for v in ventas)
        cobrado = sum(v["Total_Cobrado"] for v in ventas)
        saldo = round(cobrar - cobrado, 2)
        est = next((v["Estado_Cobro"] for v in ventas if v["Saldo"] > 0.005), "COBRADO")
        clientes_ficha = {c["Nombre_Razon_Social"]: c for c in db.leer_clientes()}
        ficha = clientes_ficha.get(cliente, {})

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
                contacto = _texto_whatsapp(ficha)
                if contacto:
                    ui.label(f"📱 WhatsApp: {contacto}").classes("font-semibold")
                ui.label(f"Bancarizado: {ficha.get('Bancarizado', '¿?')}").classes("opacity-70")

            ui.label("Detalle de facturas (como ventas completas)").classes("font-semibold text-sm q-mt-sm")
            datos_tabla = [
                {
                    "fecha": f["Fecha_Emision"] or "-",
                    "factura": f["Nro_Factura"] or "-",
                    "proveedor": f["Proveedor_Asignado"] or "—",
                    "monto": f["Monto_Total"],
                    "pct": _pct_venta_de(f, ventas),
                    "acobrar": f["Monto_Total"] * _pct_venta_de(f, ventas) / 100,
                }
                for f in facturas
            ]
            cont_tabla = ui.column().classes("w-full")
            _tabla_modo(
                cont_tabla,
                datos_tabla,
                [
                    ("proveedor", "Proveedor", "left"),
                    ("n", "Facturas", "right"),
                    ("pct", "% Venta", "right"),
                    ("monto", "Monto", "right"),
                    ("acobrar", "A cobrar", "right"),
                ],
                [
                    ("fecha", "Fecha", "left"),
                    ("proveedor", "Proveedor", "left"),
                    ("factura", "Factura N", "left"),
                    ("pct", "% Venta", "right"),
                    ("monto", "Monto", "right"),
                    ("acobrar", "A cobrar", "right"),
                ],
            )

            with ui.row().classes("w-full gap-2 q-mt-sm"):
                with ui.link(target=pdf_url.url_empresa(estado["mes"], cliente), new_tab=True).classes(
                    "row items-center gap-1 text-primary text-sm font-semibold no-underline"
                ):
                    ui.icon("picture_as_pdf", size="xs")
                    ui.label("PDF de la empresa (pestaña nueva)")

        # ---------- Registrar cobro (arriba, sin scrollear) ----------

        ventas_con_saldo = [v for v in ventas if v["Saldo"] > 0.005]
        with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("payments", color="primary")
                ui.label("Registrar cobro").classes("font-bold text-md")
                ui.space()
                ui.badge(f"Saldo total: Bs {saldo:,.2f}", color=ESTADO_COLOR.get(est, "grey")).props("text-color=white")
            if not ventas_con_saldo:
                ui.label("Todas las ventas de esta empresa están cobradas. ✔").classes("text-sm opacity-60")
            else:
                with ui.row().classes("w-full flex-wrap items-end gap-2"):
                    f_c = input_fecha("Fecha")
                    m_c = ui.number("Monto que está pagando", value=sum(v["Saldo"] for v in ventas_con_saldo), format="%.2f")
                    met_c = ui.select(METODOS, value="QR", label="Método (QR, efectivo...)", new_value_mode="add").classes("w-44")
                    venta_c = (
                        ui.select(
                            {v["ID_Venta"]: f"Venta {v['ID_Venta']} (saldo Bs {v['Saldo']:,.2f})" for v in ventas_con_saldo},
                            value=ventas_con_saldo[0]["ID_Venta"],
                            label="Este cobro es para la venta:",
                        ).classes("w-72")
                        if len(ventas_con_saldo) > 1
                        else None
                    )
                    n_c = ui.input("Nota (opcional)")
                if venta_c:
                    ui.label(
                        "Esta empresa tiene varias ventas abiertas: elegí a cuál se aplica este cobro "
                        "(así el saldo de cada venta queda exacto)."
                    ).classes("text-xs opacity-60")
                ui.button(
                    "REGISTRAR COBRO",
                    icon="payments",
                    on_click=lambda: _registrar(),
                ).props("unelevated no-caps color=primary")

        def _registrar():
            if not m_c.value or m_c.value <= 0:
                ui.notify("Monto inválido.", type="warning")
                return
            vid = venta_c.value if venta_c else ventas_con_saldo[0]["ID_Venta"]
            db.registrar_cobro(vid, m_c.value, (f_c.value or "").strip() or None, n_c.value or "", met_c.value or "")
            ui.notify("Cobro registrado.", type="positive")
            pintar()

        # ---------- Cobros ya registrados ----------

        ui.label("Cobros ya registrados").classes("font-semibold text-sm q-mt-sm")
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
                            {"name": "nota", "label": "Nota", "field": "Nota", "align": "left"},
                        ],
                        rows=[
                            {
                                "ID_Cobro": c["ID_Cobro"],
                                "Fecha": c["Fecha"],
                                "Venta": c["Venta_ID"],
                                "Monto": f"{c['Monto']:,.2f}",
                                "Metodo": c.get("Metodo", "") or "—",
                                "Nota": c["Nota"],
                            }
                            for c in cobros
                        ],
                        row_key="ID_Cobro",
                        selection="single",
                        pagination=8,
                        on_select=lambda e: sel_cobro.update(
                            {"id": e.selection[0]["ID_Cobro"] if e.selection else None}
                        ),
                    ).props("flat dense bordered")
                    ui.button(
                        "Eliminar cobro seleccionado",
                        icon="delete",
                        on_click=lambda: _eliminar_cobro(),
                    ).props("flat color=negative dense")
                else:
                    ui.label("Sin cobros registrados.").classes("text-sm opacity-50")

        def _eliminar_cobro():
            if not sel_cobro["id"]:
                ui.notify("Seleccioná un cobro.", type="warning")
                return
            db.eliminar_cobro(sel_cobro["id"])
            ui.notify("Cobro eliminado.", type="positive")
            pintar()

        pintar_cobros()

    # ---------- PAGOS: lista de proveedores ----------

    def _vista_pagos():
        datos = _resumen_pagos()
        ui.label("Proveedores que trajeron facturas").classes("font-semibold text-lg")
        if not datos:
            ui.label("Sin compras de proveedores este mes.").classes("opacity-50")
            return

        filas = [
            {
                "proveedor": d["Proveedor"],
                "facturas": d["n_facturas"],
                "empresas": d["empresas"],
                "a_pagar_s": f"{d['A_Pagar']:,.2f}",
                "pagado_s": f"{d['Pagado']:,.2f}",
                "saldo_s": f"{d['Saldo']:,.2f}",
                "estado": d["Estado"],
            }
            for d in datos
        ]
        filas.append(
            {
                "proveedor": "TOTALES",
                "facturas": sum(d["n_facturas"] for d in datos),
                "empresas": "",
                "a_pagar_s": f"{sum(d['A_Pagar'] for d in datos):,.2f}",
                "pagado_s": f"{sum(d['Pagado'] for d in datos):,.2f}",
                "saldo_s": f"{sum(d['Saldo'] for d in datos):,.2f}",
                "estado": "",
            }
        )
        ui.table(
            columns=[
                {"name": "proveedor", "label": "Proveedor", "field": "proveedor", "align": "left"},
                {"name": "facturas", "label": "Facturas", "field": "facturas", "align": "center"},
                {"name": "empresas", "label": "Empresas que trajo", "field": "empresas", "align": "left"},
                {"name": "a_pagar_s", "label": "A pagar", "field": "a_pagar_s", "align": "right"},
                {"name": "pagado_s", "label": "Pagado", "field": "pagado_s", "align": "right"},
                {"name": "saldo_s", "label": "Saldo", "field": "saldo_s", "align": "right"},
                {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
            ],
            rows=filas,
            row_key="proveedor",
            selection="single",
            pagination={"rowsPerPage": 0},
            on_select=lambda e: _ir(
                "pagos_proveedor", proveedor=(e.selection[0]["proveedor"] if e.selection else None)
            ),
        ).classes("w-full").props("flat dense bordered")
        ui.label("Seleccioná un proveedor para ver sus facturas y registrar pagos.").classes("text-xs opacity-50")

    # ---------- DETALLE PAGOS POR PROVEEDOR ----------

    def _detalle_pagos_proveedor(proveedor: str):
        facturas = [f for f in _facturas() if f["Proveedor_Asignado"] == proveedor]
        ventas = _ventas()
        facturas.sort(key=lambda f: (f["Fecha_Emision"], f["Nro_Factura"]))
        resumen = next((d for d in _resumen_pagos() if d["Proveedor"] == proveedor), None)

        a_pagar = sum(f["Monto_Total"] * (f.get("Porcentaje_Compra") or 0) / 100 for f in facturas)
        pagado = sum(p["Monto"] for p in db.leer_pagos_proveedor(proveedor=proveedor, mes=estado["mes"]))
        saldo = round(a_pagar - pagado, 2)
        estado_p = resumen["Estado"] if resumen else "PENDIENTE"

        with ui.card().classes("w-full border-2").style("border-color: #B45309;"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("local_shipping", color="orange-8").classes("text-3xl")
                ui.label(proveedor).classes("text-lg font-bold")
                ui.space()
                ui.badge(estado_p, color=ESTADO_COLOR.get(estado_p, "grey")).props("text-color=white")
            with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm text-sm"):
                ui.label(f"Facturas: {len(facturas)}")
                ui.label(f"A pagar: Bs {a_pagar:,.2f}").classes("font-semibold")
                ui.label(f"Pagado: Bs {pagado:,.2f}")
                ui.label(f"Saldo: Bs {saldo:,.2f}").classes("font-bold")

            ui.label("Detalle de facturas (como compra)").classes("font-semibold text-sm q-mt-sm")
            datos_tabla = [
                {
                    "fecha": f["Fecha_Emision"] or "-",
                    "factura": f["Nro_Factura"] or "-",
                    "cliente": (
                        (_venta_de(f, ventas) or {}).get("Cliente_Razon_Social")
                        or (f.get("Razon_Social_Cliente") or "—")
                    ),
                    "monto": f["Monto_Total"],
                    "pct": float(f.get("Porcentaje_Compra") or 0),
                    "apagar": f["Monto_Total"] * (f.get("Porcentaje_Compra") or 0) / 100,
                }
                for f in facturas
            ]
            cont_tabla = ui.column().classes("w-full")
            _tabla_modo(
                cont_tabla,
                datos_tabla,
                [
                    ("cliente", "Cliente", "left"),
                    ("n", "Facturas", "right"),
                    ("pct", "% Comp", "right"),
                    ("monto", "Monto", "right"),
                    ("apagar", "A pagar", "right"),
                ],
                [
                    ("fecha", "Fecha", "left"),
                    ("factura", "Factura N", "left"),
                    ("cliente", "Cliente", "left"),
                    ("pct", "% Comp", "right"),
                    ("monto", "Monto", "right"),
                    ("apagar", "A pagar", "right"),
                ],
            )

        ui.label("Pagos registrados").classes("font-semibold text-sm q-mt-sm")
        cont_pagos = ui.column().classes("w-full gap-2")
        sel_pago = {"id": None}

        def pintar_pagos():
            cont_pagos.clear()
            with cont_pagos:
                pagos = db.leer_pagos_proveedor(proveedor=proveedor, mes=estado["mes"])
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
                        pagination=8,
                        on_select=lambda e: sel_pago.update(
                            {"id": e.selection[0]["ID_Pago"] if e.selection else None}
                        ),
                    ).props("flat dense bordered")
                    ui.button(
                        "Eliminar pago seleccionado",
                        icon="delete",
                        on_click=lambda: _eliminar_pago(),
                    ).props("flat color=negative dense")
                else:
                    ui.label("Sin pagos registrados.").classes("text-sm opacity-50")

        def _eliminar_pago():
            if not sel_pago["id"]:
                ui.notify("Seleccioná un pago.", type="warning")
                return
            db.eliminar_pago_proveedor(sel_pago["id"])
            ui.notify("Pago eliminado.", type="positive")
            pintar()

        pintar_pagos()

        with ui.card().classes("w-full bg-gray-100 dark:bg-gray-800"):
            ui.label("Registrar pago").classes("font-semibold text-sm")
            with ui.row().classes("w-full flex-wrap items-end gap-2"):
                f_p = input_fecha("Fecha del pago")
                m_p = ui.number("Monto", value=saldo, format="%.2f")
                met_p = ui.select(METODOS, value="Efectivo", label="Método", new_value_mode="add").classes("w-40")
                n_p = ui.input("Nota")
                ui.button("Registrar pago", icon="payments", on_click=lambda: _registrar()).props("unelevated dense")

        def _registrar():
            if not m_p.value or m_p.value <= 0:
                ui.notify("Monto inválido.", type="warning")
                return
            db.registrar_pago_proveedor(
                proveedor, estado["mes"], m_p.value, (f_p.value or "").strip() or None, met_p.value or "", n_p.value or ""
            )
            ui.notify("Pago registrado.", type="positive")
            pintar()

    def _dialogo_nueva_venta():
        clientes_data = {c["Nombre_Razon_Social"]: c for c in db.leer_clientes()}
        clientes = [c["Nombre_Razon_Social"] for c in clientes_data.values() if c["Nombre_Razon_Social"]]
        mapa = {}
        sel = {"facturas": []}
        label_suma = ui.label("").classes("text-sm font-semibold")
        monto = ui.number("Monto Nominal", value=0.0, format="%.2f")
        precio = ui.number("Precio a Cobrar", value=0.0, format="%.2f")

        def _pct_cliente(nombre):
            info = clientes_data.get(nombre)
            try:
                return float(info["Pct_Venta"]) if info and info.get("Pct_Venta") else 5.0
            except (TypeError, ValueError):
                return 5.0

        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[860px]"):
            ui.label("Nueva venta").classes("text-lg font-bold")
            with ui.grid(columns=2).classes("w-full gap-2"):
                sel_cliente = ui.select(
                    clientes + ["➕ Nuevo cliente..."],
                    value=clientes[0] if clientes else "➕ Nuevo cliente...",
                    label="Cliente (su % calcula lo que le cobrás)",
                    on_change=lambda e: (_toggle_nuevo(e.value), _refrescar_disponibles(), _actualizar()),
                ).classes("w-full")
                nuevo_nombre = ui.input("Nombre del nuevo cliente").props("disable")
            nuevo_nit = ui.input("NIT del nuevo cliente").props("disable")

            cont_disp = ui.column().classes("w-full gap-2")

            def _toggle_nuevo(valor):
                if valor == "➕ Nuevo cliente...":
                    nuevo_nombre.props(remove="disable")
                    nuevo_nit.props(remove="disable")
                else:
                    nuevo_nombre.props("disable")
                    nuevo_nit.props("disable")

            def _refrescar_disponibles():
                cont_disp.clear()
                cliente_sel = sel_cliente.value
                objetivo = (
                    db.norm_cliente(db.canon_cliente(cliente_sel))
                    if cliente_sel and cliente_sel != "➕ Nuevo cliente..."
                    else ""
                )
                disponibles = [
                    f
                    for f in db.leer_facturas_mes(estado["mes"])
                    if not f.get("Venta_ID")
                    and (
                        not objetivo
                        or not (f.get("Razon_Social_Cliente") or "").strip()
                        or db.norm_cliente(db.canon_cliente(f["Razon_Social_Cliente"])) == objetivo
                    )
                ]
                mapa.clear()
                mapa.update({f["ID"]: f for f in disponibles})
                sel["facturas"] = []
                monto.value = 0.0
                precio.value = 0.0
                with cont_disp:
                    if not disponibles:
                        ui.label("Todas las facturas de este mes ya están vendidas.").classes("opacity-50 text-sm")
                        return
                    ui.label("Marcá con ✅ las facturas que le vendés:").classes("text-sm opacity-70")
                    if objetivo:
                        ui.label(
                            "Se muestran las facturas de este cliente y las que todavía no tienen comprador."
                        ).classes("text-xs opacity-50")
                    ui.table(
                        columns=COLUMNAS_FACTURAS,
                        rows=[
                            {
                                "ID": f["ID"],
                                "nro": f["Nro_Factura"] or "-",
                                "cliente": f.get("Razon_Social_Cliente") or "—",
                                "prov": f["Proveedor_Asignado"],
                                "fecha": f["Fecha_Emision"] or "-",
                                "monto": f"{f['Monto_Total']:,.2f}",
                                "cobrar": f"{f['Monto_Total'] * _pct_cliente(sel_cliente.value) / 100:,.2f}",
                            }
                            for f in disponibles
                        ],
                        row_key="ID",
                        selection="multiple",
                        pagination=12,
                        on_select=lambda e: _seleccion(e.selection or []),
                    ).classes("w-full").props("flat dense bordered")

            def _seleccion(filas):
                sel["facturas"] = [f["ID"] for f in filas]
                _actualizar()

            def _actualizar():
                suma_nominal = sum(mapa[fid]["Monto_Total"] for fid in sel["facturas"] if fid in mapa)
                pct = _pct_cliente(sel_cliente.value)
                sugerido = round(suma_nominal * pct / 100.0, 2)
                monto.value = round(suma_nominal, 2)
                precio.value = sugerido
                nombre_cli = sel_cliente.value if sel_cliente.value != "➕ Nuevo cliente..." else "el cliente nuevo"
                label_suma.set_text(
                    f"Nominal: Bs {suma_nominal:,.2f} · {nombre_cli} al {pct:g}% → cobrar Bs {sugerido:,.2f} (editable)"
                )

            _refrescar_disponibles()

            with ui.row().classes("w-full flex-wrap items-end gap-2"):
                e_entregado = ui.checkbox("Entregado ✔ (pdf/físico/excel)", value=False)
                notas = ui.input("Notas").classes("flex-1")
            label_suma

            def _registrar():
                cliente = sel_cliente.value
                if cliente == "➕ Nuevo cliente...":
                    cliente = (nuevo_nombre.value or "").strip()
                    if not cliente:
                        ui.notify("Indicá el nombre del nuevo cliente.", type="warning")
                        return
                    db.agregar_cliente(cliente, nuevo_nit.value or "")
                if not sel["facturas"]:
                    ui.notify("Marcá al menos una factura en la tabla.", type="warning")
                    return
                db.registrar_venta(
                    estado["mes"],
                    cliente,
                    monto.value or 0.0,
                    precio.value or 0.0,
                    "PENDIENTE",
                    list(sel["facturas"]),
                    notas.value or "",
                    "SI" if e_entregado.value else "",
                )
                ui.notify(f"Venta registrada a {cliente}.", type="positive")
                dialogo.close()
                pintar()

            with ui.row().classes("w-full justify-end"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Registrar Venta", icon="point_of_sale", on_click=_registrar).props(
                    "unelevated no-caps color=primary"
                )
        dialogo.open()

    def pintar_wrapper():
        pintar()

    pintar_wrapper()
