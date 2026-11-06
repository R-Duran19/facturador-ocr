"""Ajustes: información del sistema, backups, caché OCR."""

from nicegui import ui

import check_setup
import config
import db
import mover_mes
import paquete_datos
import reset_datos
import respaldos
from webui.componentes import confirmar

def seccion_sistema():
    with ui.card().classes("w-full"):
        ui.label("⚡ Gastos de IA (consumo real de Gemini)").classes("font-semibold")
        with ui.row().classes("w-full items-center gap-2"):
            if config.BILLING_ACTIVO:
                ui.badge("CON BILLING: el monto de abajo se cobra real en tu tarjeta", color="orange").props("text-color=white")
            else:
                ui.badge("SIN BILLING: gratis (free tier) — no se cobra nada", color="grey-7").props("text-color=white")
        ui.label(
            "Sin billing: los tokens se consumen igual y este contador muestra cuánto valdrían, pero Google no cobra —"
            " el límite es de velocidad y volumen diario (free tier). "
            "Con billing: se levantan los límites y ese mismo monto se factura en tu cuenta. "
            "Para activarlo: billing en Google AI Studio + BILLING_ACTIVO=1 en .env."
        ).classes("text-xs opacity-60")
        gasto = db.leer_gasto_ia()
        with ui.row().classes("w-full flex-wrap gap-x-8 gap-y-1 q-px-sm"):
            for etiqueta, valor in [("Hoy", gasto["hoy"]), ("Este mes", gasto["mes"]), ("Histórico", gasto["total"])]:
                with ui.column().classes("gap-0 min-w-[110px]"):
                    ui.label(f"${valor:,.4f}").classes("text-base font-bold")
                    ui.label(etiqueta).classes("text-[11px] opacity-50")
        ui.label(
            f"Precios configurados: ${config.PRECIO_IA_ENTRADA}/1M tokens entrada · ${config.PRECIO_IA_SALIDA}/1M salida "
            "(.env: PRECIO_IA_ENTRADA / PRECIO_IA_SALIDA). Los reintentos y caché afectan el total real."
        ).classes("text-xs opacity-50")
        if gasto["por_mes"]:
            ui.table(
                columns=[
                    {"name": "mes", "label": "Mes", "field": "mes", "align": "left"},
                    {"name": "llamadas", "label": "Llamadas", "field": "llamadas", "align": "right"},
                    {"name": "tin", "label": "Tokens in", "field": "tin", "align": "right"},
                    {"name": "tout", "label": "Tokens out", "field": "tout", "align": "right"},
                    {"name": "costo", "label": "Costo USD", "field": "costo", "align": "right"},
                ],
                rows=[
                    {
                        "mes": m["mes"],
                        "llamadas": m["llamadas"],
                        "tin": f"{m['tokens_in']:,}",
                        "tout": f"{m['tokens_out']:,}",
                        "costo": f"${m['costo']:.4f}",
                    }
                    for m in gasto["por_mes"]
                ],
                row_key="mes",
                pagination=0,
            ).props("flat dense bordered")
        else:
            ui.label("Aún no hay llamadas registradas.").classes("text-sm opacity-50")

    with ui.card().classes("w-full"):
        ui.label("Sistema").classes("font-semibold")
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("🩺 Salud del sistema: revisa Python, dependencias, .env, Gemini (prueba real), base y carpetas.").classes(
                "text-sm opacity-70"
            )
            ui.space()

            async def _salud():
                from nicegui import run

                resultados = await run.io_bound(check_setup.verificar_salud)
                with ui.dialog() as dialogo, ui.card().classes("w-full max-w-[720px]"):
                    ui.label("🩺 Salud del sistema").classes("text-lg font-bold")
                    for r in resultados:
                        color = {"OK": "green", "FALLA": "red", "AVISO": "orange"}[r["estado"]]
                        with ui.row().classes("w-full items-start gap-2"):
                            ui.badge(r["estado"], color=color).props("text-color=white")
                            with ui.column().classes("gap-0"):
                                ui.label(r["chequeo"]).classes("font-semibold text-sm")
                                ui.label(r["detalle"]).classes("text-xs opacity-70")
                    with ui.row().classes("w-full justify-end q-mt-sm"):
                        ui.button("Cerrar", on_click=dialogo.close).props("flat dense")
                dialogo.open()

            ui.button("🩺 Salud del sistema", icon="health_and_safety", on_click=_salud).props("unelevated dense no-caps")
        conn = db.conexion()
        conteo = {
            k: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for k, t in [
                ("facturas", "facturas"),
                ("ventas", "ventas"),
                ("proveedores", "proveedores"),
                ("clientes", "clientes"),
                ("campos", "campos_config"),
                ("caché OCR", "extraction_cache"),
            ]
        }
        conn.close()
        with ui.row().classes("flex-wrap gap-4"):
            for k, v in conteo.items():
                ui.label(f"{k}: ").classes("opacity-60")
                ui.label(str(v)).classes("font-semibold")
        ui.label(f"Modelo IA: {config.MODEL_NAME} · Fallbacks: {', '.join(config.FALLBACK_MODELS)}").classes("text-sm opacity-60")
        ui.label(
            f"Login: {'activado (password por .env)' if config.APP_PASSWORD else 'desactivado (APP_PASSWORD vacío)'}"
        ).classes("text-sm opacity-60")

    with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
        ui.label("📦 Paquete de datos (para pasar todo a otra computadora)").classes("font-semibold")
        ui.label(
            "Exporta el catálogo (clientes, proveedores, campos), las deudas manuales y los meses elegidos "
            "CON sus PDFs en un .zip. En la otra computadora: clonar + instalar, y acá mismo importar ese .zip. "
            "La importación crea un backup antes y no borra nada: solo agrega o actualiza."
        ).classes("text-xs opacity-60")
        opciones_mes = ["TODOS"] + db.listar_meses()
        sel_paquete = ui.select(opciones_mes, value="TODOS", label="Qué exportar").classes("w-64")

        def _exportar_paquete():
            elegidos = None if sel_paquete.value == "TODOS" else [sel_paquete.value]
            datos, nombre = paquete_datos.exportar(elegidos)
            ui.download(datos, filename=nombre)
            ui.notify(f"Paquete {nombre} generado ({len(datos) / 1e6:.1f} MB).", type="positive")

        async def _importar_paquete(e):
            try:
                archivo = getattr(e, "file", None) or e
                contenido = await archivo.read()
                resumen = paquete_datos.importar(contenido)
                ui.notify(
                    "Importado ✔ · " + ", ".join(f"{k}: {v}" for k, v in resumen.items()),
                    type="positive",
                    timeout=8,
                )
            except Exception as ex:
                ui.notify(f"No se pudo importar: {ex}", type="negative")

        ui.button("Generar paquete .zip", icon="download", on_click=_exportar_paquete).props("unelevated")
        ui.separator()
        ui.label("Importar un paquete .zip en esta instalación:").classes("text-sm")
        ui.upload(
            on_upload=_importar_paquete,
            auto_upload=True,
        ).props("accept=.zip").classes("w-full")

    with ui.card().classes("w-full border-2").style("border-color: var(--q-primary);"):
        ui.label("♻ Renombrar un mes (lo cargué con el nombre equivocado)").classes("font-semibold")
        ui.label(
            "Mueve TODAS las facturas, ventas, pagos y PDFs del mes elegido al nombre nuevo. "
            "Los IDs y enlaces no cambian: es un cambio de nombre, no se pierde ni se duplica nada."
        ).classes("text-xs opacity-60")

        meses_rn = db.listar_meses()
        with ui.row().classes("w-full items-end gap-3 flex-wrap"):
            sel_ren_origen = ui.select(
                meses_rn, value=meses_rn[0] if meses_rn else None,
                label="Mes actual (el que está mal)",
            ).classes("w-72")
            e_ren_destino = ui.input(
                "Nombre nuevo (formato: 2026_10_Octubre)",
                value=None,
            ).classes("w-72").tooltip("Formato: año_mes_Nombre — ej: 2026_10_Octubre")
            ui.button(
                "Renombrar mes",
                icon="drive_file_rename_outline",
                on_click=lambda: _renombrar_mes(),
            ).props("unelevated dense no-caps color=primary")

        def _renombrar_mes():
            import re

            origen, destino = sel_ren_origen.value, (e_ren_destino.value or "").strip()
            if not origen:
                ui.notify("No hay meses para renombrar.", type="info")
                return
            if not re.match(r"^\d{4}_\d{2}_\S+$", destino):
                ui.notify("El nombre nuevo tiene que respetar el formato: 2026_10_Octubre", type="warning")
                return
            if origen == destino:
                ui.notify("El nombre nuevo es igual al actual.", type="warning")
                return

            def accion():
                resumen = mover_mes.mover(origen, destino)
                ui.notify(
                    f"Renombrado {origen} → {destino}: {resumen.get('facturas', 0)} facturas, "
                    f"{resumen.get('pdfs_movidos', 0)} PDFs movidos.",
                    type="positive",
                    timeout=6,
                )
                ui.navigate.to("/configuracion")

            confirmar(f"¿Renombrar {origen} → {destino}? (backup automático antes)", accion, "Renombrar")

    with ui.card().classes("w-full border-2").style("border-color: #B91C1C;"):
        ui.label("🧨 Reset de datos (borrar mes o empezar de cero)").classes("font-semibold")
        ui.label(
            "Siempre se crea un backup automático en backups/ antes de borrar. "
            "Después de borrar se recarga la página sola para actualizar los selectores de mes."
        ).classes("text-xs opacity-60")

        meses = db.listar_meses()

        def _borrar_mes():
            mes = sel_mes_borrar.value
            if not mes:
                ui.notify("No hay meses para borrar.", type="info")
                return

            def accion():
                resumen = reset_datos.borrar_meses([mes], borrar_pdfs=chk_pdfs_mes.value)
                info = resumen.get(mes, {})
                ui.notify(
                    f"Mes {mes} borrado: {info.get('facturas', 0)} facturas, {info.get('ventas', 0)} ventas. Backup creado antes.",
                    type="positive",
                    timeout=6,
                )
                ui.navigate.to("/configuracion")

            confirmar(f"¿Borrar TODO el mes {mes}? (backup automático antes)", accion, "Borrar mes")

        def _borrar_todo():
            conservar = chk_catalogo.value
            detalle = "conservando clientes y proveedores" if conservar else "incluyendo CLIENTES y PROVEEDORES"

            def accion():
                reset_datos.borrar_todo(conservar_catalogo=conservar, borrar_pdfs=chk_pdfs_todo.value)
                ui.notify(f"Sistema reseteado ({detalle}). Backup creado antes.", type="positive", timeout=6)
                ui.navigate.to("/configuracion")

            confirmar(
                f"¿Borrar TODO el historial de facturas/ventas/cobros/pagos/deudas ({detalle})? (backup automático antes)",
                accion,
                "Sí, borrar todo",
            )

        with ui.row().classes("w-full items-end gap-3 flex-wrap q-mt-sm"):
            sel_mes_borrar = ui.select(
                meses, value=meses[0] if meses else None,
                label="Mes a borrar",
            ).classes("w-64")
            chk_pdfs_mes = ui.checkbox("también borrar sus PDFs")
            ui.button(
                "Borrar ese mes",
                icon="delete_sweep",
                color="orange",
                on_click=_borrar_mes,
            ).props("unelevated dense no-caps")

        ui.separator().classes("q-my-sm")
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            chk_catalogo = ui.checkbox(
                "conservar clientes y proveedores", value=True,
            ).tooltip("Desmarcalo solo si querés arrancar absolutamente de cero")
            chk_pdfs_todo = ui.checkbox("también borrar todos los PDFs")
            ui.button(
                "Borrar TODO (facturas, ventas, cobros, pagos, deudas)",
                icon="dangerous",
                color="negative",
                on_click=_borrar_todo,
            ).props("unelevated dense no-caps")

    with ui.card().classes("w-full"):
        ui.label("Respaldos de la base de datos").classes("font-semibold")
        ui.label(
            f"Carpeta: {config.CARPETA_RESPALDOS}/ · Retención: {config.RETENCION_RESPALDOS} copias · "
            "Backup automático al iniciar y cada 24 h."
        ).classes("text-sm opacity-60")

        cont_backups = ui.column().classes("w-full gap-2")

        def pintar_backups():
            cont_backups.clear()
            with cont_backups:
                backups = respaldos.listar_backups()
                if backups:
                    ui.table(
                        columns=[
                            {"name": "archivo", "label": "Archivo", "field": "archivo", "align": "left"},
                            {"name": "kb", "label": "Tamaño (KB)", "field": "tamano_kb", "align": "right"},
                        ],
                        rows=[{**b, "kb": f"{b['tamano_kb']:,.1f}"} for b in backups],
                        row_key="archivo",
                        pagination=0,
                    ).props("flat dense")
                else:
                    ui.label("Sin respaldos aún.").classes("opacity-50 text-sm")

        def hacer_backup():
            p = respaldos.crear_backup("manual")
            ui.notify(f"Backup creado: {p.name}", type="positive")
            pintar_backups()

        ui.button("Crear backup ahora", icon="backup", on_click=hacer_backup).props("unelevated")
        pintar_backups()

    with ui.card().classes("w-full"):
        ui.label("Datos iniciales del negocio").classes("font-semibold")
        ui.label(
            "Siembra los proveedores-persona (Anahi, Gladys, Carmen, Gary, Javi, Jhimmy, Dio) "
            "y los clientes activos con su rubro y % de venta. No duplica los que ya existen."
        ).classes("text-sm opacity-60")

        def sembrar():
            import seeds

            r = seeds.sembrar()
            ui.notify(
                f"Seeders OK: {r['proveedores_nuevos']} proveedor(es) y {r['clientes_nuevos']} cliente(s) nuevos.",
                type="positive",
            )

        ui.button("Sembrar datos iniciales", icon="spa", on_click=sembrar).props("unelevated")

    with ui.card().classes("w-full"):
        ui.label("Caché de OCR").classes("font-semibold")
        ui.label(
            "Cada archivo procesado guarda su resultado por hash: volver a subir el mismo PDF es instantáneo y gratis. "
            "Se limpia sola (últimos 20.000)."
        ).classes("text-sm opacity-60")

        def limpiar():
            n = db.limpiar_cache(0)
            ui.notify(f"Caché vaciada ({n} entradas).", type="positive")

        ui.button("Vaciar caché", icon="cleaning_services", on_click=limpiar).props("flat color=negative")


__all__ = ["seccion_sistema"]
