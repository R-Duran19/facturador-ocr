"""Ajustes: información del sistema, backups, caché OCR."""

from nicegui import ui

import check_setup
import config
import db
import paquete_datos
import respaldos

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
