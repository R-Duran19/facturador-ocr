import io
import re

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import db
import reportes
from config import CARPETA_EXPORTS

_CLAVES_MONTO = ("monto", "total", "cobrar", "saldo", "cobrado", "compra", "venta", "utilidad", "credito", "precio")


def _estilar_hoja(ws, fila_header: int = 1, titulo: str = "") -> None:
    """Formato prolijo: encabezado verde, bordes, zebra, formatos de moneda y anchos."""
    verde = PatternFill("solid", fgColor="175E3B")
    zebra = PatternFill("solid", fgColor="F3F9F5")
    gris = PatternFill("solid", fgColor="EDEDED")
    lado = Side(style="thin", color="C9D8CD")
    borde = Border(left=lado, right=lado, top=lado, bottom=lado)

    max_col = ws.max_column
    max_row = ws.max_row

    if titulo and fila_header >= 2:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
        celda = ws.cell(row=1, column=1)
        celda.font = Font(bold=True, size=13, color="175E3B")
        celda.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 24

    for j in range(1, max_col + 1):
        celda = ws.cell(row=fila_header, column=j)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = verde
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = borde
    ws.row_dimensions[fila_header].height = 22

    encabezados = {
        j: str(ws.cell(row=fila_header, column=j).value or "").strip().lower() for j in range(1, max_col + 1)
    }
    for i in range(fila_header + 1, max_row + 1):
        es_total = "total" in str(ws.cell(row=i, column=1).value or "").strip().lower()
        banda = (i - fila_header) % 2 == 0
        for j in range(1, max_col + 1):
            celda = ws.cell(row=i, column=j)
            celda.border = borde
            celda.alignment = Alignment(vertical="center", wrap_text=False)
            if es_total:
                celda.font = Font(bold=True)
                celda.fill = gris
            elif banda:
                celda.fill = zebra
            es_pct = encabezados[j].startswith("%")
            if es_pct:
                celda.number_format = "0.0#"
            elif any(clave in encabezados[j] for clave in _CLAVES_MONTO) and isinstance(celda.value, (int, float)):
                celda.number_format = "#,##0.00"

    for j in range(1, max_col + 1):
        largo = max(
            (
                len(str(celda.value))
                for i in range(fila_header, max_row + 1)
                for celda in [ws.cell(row=i, column=j)]
                if celda.value is not None
            ),
            default=8,
        )
        ws.column_dimensions[get_column_letter(j)].width = min(max(largo + 3, 10), 52)

    ws.freeze_panes = ws.cell(row=fila_header + 1, column=2)


def _titulo_hoja(texto: str) -> str:
    limpio = re.sub(r"[\[\]:*?/\\]", "-", str(texto)).strip() or "SIN PROVEEDOR"
    return limpio[:31]


def exportar_mes_excel(mes: str) -> tuple[bytes, str]:
    facturas = db.leer_facturas_mes(mes)
    ventas = db.leer_ventas_mes(mes)
    claves = [c["clave"] for c in db.listar_campos(solo_activos=True) if c["clave"] != "ID"]

    df_todas = pd.DataFrame(facturas)
    for col in claves:
        if col not in df_todas.columns:
            df_todas[col] = ""

    buffer = io.BytesIO()
    nombre = f"{mes}.xlsx"
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if facturas:
            resumen = (
                df_todas.groupby("Proveedor_Asignado")
                .agg(**{
                    "Facturas": ("ID", "count"),
                    "Total": ("Monto_Total", "sum"),
                    "Credito_Fiscal": ("Credito_Fiscal", "sum"),
                })
                .reset_index()
            )
            resumen.loc[len(resumen)] = ["TOTAL", len(facturas), df_todas["Monto_Total"].sum(), df_todas["Credito_Fiscal"].sum()]
            resumen.to_excel(writer, sheet_name="RESUMEN", index=False)

            hojas_usadas = {"RESUMEN", "VENTAS"}
            for proveedor, grupo in df_todas.groupby("Proveedor_Asignado"):
                titulo = _titulo_hoja(proveedor)
                base, n = titulo, 2
                while titulo in hojas_usadas:
                    titulo = f"{base[:28]}_{n}"
                    n += 1
                hojas_usadas.add(titulo)
                grupo[claves].to_excel(writer, sheet_name=titulo, index=False)

        if ventas:
            pd.DataFrame(ventas)[
                ["Cliente_Razon_Social", "Monto_Credito_Vendido", "Precio_Cobrado", "Estado_Cobro", "Facturas_IDs", "Notas"]
            ].to_excel(writer, sheet_name="VENTAS", index=False)

        for ws in writer.sheets.values():
            _estilar_hoja(ws, fila_header=1)

    datos = buffer.getvalue()

    try:
        carpeta = __import__("pathlib").Path(CARPETA_EXPORTS)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(datos)
    except OSError:
        pass
    return datos, nombre


