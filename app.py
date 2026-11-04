import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

import db
import exportador
from config import ESTADOS_COBRO, ESTADOS_PAGO, MAX_WORKERS
from extractor import procesar_archivo

st.set_page_config(page_title="Gestor Fiscal OCR", layout="wide", page_icon="📑")

db.inicializar()

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@st.cache_data(ttl=60, show_spinner=False)
def _facturas(mes: str) -> list:
    return db.leer_facturas_mes(mes)


@st.cache_data(ttl=60, show_spinner=False)
def _ventas(mes: str) -> list:
    return db.leer_ventas_mes(mes)


@st.cache_data(ttl=60, show_spinner=False)
def _proveedores() -> list:
    return db.leer_proveedores()


@st.cache_data(ttl=60, show_spinner=False)
def _clientes() -> list:
    return db.leer_clientes()


@st.cache_data(ttl=60, show_spinner=False)
def _campos() -> list:
    return db.listar_campos()


@st.cache_data(ttl=60, show_spinner=False)
def _todas_compras() -> list:
    return db.leer_todas_compras()


def _claves_activos() -> list:
    return [c["clave"] for c in _campos() if c["activo"] and c["clave"] != "ID"]


def _claves_editables() -> list:
    return [
        c["clave"]
        for c in _campos()
        if c["activo"] and c["clave"] not in ("ID", "Nombre_Archivo", "Venta_ID")
    ]


def _nombre_mes(anio: int, mes: int) -> str:
    return f"{anio}_{mes:02d}_{MESES_ES[mes - 1]}"


def _opciones_meses() -> list:
    hoy = datetime.date.today()
    total = hoy.year * 12 + (hoy.month - 1)
    opciones = []
    for offset in range(-2, 7):
        anio, mes0 = divmod(total + offset, 12)
        opciones.append(_nombre_mes(anio, mes0 + 1))
    return opciones


def _df_facturas(registros: list) -> pd.DataFrame:
    claves = [c["clave"] for c in _campos() if c["clave"] != "ID"]
    df = pd.DataFrame(registros)
    for col in claves:
        if col not in df.columns:
            df[col] = ""
    for campo in _campos():
        if campo["tipo"] == "numero" and campo["clave"] in df.columns:
            df[campo["clave"]] = pd.to_numeric(df[campo["clave"]], errors="coerce").fillna(0.0)
    return df


def _config_columnas(opciones_prov: list) -> dict:
    cfg = {}
    for c in _campos():
        if not c["activo"]:
            continue
        k = c["clave"]
        if k == "Estado_Pago":
            cfg[k] = st.column_config.SelectboxColumn("Estado Pago", options=ESTADOS_PAGO)
        elif k == "Proveedor_Asignado":
            cfg[k] = st.column_config.SelectboxColumn(
                "Proveedor", options=sorted({p for p in opciones_prov if p})
            )
        elif k == "Venta_ID":
            cfg[k] = st.column_config.TextColumn("Venta", disabled=True)
        elif c["tipo"] == "numero":
            cfg[k] = st.column_config.NumberColumn(c["etiqueta"], format="%.2f")
        elif c["tipo"] == "booleano":
            cfg[k] = st.column_config.CheckboxColumn(c["etiqueta"])
        else:
            cfg[k] = st.column_config.TextColumn(
                c["etiqueta"], width="medium" if len(c["etiqueta"]) < 18 else "large"
            )
    return cfg


def _normaliza(valor):
    if isinstance(valor, float):
        return round(valor, 2)
    if valor is None:
        return ""
    return str(valor).strip()


def _difieren(a: dict, b: dict, campos_lista: list) -> bool:
    return any(_normaliza(a.get(c)) != _normaliza(b.get(c)) for c in campos_lista)


def _toast_y_recargar(mensaje: str, claves_editor: list = None):
    st.session_state["msg_exito"] = mensaje
    for clave in claves_editor or []:
        st.session_state.pop(clave, None)
    st.cache_data.clear()
    st.rerun()


if "msg_exito" in st.session_state:
    st.success(st.session_state.pop("msg_exito"))

