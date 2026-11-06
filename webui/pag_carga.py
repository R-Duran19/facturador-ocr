"""Portada y trabajo diario: carga de facturas por proveedor con cola en vivo."""

import re
from datetime import date

from nicegui import ui

import config
import db
from ocr_queue import COLA
from webui.componentes import chips_estado, strip_metricas, tarjeta_gasto_ia
from webui.pag_facturas import dialogo_factura
from webui.plantilla import pagina

EXTENSIONES = {".jpg", ".jpeg", ".png", ".pdf"}

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

COLUMNAS_ARCHIVO = [
    {"name": "nombre", "label": "Archivo", "field": "nombre", "align": "left"},
    {"name": "estado", "label": "Estado", "field": "estado", "align": "center"},
    {"name": "nro_factura", "label": "N° Factura", "field": "nro_factura", "align": "left"},
    {"name": "razon_social", "label": "Emisor", "field": "razon_social", "align": "left"},
    {"name": "cliente", "label": "Cliente", "field": "cliente", "align": "left"},
    {"name": "monto_total", "label": "Monto", "field": "monto_total", "align": "right"},
    {"name": "observaciones", "label": "Observaciones", "field": "observaciones", "align": "left"},
    {"name": "error", "label": "Detalle del error", "field": "error", "align": "left"},
]


def _mes_actual() -> str:
    hoy = date.today()
    return f"{hoy.year}_{hoy.month:02d}_{MESES_ES[hoy.month - 1]}"


def _legible(nombre_mes: str) -> str:
    try:
        anio, num, _ = str(nombre_mes).split("_", 2)
        return f"{MESES_ES[int(num) - 1]} {anio}"
    except (ValueError, IndexError):
        return str(nombre_mes)