def exportar_reportes_mes(mes: str, incluir_todos: bool = False) -> tuple[bytes, str]:
    """Réplica de los dos Excel de control del cliente, en un solo libro."""
    filas_costos = reportes.resumen_costos_ganancia(mes)
    filas_ventas = reportes.resumen_ventas_cliente(mes, incluir_todos=incluir_todos)

    buffer = io.BytesIO()
    nombre = f"control {mes}.xlsx"
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        titulo = f"RESUMEN DE COSTOS Y GANANCIA - {mes.upper()}"
        hoja = writer.book.create_sheet(title="COSTOS Y GANANCIA")
        hoja.append([titulo])
        hoja.append(
            ["proveedor", "nombre (cliente)", "total facturado", "%", "compra", "%", "venta", "utilidad", "observaciones"]
        )
        for f in filas_costos:
            hoja.append(
                [
                    f["Proveedor"],
                    f["Cliente"],
                    f["Total_Facturado"],
                    f["Pct_Compra"],
                    f["Compra"],
                    f["Pct_Venta"],
                    f["Venta"],
                    f["Utilidad"],
                    "",
                ]
            )
        tot_fac = sum(f["Total_Facturado"] for f in filas_costos)
        tot_compra = sum(f["Compra"] for f in filas_costos)
        tot_venta = sum(f["Venta"] for f in filas_costos)
        tot_util = sum(f["Utilidad"] for f in filas_costos)
        hoja.append(["TOTALES", "", tot_fac, "", tot_compra, "", tot_venta, tot_util, ""])

        hoja2 = writer.book.create_sheet(title="VENTAS")
        hoja2.append([f"VENTAS RESUMEN - {mes.upper()}"])
        hoja2.append(
            ["#", "nombre", "rubro", "monto", "cobrar", "%", "prov.", "entregado", "cobrado", "saldo", "estado"]
        )
        for f in filas_ventas:
            hoja2.append(
                [
                    f["Nro"],
                    f["Cliente"],
                    f["Rubro"],
                    f["Monto"],
                    f["Cobrar"],
                    f["Pct"],
                    f["Proveedor"],
                    f["Entregado"],
                    f["Cobrado"],
                    f["Saldo"],
                    f["Estado"],
                ]
            )
        hoja2.append(
            [
                "total",
                "",
                "",
                sum(f["Monto"] for f in filas_ventas),
                sum(f["Cobrar"] for f in filas_ventas),
                "",
                "",
                "",
                sum(f["Cobrado"] for f in filas_ventas),
                sum(f["Saldo"] for f in filas_ventas),
                "",
            ]
        )

        _estilar_hoja(hoja, fila_header=2, titulo=f"resumen de costos y ganancia - {mes}")
        _estilar_hoja(hoja2, fila_header=2, titulo=f"ventas resumen - {mes}")

    datos = buffer.getvalue()
    try:
        from pathlib import Path

        carpeta = Path(CARPETA_EXPORTS)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(datos)
    except OSError:
        pass
    return datos, nombre
