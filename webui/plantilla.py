"""Plantilla común: sesión, encabezado, menú lateral y guard de login."""

import time
from contextlib import contextmanager
from typing import Callable

from nicegui import app, ui

import config
import db
from webui import nav

__all__ = ["pagina", "TITULOS"]

_MENU_OPERACION = [
    ("/", "Cargar facturas", "cloud_upload"),
    ("/gestion", "Gestión del mes", "folder_open"),
    ("/ventas", "Ventas y cobros", "sell"),
    ("/facturas", "Buscar facturas", "search"),
]
_MENU_CONFIG = [
    ("/configuracion", "Configuración", "settings"),
]

TITULOS = {
    **{ruta: nombre for ruta, nombre, _ in _MENU_OPERACION + _MENU_CONFIG},
    "/pagos": "Pagos a proveedores",
    "/reportes": "Reportes del mes",
}


def _autenticado() -> bool:
    if not config.APP_PASSWORD:
        return True
    ts = app.storage.user.get("login_ts", 0)
    return ts > 0 and (time.time() - ts) < config.SESION_HORAS * 3600


def _bloqueado() -> int:
    hasta = app.storage.client.get("bloqueo_hasta", 0)
    return max(0, int(hasta - time.time()))


def _registrar_fallo() -> None:
    fallos = app.storage.client.get("fallos", 0) + 1
    app.storage.client["fallos"] = fallos
    if fallos >= config.MAX_INTENTOS_LOGIN:
        app.storage.client["bloqueo_hasta"] = time.time() + 15 * 60
        app.storage.client["fallos"] = 0


def _render_login() -> bool:
    ui.add_head_html("<style>.login-card{max-width:380px;margin:14vh auto 0;}</style>")
    restante = _bloqueado()
    with ui.card().classes("login-card w-full"):
        with ui.column().classes("w-full gap-3 items-center"):
            ui.icon("lock", size="3rem", color="primary")
            ui.label("Facturador OCR").classes("text-xl font-bold")
            if restante:
                ui.label(f"Demasiados intentos. Esperá {restante // 60 + 1} min.").classes("text-negative")
                return False
            clave = ui.input("Contraseña", password=True, password_toggle_button=True).classes("w-full")
            aviso = ui.label("").classes("text-negative text-sm")

            def intentar() -> None:
                if config.APP_PASSWORD and clave.value and _comparar(clave.value, config.APP_PASSWORD):
                    app.storage.user["login_ts"] = time.time()
                    app.storage.client["fallos"] = 0
                    ui.navigate.to("/")
                    return
                _registrar_fallo()
                aviso.set_text("Contraseña incorrecta.")
                clave.set_value(None)

            clave.on("keydown.enter", intentar)
            ui.button("Entrar", on_click=intentar).classes("w-full")
    return False


def _comparar(a: str, b: str) -> bool:
    import secrets

    return secrets.compare_digest(a.encode(), b.encode())


def _cerrar_sesion() -> None:
    app.storage.user["login_ts"] = 0
    ui.navigate.to("/")


def _clientes_pendientes() -> int:
    """Cantidad de clientes con % Venta o WhatsApp contacto sin completar."""
    try:
        n = 0
        for c in db.leer_clientes():
            try:
                pct = float(c.get("Pct_Venta") or 0)
            except (TypeError, ValueError):
                pct = 0.0
            if pct <= 0 or not str(c.get("Contacto", "")).strip():
                n += 1
        return n
    except Exception:
        return 0


def _ir_clientes(aviso) -> None:
    app.storage.user["ir_clientes"] = True
    aviso.close()
    ui.navigate.to("/configuracion")


def _item_menu(ruta: str, nombre: str, icono: str, activa: bool, pendientes: int = 0) -> None:
    props = "unelevated no-caps align=left color=primary text-color=white" if activa else "flat align=left no-caps"
    boton = ui.button(nombre, icon=icono, on_click=lambda r=ruta: ui.navigate.to(r)).props(props).classes("w-full")
    if pendientes:
        with boton:
            ui.badge(str(pendientes)).props("color=red-8 text-color=white rounded-borders").classes(
                "q-ml-auto"
            ).tooltip(f"{pendientes} cliente(s) con datos pendientes")


