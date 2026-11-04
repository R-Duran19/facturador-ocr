import io
import re

import pandas as pd

import db
import reportes
from config import CARPETA_EXPORTS


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
        titulo = f"resumen de costos y ganancia - {mes}"
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
        hoja2.append([f"ventas resumen - {mes}"])
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
    datos = buffer.getvalue()
    try:
        from pathlib import Path

        carpeta = Path(CARPETA_EXPORTS)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(datos)
    except OSError:
        pass
    return datos, nombre