@pagina("/")
def pagina_carga():
    ui.add_head_html(
        """
<style>
.dropzone .q-uploader {
  box-shadow: none;
  background: #F3F9F5;
  border: 2px dashed #175E3B;
  border-radius: 14px;
  width: 100%;
}
.dropzone .q-uploader__header {
  background: transparent;
  color: #175E3B;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-height: 150px;
  cursor: pointer;
  position: relative;
}
.dropzone .q-uploader__header::before {
  content: 'cloud_upload';
  font-family: 'Material Icons';
  font-size: 46px;
  line-height: 1;
}
.dropzone .q-uploader__header::after {
  content: 'Arrastrá acá  ·  o hacé clic';
  font-size: 15px;
  font-weight: 700;
}
.dropzone .q-uploader__header .q-uploader__title,
.dropzone .q-uploader__header .q-uploader__subtitle { font-size: 11px; opacity: .55; }
.dropzone .q-uploader__header .q-btn { display: none; }
.dropzone .q-uploader__list { min-height: 0; }
.body--dark .dropzone .q-uploader { background: rgba(23, 94, 59, 0.12); border-color: #6EE7A0; }
.body--dark .dropzone .q-uploader__header { color: #86EFAC; }
</style>
<script>
document.addEventListener('click', function (ev) {
  var cabecera = ev.target.closest('.dropzone .q-uploader__header');
  if (!cabecera || ev.target.closest('.q-btn')) return;
  var boton = cabecera.querySelector('.q-btn, button');
  if (boton) boton.click();
});
</script>
"""
    )

    meses = sorted(set(db.listar_meses()), reverse=True)
    mes_hoy = _mes_actual()
    opciones_mes = list(meses)
    proveedores = [p for p in db.leer_proveedores() if p != "Sin Asignar"]
    fichas = {p["Nombre_Proveedor"]: p for p in db.leer_proveedores_full()}
    opciones_prov = [p for p in proveedores if p in fichas] or proveedores

    strip_cont = ui.column().classes("w-full")

    @ui.refreshable
    def pintar_strip():
        with ui.row().classes("w-full flex-wrap items-start gap-3"):
            with ui.column().classes("flex-1 min-w-[420px] gap-0"):
                strip_metricas(sel_mes.value or mes_hoy)
            with ui.column().classes("items-end"):
                tarjeta_gasto_ia()

    with ui.row().classes("w-full flex-wrap items-end gap-3"):
        sel_mes = ui.select(
            opciones_mes,
            value=opciones_mes[0] if opciones_mes else mes_hoy,
            label="Mes de trabajo (crear uno nuevo con ＋ Nuevo mes)",
            new_value_mode="add",
            on_change=lambda e: pintar_strip.refresh(),
        ).classes("w-full max-w-md")
        ui.button("＋ Nuevo mes", icon="calendar_month", on_click=lambda: _dialogo_nuevo_mes()).props("flat dense").tooltip(
            "Crear un mes para registrar facturas"
        )
        ui.space()
        ui.button("➕ Factura manual", icon="post_add", on_click=_factura_manual).props("flat dense").tooltip(
            "Registrar una factura a mano (sin IA), en el mes seleccionado"
        )
    ui.label(f"📍 Estamos en: {_legible(mes_hoy)} · Mes seleccionado: {_legible(sel_mes.value or '')}").classes(
        "text-xs opacity-60 -mt-2"
    )

    pintar_strip()
    ui.separator()

    with ui.expansion("¿Cómo funciona?", icon="help_outline").classes("w-full text-sm"):
        with ui.column().classes("gap-1 text-sm"):
            ui.label(
                "1. Elegí el mes. 2. Elegí el PROVEEDOR (el % sale de su ficha) y arrastrá sus facturas. "
                "3. Tocá Procesar — se van a la cola y el campo se limpia para cargar otro proveedor. "
                "4. Todo se guarda solo; duplicadas y errores esperan tu decisión."
            )

    def _dialogo_nuevo_mes():
        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[420px]"):
            ui.label("Nuevo mes de registro").classes("text-lg font-bold")
            ui.label("Se crea al instante y queda listo para cargar facturas. Si ya existe, solo se selecciona.").classes(
                "text-xs opacity-50"
            )
            hoy = date.today()
            with ui.grid(columns=2).classes("w-full gap-3"):
                e_anio = ui.select({a: str(a) for a in range(hoy.year - 1, hoy.year + 2)}, value=hoy.year, label="Año")
                e_mes = ui.select({i + 1: nombre for i, nombre in enumerate(MESES_ES)}, value=hoy.month, label="Mes")
            vista = ui.label("").classes("font-semibold text-primary")

            def _vista():
                vista.set_text(f"Se seleccionará: {e_mes.value:02d} / {e_anio.value}")

            e_anio.on_value_change(lambda _: _vista())
            e_mes.on_value_change(lambda _: _vista())
            _vista()

            def _crear():
                nombre = f"{e_anio.value}_{int(e_mes.value):02d}_{MESES_ES[int(e_mes.value) - 1]}"
                if nombre not in opciones_mes:
                    opciones_mes.append(nombre)
                    opciones_mes.sort(reverse=True)
                    sel_mes.set_options(opciones_mes)
                    ui.notify(f"Mes {nombre} listo para usar.", type="positive")
                else:
                    ui.notify(f"{nombre} ya existía: lo seleccioné.", type="info")
                sel_mes.set_value(nombre)
                pintar_strip.refresh()
                dialogo.close()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancelar", on_click=dialogo.close).props("flat dense")
                ui.button("Crear y usar", icon="check", on_click=_crear).props("unelevated dense")
            dialogo.open()

    estado_archivos = {"archivos": []}

    def _pct_de(proveedor: str) -> float:
        ficha = fichas.get(proveedor)
        if not ficha:
            return 3.5
        try:
            pct = float(ficha.get("Comision_Pactada_Pct") or 0)
        except (TypeError, ValueError):
            pct = 0.0
        return pct if pct > 0 else 3.5

    def _quitar_archivo(nombre: str):
        estado_archivos["archivos"] = [(n, d) for n, d in estado_archivos["archivos"] if n != nombre]

    async def _recibir_archivo(e) -> None:
        archivo = getattr(e, "file", None) or e
        nombre = (getattr(archivo, "name", "") or "").strip() or "archivo"
        extens = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
        if extens not in EXTENSIONES:
            ui.notify(f"{nombre}: solo JPG, PNG o PDF", type="negative")
            return
        try:
            datos = await archivo.read()
        except Exception:
            ui.notify(f"{nombre}: no se pudo leer el archivo, reintentá la subida", type="negative")
            return
        if not datos:
            ui.notify(f"{nombre}: archivo vacío", type="negative")
            return
        if len(datos) > config.MAX_FILE_MB * 1024 * 1024:
            ui.notify(f"{nombre}: supera {config.MAX_FILE_MB} MB", type="negative")
            return
        if any(n == nombre for n, _ in estado_archivos["archivos"]):
            base, ext = nombre.rsplit(".", 1)
            nombre = f"{base}_2.{ext}"
        estado_archivos["archivos"].append((nombre, datos))
        pintar_pend()
        ui.notify(f"✅ {nombre} listo ({len(estado_archivos['archivos'])} en cola)", type="positive", timeout=1)

    def _factura_manual():
        registro = {c["clave"]: (0.0 if c["tipo"] == "numero" else "") for c in db.listar_campos()} | {
            "ID": "",
            "Venta_ID": "",
        }
        registro["Proveedor_Asignado"] = sel_prov.value or ""
        registro["Porcentaje_Compra"] = pct_input.value or 0.0
        dialogo_factura(
            registro,
            refrescar=lambda: (pintar_strip.refresh(), pintar_lotes.refresh()),
            es_nueva=True,
            mes_nueva=sel_mes.value,
        )

    def _procesar():
        archivos = estado_archivos["archivos"]
        if not archivos:
            ui.notify("Subí al menos una factura primero.", type="warning")
            return
        mes = (sel_mes.value or "").strip()
        if not re.match(r"^\d{4}_\d{2}_\S+$", mes):
            ui.notify(f"Mes inválido: '{mes}'. Formato: 2026_10_Octubre", type="negative")
            return
        proveedor = sel_prov.value
        if not proveedor:
            ui.notify("Elegí el proveedor.", type="warning")
            return
        if proveedor not in fichas:
            ui.notify(
                f"⚠ '{proveedor}' no tiene ficha en Configuración → Proveedores: revisá el % compra antes de procesar.",
                type="warning",
                timeout=6,
            )
        gasto = db.leer_gasto_ia()
        llamadas = sum(m["llamadas"] for m in gasto["por_mes"])
        promedio = (gasto["total"] / llamadas) if llamadas else 0.0007
        n = len(archivos)
        pct = pct_input.value or 0.0

        with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[480px]"):
            ui.label("¿Todo listo?").classes("text-lg font-bold")
            with ui.column().classes("w-full gap-1 text-sm"):
                ui.label(f"📄 Archivos: {n}")
                ui.label(f"🚚 Proveedor: {proveedor}")
                ui.label(f"📅 Mes: {_legible(mes)} ({mes})")
                ui.label(f"💸 % compra: {pct:g}%")
                ui.label(f"⚡ Costo estimado: ≈ ${promedio * n:.4f}")
            ui.label("Arrancan en segundo plano. Los OK se guardan y su venta se crea sola; duplicadas y errores esperan tu decisión.").classes(
                "text-xs opacity-60"
            )
            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Revisar de nuevo", on_click=dialogo.close).props("flat dense")
                ui.button(
                    f"Sí, procesar {n} ahora",
                    icon="rocket_launch",
                    on_click=lambda: (dialogo.close(), _ejecutar()),
                ).props("unelevated dense color=primary")
        dialogo.open()

        def _ejecutar():
            COLA.agregar_lote(mes, proveedor, list(archivos), pct)
            estado_archivos["archivos"] = []
            subidor.reset()
            pintar_pend()
            pintar_lotes.refresh()
            ui.notify(f"Lote de {proveedor} procesando. Elegí otro proveedor y repetí.", type="positive")

    with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
        with ui.row().classes("w-full items-center gap-3"):
            sel_prov = ui.select(
                opciones_prov,
                value=opciones_prov[0] if opciones_prov else None,
                label="Proveedor",
                on_change=lambda e: pct_input.set_value(_pct_de(e.value)),
            ).classes("w-56")
            pct_input = ui.number(
                "% compra (de su ficha, editable)",
                value=_pct_de(opciones_prov[0]) if opciones_prov else 3.5,
                format="%.2f",
                min=0.0,
                max=100.0,
            ).tooltip(
                "Sale de la ficha del proveedor. Podés ajustarlo aquí antes de procesar. "
                "Correcciones después de subir: Gestión del mes → proveedor → Aplicar y recalcular."
            ).classes("w-48")
            ui.space()
            ui.button(
                "🚀 Procesar",
                icon="rocket_launch",
                on_click=_procesar,
            ).props("unelevated dense no-caps color=primary").tooltip(
                "Procesa los archivos subidos con la IA"
            )

        cont_pend = ui.column().classes("w-full gap-2")

        def pintar_pend():
            cont_pend.clear()
            with cont_pend:
                archivos = estado_archivos["archivos"]
                if archivos:
                    with ui.row().classes("flex-wrap gap-2 items-center"):
                        ui.badge(f"{len(archivos)} en cola local", color="blue-2").props("text-color=black")
                        for nombre, _ in archivos:
                            with ui.row().classes("items-center q-px-sm q-py-xs rounded-borders bordered"):
                                ui.label(nombre).classes("text-xs")
                                ui.button(
                                    icon="close",
                                    on_click=lambda n=nombre: (_quitar_archivo(n), pintar_pend()),
                                ).props("flat dense round size=xs")
                else:
                    ui.label("Sin archivos. Elegí el proveedor y arrastrá sus facturas abajo ⬇").classes(
                        "text-xs opacity-50"
                    )

        subidor = ui.upload(
            multiple=True,
            auto_upload=True,
            on_upload=_recibir_archivo,
            on_rejected=lambda: ui.notify(
                "Archivo rechazado: tiene que ser JPG, PNG o PDF y pesar menos de 10 MB", type="negative"
            ),
        ).props(f"accept=.jpg,.jpeg,.png,.pdf, max-file-size={config.MAX_FILE_MB * 1024 * 1024}").classes(
            "w-full dropzone"
        )

    pintar_pend()

    # ---------- COLA GLOBAL ----------

    ui.separator()
    with ui.row().classes("w-full items-center gap-2"):
        ui.badge("4", color="primary").props("rounded")
        ui.label("Cola de procesamiento (todos los proveedores)").classes("font-semibold")
        ui.label("Los OK se guardan y su venta se crea sola; duplicadas y errores esperan tu decisión.").classes(
            "text-xs opacity-50"
        )

    contenedor_lotes = ui.column().classes("w-full gap-4")

    @ui.refreshable
    def pintar_lotes():
        contenedor_lotes.clear()
        lotes = COLA.resumen_lotes()
        with contenedor_lotes:
            if not lotes:
                ui.label("Sin lotes en curso.").classes("opacity-50")
            for lote in lotes:
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center gap-3"):
                        ui.icon("folder_zip")
                        ui.label(
                            f"Lote {lote['id']} · {lote['proveedor']} al {(lote['pct_compra'] or 0):g}% · {lote['mes']}"
                        ).classes("font-semibold")
                        ui.space()
                        ui.label(f"{lote['hechos']}/{lote['total']}").classes("opacity-70")
                        if not lote["activo"]:
                            ui.button(
                                icon="delete_sweep",
                                on_click=lambda: (COLA.limpiar_completados(), pintar_lotes.refresh()),
                            ).props("flat dense round").tooltip("Limpiar lotes terminados")
                    ui.linear_progress(value=lote["progreso"], show_value=False).classes("w-full")
                    chips_estado(lote["ok"], lote["duplicados"], lote["errores"])
                    suma_ok = sum((a["monto_total"] or 0) for a in lote["archivos"] if a["estado"] == "OK")
                    if suma_ok:
                        ui.label(f"Σ montos guardados: Bs {suma_ok:,.2f}").classes("text-xs opacity-60")
                    for v in lote.get("ventas", []):
                        with ui.row().classes("items-center gap-2 q-px-sm"):
                            ui.icon("sell", color="green", size="xs")
                            ui.label(
                                f"Venta creada a {v['cliente']} por Bs {v['precio']:,.2f} (al % de su ficha — editable en Ventas)"
                            ).classes("text-xs text-green-700 dark:text-green-400")
                    ui.table(
                        columns=COLUMNAS_ARCHIVO,
                        rows=[{**a, "monto_total": f"{(a['monto_total'] or 0):,.2f}"} for a in lote["archivos"]],
                        row_key="nombre",
                        pagination=0,
                    ).classes("w-full").props("flat dense")
                    acciones = []
                    for i, a in enumerate(lote["archivos"]):
                        if a["estado"] == "DUPLICADO":
                            acciones.append((i, a["nombre"], "Adjuntar PDF a la existente", "orange", "attach_file"))
                            acciones.append((i, a["nombre"], "Guardar como NUEVA factura", "green", "add_task"))
                        elif a["estado"] == "ERROR":
                            acciones.append((i, a["nombre"], "Reintentar", "blue", "replay"))
                    if acciones:
                        with ui.row().classes("flex-wrap gap-2 items-center"):
                            ui.label("Decide:").classes("text-sm opacity-60")
                            for i, nombre, texto, color, icono in acciones:
                                ui.button(
                                    f"{texto}: {nombre}",
                                    icon=icono,
                                    on_click=lambda i=i, t=texto: (
                                        cola_accion(lote["id"], i, t),
                                        pintar_lotes.refresh(),
                                    ),
                                ).props(f"unelevated no-caps color={color} dense")
                            if any(a["estado"] == "DUPLICADO" for a in lote["archivos"]):
                                ui.label(
                                    "Duplicado = ya existe una factura guardada con ese NIT emisor + N° "
                                    "(probablemente de una subida anterior). Nada se guarda hasta que elijas: "
                                    "'Adjuntar PDF' suma el archivo a la factura ya existente; si la descartás, no se registra."
                                ).classes("text-xs opacity-60")

    def cola_accion(lote_id: str, indice: int, tipo: str) -> None:
        if tipo == "Adjuntar PDF a la existente":
            ok = COLA.guardar_duplicado(lote_id, indice)
            ui.notify(
                "PDF adjuntado a la factura existente ✔" if ok else "No se pudo adjuntar (el registro ya no está disponible).",
                type="positive" if ok else "warning",
            )
        elif tipo == "Guardar como NUEVA factura":
            ok = COLA.guardar_como_nueva(lote_id, indice)
            ui.notify(
                "Factura guardada como NUEVA ✔ (con su venta al cliente)" if ok else "No se pudo guardar (el registro ya no está disponible).",
                type="positive" if ok else "warning",
            )
        elif tipo == "Reintentar":
            COLA.reintentar_archivo(lote_id, indice)
        else:
            COLA.descartar_archivo(lote_id, indice)

    pintar_lotes()
    snapshot = {"hash": ""}

    def _tick():
        try:
            import json

            actual = json.dumps(COLA.resumen_lotes(), sort_keys=True, default=str)
        except Exception:
            return
        if actual != snapshot["hash"]:
            snapshot["hash"] = actual
            pintar_lotes.refresh()

    ui.timer(1.5, _tick)
    ui.label("¿Ya guardaste todo? → Gestión del mes para ver compras/ventas · Ventas y cobros para cobrar y pagar").classes(
        "text-sm opacity-50"
    )