def _chrome(titulo: str, ruta: str) -> None:
    ui.colors(primary="#175E3B")
    ui.add_head_html(
        "<style>.text-h5{font-weight:700 !important;} "
        ".q-card{border-radius:12px;} .nicegui-content{max-width:1400px;}</style>"
    )
    ui.keyboard.on_key("Alt+ArrowLeft", lambda _: nav.atras())
    oscuro = ui.dark_mode()
    with ui.header().classes("items-center"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=white")
        ui.icon("receipt_long").classes("text-white text-2xl")
        ui.label("Facturador").classes("text-white text-lg font-bold")
        ui.space()
        ui.label(titulo).classes("text-white/60 text-sm")
        ui.button(icon="arrow_back", on_click=lambda: nav.atras()).props("flat round color=white").tooltip(
            "Volver atrás (Alt + ←)"
        )
        ui.button(icon="dark_mode", on_click=oscuro.toggle).props("flat round color=white")
        if config.APP_PASSWORD:
            ui.button(icon="logout", on_click=_cerrar_sesion).props("flat round color=white")
    with ui.left_drawer(bordered=True, elevated=False) as drawer:
        with ui.column().classes("gap-1 w-full q-pt-sm"):
            ui.label("Operación").classes("text-xs opacity-50 q-px-md")
            for r, nombre, icono in _MENU_OPERACION:
                _item_menu(r, nombre, icono, r == ruta)
            ui.separator().classes("q-my-sm")
            ui.label("Ajustes").classes("text-xs opacity-50 q-px-md")
            pendientes_cli = _clientes_pendientes()
            for r, nombre, icono in _MENU_CONFIG:
                _item_menu(r, nombre, icono, r == ruta, pendientes_cli)

    aviso_hoy = time.strftime("%Y-%m-%d")
    if pendientes_cli and app.storage.user.get("aviso_clientes_dia") != aviso_hoy:
        app.storage.user["aviso_clientes_dia"] = aviso_hoy
        with ui.dialog() as aviso, ui.card().classes("w-full max-w-[440px]"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("notifications_active", color="red-8").classes("text-3xl")
                ui.label("Clientes por completar").classes("text-lg font-bold")
            ui.label(
                f"Tenés {pendientes_cli} cliente(s) con datos pendientes (% Venta o WhatsApp contacto). "
                "Completalos para que los reportes y WhatsApp salgan bien."
            ).classes("text-sm")
            ui.label("(Este aviso se cierra solo en unos segundos, o tocá fuera / Después)").classes(
                "text-xs opacity-50"
            )
            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Después", on_click=aviso.close).props("flat dense")
                ui.button(
                    "Ir a clientes",
                    icon="badge",
                    on_click=lambda: _ir_clientes(aviso),
                ).props("unelevated dense color=primary")
        aviso.open()
        ui.run_javascript(
            "setTimeout(() => { const b = [...document.querySelectorAll('.q-dialog .q-btn')]"
            ".find(x => x.textContent.includes('Después')); if (b) b.click(); }, 7000);"
        )
    with ui.column().classes("w-full q-pa-md gap-4"):
        yield


@contextmanager
def _chrome_ctx(titulo: str, ruta: str):
    generador = _chrome(titulo, ruta)
    next(generador)
    try:
        yield
    finally:
        generador.close()


def pagina(ruta: str) -> Callable:
    """Decorador: registra la página con guard de sesión y plantilla común.
    El título se toma de TITULOS[ruta]."""

    def decorador(builder: Callable) -> Callable:
        @ui.page(ruta)
        def vista():
            if not _autenticado():
                _render_login()
                return
            nav.registrar(ruta)
            with _chrome_ctx(TITULOS.get(ruta, ""), ruta):
                builder()

        return builder

    return decorador
