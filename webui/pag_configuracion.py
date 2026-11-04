"""Configuración general: proveedores, clientes, campos y sistema en un solo lugar."""

from nicegui import ui

from webui.pag_ajustes import seccion_sistema
from webui.pag_campos import seccion_campos
from webui.pag_maestros import seccion_clientes, seccion_proveedores
from webui.plantilla import pagina

__all__ = ["pagina_configuracion"]


@pagina("/configuracion")
def pagina_configuracion():
    with ui.tabs().classes("w-full").props("dense inline-breakpoint=0") as tabs:
        tab_prov = ui.tab("Proveedores", icon="local_shipping")
        tab_cli = ui.tab("Clientes", icon="badge")
        tab_campos = ui.tab("Campos", icon="tune")
        tab_sistema = ui.tab("Sistema", icon="settings")
    with ui.tab_panels(tabs, value=tab_prov).classes("w-full"):
        with ui.tab_panel(tab_prov).classes("p-0"):
            seccion_proveedores()
        with ui.tab_panel(tab_cli).classes("p-0"):
            seccion_clientes()
        with ui.tab_panel(tab_campos).classes("p-0"):
            seccion_campos()
        with ui.tab_panel(tab_sistema).classes("p-0"):
            seccion_sistema()