with st.sidebar:
    st.header("⚙️ Configuración")
    opciones_meses = _opciones_meses()
    mes_hoy = _nombre_mes(datetime.date.today().year, datetime.date.today().month)
    mes_seleccionado = st.selectbox(
        "Mes de operación:",
        opciones_meses,
        index=opciones_meses.index(mes_hoy) if mes_hoy in opciones_meses else 0,
    )
    lista_proveedores = _proveedores()
    proveedor_actual = st.selectbox("Proveedor actual:", lista_proveedores)
    st.caption("💾 Base de datos local: facturas.db")

tab_carga, tab_registros, tab_prov, tab_clientes, tab_ventas, tab_balance, tab_campos = st.tabs(
    [
        "📥 Carga de Facturas",
        "🗂 Facturas Guardadas",
        "👥 Proveedores",
        "🧑‍💼 Clientes",
        "💼 Ventas y Cobros",
        "📊 Estado de Cuenta",
        "⚙️ Campos",
    ]
)

st.title("📑 Sistema de Control Fiscal y Facturación")

with tab_carga:
    st.subheader(f"Extracción de Datos — {mes_seleccionado}")
    archivos = st.file_uploader(
        "Arrastra imágenes o PDFs de facturas aquí",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
    )

    if archivos and st.button("🚀 Extraer Datos con IA", type="primary"):
        claves_existentes = db.leer_claves_existentes(mes_seleccionado)
        barra = st.progress(0.0, text="Procesando...")
        resultados = {}
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(archivos))) as pool:
            futuros = {pool.submit(procesar_archivo, a.getvalue(), a.name): a.name for a in archivos}
            for hecho, fut in enumerate(as_completed(futuros), 1):
                resultados[futuros[fut]] = fut.result()
                barra.progress(hecho / len(archivos), text=f"{hecho}/{len(archivos)} procesadas...")
        barra.empty()

        datos = []
        for arch in archivos:
            d = resultados[arch.name]
            registro = {
                "Nombre_Archivo": arch.name,
                "Proveedor_Asignado": proveedor_actual,
                "Estado_Pago": "PENDIENTE",
                "Venta_ID": "",
            }
            registro.update(d)
            clave = (
                str(registro.get("NIT_Emisor", "")).strip().upper(),
                str(registro.get("Nro_Factura", "")).strip().upper(),
                str(registro.get("Cod_Autorizacion", "")).strip().upper(),
            )
            registro["Duplicado"] = any(clave) and clave in claves_existentes
            registro["Incluir"] = not registro["Duplicado"]
            datos.append(registro)
        st.session_state["facturas_procesadas"] = datos
        st.session_state.pop("editor_carga", None)
        st.rerun()

    if st.session_state.get("facturas_procesadas"):
        datos = st.session_state["facturas_procesadas"]
        n_dup = sum(1 for d in datos if d.get("Duplicado"))
        if n_dup:
            st.warning(
                f"⚠️ {n_dup} factura(s) parecen duplicadas (mismo NIT + N° + código de autorización). "
                "Revisa la columna 'Incluir' antes de guardar."
            )
        df = _df_facturas(datos).drop(columns=["ID"], errors="ignore")
        df["Duplicado"] = df.get("Duplicado", False)
        df["Incluir"] = df.get("Incluir", True)
        columnas_orden = ["Nombre_Archivo", "Duplicado", "Incluir"] + [
            c for c in _claves_activos() if c != "Nombre_Archivo"
        ]
        df = df[[c for c in columnas_orden if c in df.columns]]

        cfg = _config_columnas(lista_proveedores)
        cfg["Duplicado"] = st.column_config.CheckboxColumn("Duplicado", disabled=True)
        cfg["Incluir"] = st.column_config.CheckboxColumn("Incluir")
        editado = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="editor_carga",
            disabled=["Nombre_Archivo", "Duplicado"],
            column_config=cfg,
        )

        if st.button("💾 Guardar Facturas", type="primary"):
            registros = [r for r in editado.to_dict(orient="records") if r.get("Incluir", True)]
            if not registros:
                st.warning("No hay facturas marcadas para incluir.")
            else:
                n = db.registrar_facturas_batch(mes_seleccionado, registros)
                st.session_state["facturas_procesadas"] = []
                _toast_y_recargar(f"✅ {n} factura(s) guardadas en {mes_seleccionado}.", ["editor_carga"])

with tab_registros:
    st.subheader(f"Facturas Guardadas — {mes_seleccionado}")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption("Edita las celdas, cambia el Estado de Pago o marca filas para eliminar y luego guarda los cambios.")
    with col_b:
        try:
            datos_excel, nombre_excel = exportador.exportar_mes_excel(mes_seleccionado)
            st.download_button(
                "📤 Exportar mes a Excel",
                data=datos_excel,
                file_name=nombre_excel,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.caption(f"Export no disponible: {e}")

    if st.button("🔄 Cargar facturas del mes"):
        st.session_state["df_registros"] = _df_facturas(_facturas(mes_seleccionado))
        st.session_state["registros_mes"] = mes_seleccionado
        st.session_state.pop("editor_registros", None)
        st.rerun()

    df_reg = st.session_state.get("df_registros")
    mes_reg = st.session_state.get("registros_mes")
    if df_reg is not None and mes_reg == mes_seleccionado:
        if df_reg.empty:
            st.info("Aún no hay facturas registradas en este mes.")
        else:
            original = df_reg.to_dict(orient="records")
            editable = df_reg.copy()
            editable["Eliminar"] = False
            columnas_edit = _claves_editables()
            editado_reg = st.data_editor(
                editable,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="editor_registros",
                disabled=["ID", "Nombre_Archivo", "Venta_ID", "Eliminar"],
                column_config=_config_columnas(lista_proveedores),
            )

            if st.button("💾 Guardar cambios", type="primary"):
                registros_nuevos = editado_reg.to_dict(orient="records")
                marcados = {r["ID"] for r in registros_nuevos if r.get("Eliminar")}
                presentes = {r["ID"] for r in registros_nuevos}
                actualizados, eliminados = 0, 0
                for r in registros_nuevos:
                    if r.get("Eliminar"):
                        continue
                    previo = next((o for o in original if o["ID"] == r["ID"]), None)
                    if previo is not None and _difieren(previo, r, columnas_edit):
                        if db.actualizar_factura(mes_seleccionado, r):
                            actualizados += 1
                for r in original:
                    if r["ID"] in marcados or r["ID"] not in presentes:
                        if db.eliminar_factura(mes_seleccionado, r["ID"]):
                            eliminados += 1
                st.session_state["df_registros"] = _df_facturas(_facturas(mes_seleccionado))
                _toast_y_recargar(
                    f"✅ {actualizados} actualizada(s), {eliminados} eliminada(s).", ["editor_registros"]
                )
    elif df_reg is not None:
        st.info(f"La tabla cargada corresponde a {mes_reg}. Vuelve a cargar para este mes.")

with tab_prov:
    st.subheader("Proveedores")
    with st.form("nuevo_prov", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
        nit = c1.text_input("NIT:")
        nombre = c2.text_input("Razón Social:")
        telefono = c3.text_input("Teléfono:")
        comision = c4.number_input("Comisión (%):", min_value=0.0, max_value=100.0, step=0.5)
        if st.form_submit_button("➕ Agregar Proveedor"):
            if nombre.strip():
                db.agregar_proveedor(nit, nombre, telefono, comision)
                st.session_state["msg_exito"] = f"✅ Proveedor '{nombre}' agregado."
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("La razón social es obligatoria.")

    proveedores_full = db.leer_proveedores_full()
    if proveedores_full:
        st.dataframe(
            pd.DataFrame(proveedores_full),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Comision_Pactada_Pct": st.column_config.NumberColumn("Comisión %", format="%.1f")
            },
        )
        with st.form("eliminar_prov"):
            a_eliminar = st.selectbox(
                "Eliminar proveedor:",
                [p["Nombre_Proveedor"] for p in proveedores_full if p["Nombre_Proveedor"]],
            )
            if st.form_submit_button("🗑 Eliminar"):
                db.eliminar_proveedor(a_eliminar)
                st.session_state["msg_exito"] = f"🗑 Proveedor '{a_eliminar}' eliminado."
                st.cache_data.clear()
                st.rerun()
    else:
        st.info("Aún no hay proveedores registrados.")

with tab_clientes:
    st.subheader("Clientes")
    with st.form("nuevo_cliente", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        nombre_cli = c1.text_input("Nombre / Razón Social:")
        nit_cli = c2.text_input("NIT:")
        tel_cli = c3.text_input("Teléfono:")
        if st.form_submit_button("➕ Agregar Cliente"):
            if nombre_cli.strip():
                db.agregar_cliente(nombre_cli, nit_cli, tel_cli)
                st.session_state["msg_exito"] = f"✅ Cliente '{nombre_cli}' agregado."
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")

    clientes_lista = _clientes()
    if clientes_lista:
        st.dataframe(
            pd.DataFrame(clientes_lista)[
                ["ID_Cliente", "Nombre_Razon_Social", "NIT", "Telefono", "Notas"]
            ],
            use_container_width=True,
            hide_index=True,
        )
        with st.form("eliminar_cliente"):
            a_eliminar_cli = st.selectbox(
                "Eliminar cliente:",
                [c["Nombre_Razon_Social"] for c in clientes_lista if c["Nombre_Razon_Social"]],
            )
            if st.form_submit_button("🗑 Eliminar"):
                db.eliminar_cliente(a_eliminar_cli)
                st.session_state["msg_exito"] = f"🗑 Cliente '{a_eliminar_cli}' eliminado."
                st.cache_data.clear()
                st.rerun()
    else:
        st.info("Aún no hay clientes registrados.")

with tab_ventas:
    st.subheader(f"Ventas de Crédito Fiscal — {mes_seleccionado}")

    st.markdown("**Registrar nueva venta**")
    clientes_reg = _clientes()
    nombres_clientes = [c["Nombre_Razon_Social"] for c in clientes_reg if c["Nombre_Razon_Social"]]
    eleccion_cli = st.selectbox(
        "Cliente:", nombres_clientes + ["➕ Nuevo cliente..."], key="sel_cliente_venta"
    )
    nombre_final_cli = eleccion_cli
    nit_final_cli = ""
    if eleccion_cli == "➕ Nuevo cliente...":
        c1, c2, c3 = st.columns([2, 1, 1])
        nombre_final_cli = c1.text_input("Nombre / Razón Social del cliente:", key="nuevo_cli_nombre")
        nit_final_cli = c2.text_input("NIT:", key="nuevo_cli_nit")
        c3.text_input("Teléfono:", key="nuevo_cli_tel")

    facturas_disponibles = [f for f in _facturas(mes_seleccionado) if not f.get("Venta_ID")]
    mapa_facturas = {f["ID"]: f for f in facturas_disponibles}

    def _etiqueta_factura(id_factura):
        f = mapa_facturas.get(id_factura, {})
        return f"N° {f.get('Nro_Factura','?')} — {f.get('Proveedor_Asignado','?')} — crédito Bs {f.get('Credito_Fiscal',0):,.2f}"

    seleccion = st.multiselect(
        "Facturas a vender (solo se listan las no vendidas):",
        options=list(mapa_facturas.keys()),
        format_func=_etiqueta_factura,
        key="sel_facturas_venta",
    )
    suma_credito = sum(mapa_facturas[i]["Credito_Fiscal"] for i in seleccion)

    c1, c2, c3, c4 = st.columns(4)
    monto_credito = c1.number_input(
        "Crédito Vendido:", min_value=0.0, step=0.01, value=float(suma_credito), key="venta_monto"
    )
    st.caption(f"Crédito fiscal de la selección: Bs {suma_credito:,.2f}")
    precio_cobrado = c2.number_input("Precio a Cobrar:", min_value=0.0, step=0.01, key="venta_precio")
    estado = c3.selectbox("Estado:", ESTADOS_COBRO, key="venta_estado")
    notas = c4.text_input("Notas:", key="venta_notas")

    if st.button("💾 Registrar Venta", type="primary"):
        if not nombre_final_cli or nombre_final_cli == "➕ Nuevo cliente...":
            st.error("Indicá el cliente (existente o nuevo).")
        elif not seleccion:
            st.error("Seleccioná al menos una factura para vender.")
        else:
            if eleccion_cli == "➕ Nuevo cliente...":
                db.agregar_cliente(nombre_final_cli, nit_final_cli)
            db.registrar_venta(
                mes_seleccionado,
                nombre_final_cli,
                monto_credito,
                precio_cobrado,
                estado,
                seleccion,
                notas,
            )
            st.session_state.pop("df_ventas", None)
            _toast_y_recargar(
                f"✅ Venta registrada a '{nombre_final_cli}' por {len(seleccion)} factura(s).",
                ["editor_ventas"],
            )

    st.divider()

    if st.button("🔄 Cargar ventas del mes", key="btn_cargar_ventas"):
        st.session_state["df_ventas"] = pd.DataFrame(_ventas(mes_seleccionado))
        st.session_state["ventas_mes"] = mes_seleccionado
        st.session_state.pop("editor_ventas", None)
        st.rerun()

    df_ven = st.session_state.get("df_ventas")
    mes_ven = st.session_state.get("ventas_mes")
    if df_ven is not None and mes_ven == mes_seleccionado:
        if df_ven.empty:
            st.info("Aún no hay ventas registradas en este mes.")
        else:
            original_ven = df_ven.to_dict(orient="records")
            editable_ven = df_ven.copy()
            editable_ven["Eliminar"] = False
            editado_ven = st.data_editor(
                editable_ven,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="editor_ventas",
                disabled=["ID_Venta", "Mes", "Facturas_IDs", "Eliminar"],
                column_config={
                    "Eliminar": st.column_config.CheckboxColumn("🗑 Eliminar"),
                    "Cliente_Razon_Social": st.column_config.TextColumn("Cliente", width="medium"),
                    "Monto_Credito_Vendido": st.column_config.NumberColumn("Crédito Vendido", format="%.2f"),
                    "Precio_Cobrado": st.column_config.NumberColumn("Precio Cobrado", format="%.2f"),
                    "Estado_Cobro": st.column_config.SelectboxColumn("Estado", options=ESTADOS_COBRO),
                    "Facturas_IDs": st.column_config.TextColumn("Facturas vendidas", width="large"),
                    "Notas": st.column_config.TextColumn("Notas", width="medium"),
                },
            )
            if st.button("💾 Guardar cambios", key="btn_guardar_ventas"):
                registros_ven = editado_ven.to_dict(orient="records")
                marcados_ven = {r["ID_Venta"] for r in registros_ven if r.get("Eliminar")}
                presentes_ven = {r["ID_Venta"] for r in registros_ven}
                actualizados, eliminados = 0, 0
                campos_venta = [
                    "Cliente_Razon_Social",
                    "Monto_Credito_Vendido",
                    "Precio_Cobrado",
                    "Estado_Cobro",
                    "Facturas_IDs",
                    "Notas",
                ]
                for r in registros_ven:
                    if r.get("Eliminar"):
                        continue
                    previo = next((o for o in original_ven if o["ID_Venta"] == r["ID_Venta"]), None)
                    if previo is not None and _difieren(previo, r, campos_venta):
                        if db.actualizar_venta(mes_seleccionado, r):
                            actualizados += 1
                for r in original_ven:
                    if r["ID_Venta"] in marcados_ven or r["ID_Venta"] not in presentes_ven:
                        if db.eliminar_venta(r):
                            eliminados += 1
                st.session_state["df_ventas"] = pd.DataFrame(_ventas(mes_seleccionado))
                _toast_y_recargar(
                    f"✅ {actualizados} venta(s) actualizada(s), {eliminados} eliminada(s).", ["editor_ventas"]
                )
    elif df_ven is not None:
        st.info(f"La tabla cargada corresponde a {mes_ven}. Vuelve a cargar para este mes.")

with tab_balance:
    st.subheader(f"Estado de Cuenta — {mes_seleccionado}")
    col_f, col_e = st.columns([3, 1])
    with col_f:
        filtro_prov = st.selectbox("Filtrar por proveedor:", ["TODOS"] + sorted({p for p in lista_proveedores if p}))
    with col_e:
        try:
            datos_excel_b, nombre_excel_b = exportador.exportar_mes_excel(mes_seleccionado)
            st.download_button(
                "📤 Exportar Excel",
                data=datos_excel_b,
                file_name=nombre_excel_b,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception:
            pass

    if st.button("🔄 Actualizar Balance"):
        st.cache_data.clear()
        st.session_state["cargar_balance"] = True
        st.rerun()

    if st.session_state.get("cargar_balance"):
        facturas_todas = _facturas(mes_seleccionado)
        facturas = [
            f for f in facturas_todas
            if filtro_prov == "TODOS" or f.get("Proveedor_Asignado") == filtro_prov
        ]
        ventas = _ventas(mes_seleccionado)

        total_compras = sum(f["Monto_Total"] for f in facturas)
        credito_comprado = sum(f["Credito_Fiscal"] for f in facturas)
        credito_vendido = sum(v["Monto_Credito_Vendido"] for v in ventas)
        cobrado = sum(v["Precio_Cobrado"] for v in ventas if v["Estado_Cobro"] == "COBRADO")
        por_cobrar = sum(v["Precio_Cobrado"] for v in ventas if v["Estado_Cobro"] != "COBRADO")
        ganancia = sum(v["Precio_Cobrado"] for v in ventas) - credito_vendido
        n_vendidas = len([f for f in facturas if f.get("Venta_ID")])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("N° Facturas", len(facturas))
        m2.metric("Total Compras", f"{total_compras:,.2f}")
        m3.metric("Crédito Comprado", f"{credito_comprado:,.2f}")
        m4.metric("Crédito Vendido", f"{credito_vendido:,.2f}")

        m5, m6, m7, m8 = st.columns(4)
        m5.metric("Crédito Disponible", f"{credito_comprado - credito_vendido:,.2f}")
        m6.metric("Cobrado", f"{cobrado:,.2f}")
        m7.metric("Por Cobrar", f"{por_cobrar:,.2f}")
        m8.metric("Ganancia Bruta", f"{ganancia:,.2f}")

        st.caption(f"Facturas vendidas: {n_vendidas} de {len(facturas)}")

        st.divider()
        c_izq, c_der = st.columns(2)
        with c_izq:
            st.markdown("**Facturas del mes**")
            if facturas:
                st.dataframe(
                    _df_facturas(facturas)[
                        ["Proveedor_Asignado", "Razon_Social", "Nro_Factura", "Fecha_Emision", "Monto_Total", "Credito_Fiscal", "Estado_Pago", "Venta_ID"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Sin facturas registradas.")
        with c_der:
            st.markdown("**Ventas del mes**")
            if ventas:
                st.dataframe(
                    pd.DataFrame(ventas)[
                        ["Cliente_Razon_Social", "Monto_Credito_Vendido", "Precio_Cobrado", "Estado_Cobro", "Facturas_IDs", "Notas"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Sin ventas registradas.")

        st.divider()
        st.markdown("**Acumulado anual (compras)**")
        todas = _todas_compras()
        if todas:
            df_anual = pd.DataFrame(todas)
            df_anual["Monto_Total"] = pd.to_numeric(df_anual["Monto_Total"], errors="coerce").fillna(0.0)
            df_anual["Credito_Fiscal"] = pd.to_numeric(df_anual["Credito_Fiscal"], errors="coerce").fillna(0.0)
            resumen = (
                df_anual.groupby("Mes")
                .agg(Facturas=("ID", "count"), Total_Compras=("Monto_Total", "sum"), Credito_Fiscal=("Credito_Fiscal", "sum"))
                .reset_index()
                .sort_values("Mes")
            )
            st.dataframe(resumen, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay facturas registradas.")

with tab_campos:
    st.subheader("⚙️ Configuración de Campos de Factura")
    st.caption(
        "Define qué datos se guardan de cada factura y cuáles pide la IA al extraer. "
        "Desactivar un campo NO borra su información histórica, solo la oculta. "
        "Los campos de núcleo no se pueden eliminar porque el sistema los usa (montos, factura, estados)."
    )

    campos_lista = db.listar_campos()
    df_campos = pd.DataFrame(campos_lista)[
        ["clave", "etiqueta", "tipo", "descripcion", "nucleo", "activo", "en_ia", "orden"]
    ]
    editado_campos = st.data_editor(
        df_campos,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="editor_campos",
        disabled=["clave", "nucleo"],
        column_config={
            "clave": st.column_config.TextColumn("Clave", disabled=True),
            "etiqueta": st.column_config.TextColumn("Etiqueta visible"),
            "tipo": st.column_config.SelectboxColumn(
                "Tipo", options=["texto", "numero", "fecha", "booleano"]
            ),
            "descripcion": st.column_config.TextColumn("Descripción para la IA", width="large"),
            "nucleo": st.column_config.CheckboxColumn("Núcleo", disabled=True),
            "activo": st.column_config.CheckboxColumn("Activo"),
            "en_ia": st.column_config.CheckboxColumn("Pedir a la IA"),
            "orden": st.column_config.NumberColumn("Orden", step=1),
        },
    )

    if st.button("💾 Guardar configuración de campos"):
        n_cambios = 0
        for r in editado_campos.to_dict(orient="records"):
            previo = next((c for c in campos_lista if c["clave"] == r["clave"]), None)
            if previo is None:
                continue
            cambios = {}
            for k in ("etiqueta", "tipo", "descripcion"):
                if str(r.get(k, "")).strip() != str(previo.get(k, "")):
                    cambios[k] = str(r.get(k, "")).strip()
            for k in ("activo", "en_ia"):
                if bool(r.get(k)) != bool(previo.get(k)):
                    cambios[k] = bool(r.get(k))
            if int(r.get("orden", 0)) != int(previo.get("orden", 0)):
                cambios["orden"] = int(r.get("orden", 0))
            if cambios:
                db.actualizar_campo(r["clave"], **cambios)
                n_cambios += 1
        _toast_y_recargar(f"✅ {n_cambios} campo(s) actualizado(s).", ["editor_campos"])

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        with st.form("nuevo_campo", clear_on_submit=True):
            st.markdown("**Agregar nuevo campo**")
            nueva_etiqueta = st.text_input("Etiqueta (nombre visible):")
            nuevo_tipo = st.selectbox("Tipo:", ["texto", "numero", "fecha", "booleano"])
            nueva_desc = st.text_input("Descripción para la IA:")
            nueva_en_ia = st.checkbox("Pedir este campo a la IA al extraer", value=True)
            if st.form_submit_button("➕ Agregar Campo"):
                if nueva_etiqueta.strip():
                    clave = db.agregar_campo(nueva_etiqueta, nuevo_tipo, nueva_desc, nueva_en_ia)
                    _toast_y_recargar(f"✅ Campo '{clave}' agregado.", ["editor_campos"])
                else:
                    st.error("La etiqueta es obligatoria.")
    with c2:
        with st.form("eliminar_campo"):
            st.markdown("**Eliminar campo extra**")
            eliminables = [c["clave"] for c in campos_lista if not c["nucleo"]]
            if eliminables:
                campo_eliminar = st.selectbox("Campo:", eliminables)
                if st.form_submit_button("🗑 Eliminar"):
                    db.eliminar_campo(campo_eliminar)
                    _toast_y_recargar(f"🗑 Campo '{campo_eliminar}' eliminado.", ["editor_campos"])
            else:
                st.info("No hay campos extras para eliminar.")
