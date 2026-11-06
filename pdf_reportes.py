"""Reportes en PDF: ventas completas por empresa y resumen mensual."""

import io
import zipfile
from datetime import date

from fpdf import FPDF
from fpdf.fonts import FontFace

import db
import reportes

__all__ = ["pdf_empresa", "pdf_resumen_mes", "pdfs_por_empresa_zip"]

_VERDE_TITULO = (216, 232, 222)
_VERDE_TITULO_TEXTO = (27, 67, 50)
_VERDE_SECCION = (58, 110, 82)
_HEADER_FILL = (255, 242, 204)
_HEADER_TEXT = (120, 84, 6)
_ZEBRA = (250, 252, 250)


def _pdf_base(titulo: str) -> FPDF:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(*_VERDE_TITULO)
    pdf.set_text_color(*_VERDE_TITULO_TEXTO)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, titulo, new_x="LMARGIN", new_y="NEXT", align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 8)
    pdf.ln(2)
    return pdf


def _titulo_seccion(pdf: FPDF, texto: str) -> None:
    pdf.ln(1)
    pdf.set_fill_color(*_VERDE_SECCION)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 9, texto, new_x="LMARGIN", new_y="NEXT", align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 8)
    pdf.ln(1)


def _tabla_datos(pdf: FPDF, anchos: list, encabezados: list, filas: list, alineados) -> None:
    with pdf.table(
        borders_layout="ALL",
        text_align=alineados,
        col_widths=anchos,
        line_height=5,
        padding=1.4,
        num_heading_rows=1,
        headings_style=FontFace(emphasis="BOLD", size_pt=8.5, fill_color=_HEADER_FILL, color=_HEADER_TEXT),
        cell_fill_color=_ZEBRA,
        cell_fill_mode="ROWS",
    ) as tabla:
        fila = tabla.row()
        for texto in encabezados:
            fila.cell(texto)
        for valores in filas:
            fila = tabla.row()
            for valor in valores:
                fila.cell(str(valor))


def _tabla(pdf: FPDF, anchos: list, fila: list, estilo: str = "") -> None:
    if estilo == "header":
        pdf.set_font("helvetica", "B", 8.5)
        pdf.set_fill_color(*_HEADER_FILL)
    elif estilo == "total":
        pdf.set_font("helvetica", "B", 8.5)
        pdf.set_fill_color(240, 240, 240)
    else:
        pdf.set_font("helvetica", "", 8)
    for texto, ancho in zip(fila, anchos):
        pdf.cell(ancho, 7, str(texto), border=1, fill=bool(estilo))
    pdf.ln()


def _limpia(texto) -> str:
    return str(texto if texto is not None else "").replace("\u2019", "'").encode("latin-1", "replace").decode("latin-1")


def pdf_empresa(cliente: str, mes: str) -> bytes:
    """PDF estilo 'ventas completas': facturas vendidas a un cliente (SIN columna proveedor)."""
    db.reconciliar_ventas_mes(mes)
    ventas = [v for v in db.leer_ventas_mes(mes) if v["Cliente_Razon_Social"] == cliente]
    facturas_ids = []
    for v in ventas:
        facturas_ids += [i.strip() for i in v["Facturas_IDs"].split(",") if i.strip()]
    ids_set = set(facturas_ids)
    facturas = [f for f in db.leer_facturas_mes(mes) if f["ID"] in ids_set]
    facturas.sort(key=lambda f: (f["Fecha_Emision"], f["Nro_Factura"]))

    total_nominal = sum(f["Monto_Total"] for f in facturas)
    total_cobrar = sum(v["Precio_Cobrado"] for v in ventas)
    total_cobrado = sum(v["Total_Cobrado"] for v in ventas)
    saldo = round(total_cobrar - total_cobrado, 2)
    ficha = next((c for c in db.leer_clientes() if c["Nombre_Razon_Social"] == cliente), {})
    try:
        pct_ficha = float(ficha.get("Pct_Venta") or 0)
    except (TypeError, ValueError):
        pct_ficha = 0.0
    contacto = " - ".join(
        p
        for p in (
            str(ficha.get("Contacto", "") or "").strip(),
            str(ficha.get("Telefono", "") or "").strip(),
        )
        if p
    )

    pdf = _pdf_base(f"VENTAS COMPLETAS - {_limpia(cliente)} - {_limpia(mes)}")
    if contacto:
        pdf.set_font("helvetica", "", 8.5)
        pdf.cell(0, 6, f"WhatsApp / Contacto: {_limpia(contacto)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    filas = []
    for f in facturas:
        venta = next((v for v in ventas if f["ID"] in [i.strip() for i in v["Facturas_IDs"].split(",")]), None)
        if pct_ficha > 0:
            pct_venta = pct_ficha
        elif venta and venta["Monto_Nominal"]:
            pct_venta = round(venta["Precio_Cobrado"] / venta["Monto_Nominal"] * 100, 2)
        else:
            pct_venta = 0.0
        filas.append(
            [
                _limpia(f["Fecha_Emision"] or "-"),
                _limpia(f["Nro_Factura"] or "-"),
                f"{f['Monto_Total']:,.2f}",
                f"{pct_venta:g}%",
                f"{f['Monto_Total'] * pct_venta / 100:,.2f}",
            ]
        )
    filas.append(["TOTALES", "", f"{total_nominal:,.2f}", "", f"{total_cobrar:,.2f}"])
    _tabla_datos(
        pdf,
        [26, 34, 30, 22, 34],
        ["Fecha", "Factura N", "Monto (Bs)", "% Venta", "A cobrar (Bs)"],
        filas,
        ("CENTER", "CENTER", "RIGHT", "RIGHT", "RIGHT"),
    )

    pdf.ln(4)
    _tabla(pdf, [45, 40], ["TOTAL FACTURADO (Bs)", f"{total_nominal:,.2f}"], "total")
    _tabla(pdf, [45, 40], ["TOTAL A COBRAR (Bs)", f"{total_cobrar:,.2f}"], "total")
    _tabla(pdf, [45, 40], ["COBRADO (Bs)", f"{total_cobrado:,.2f}"])
    _tabla(pdf, [45, 40], ["SALDO (Bs)", f"{saldo:,.2f}"], "total")
    return bytes(pdf.output())


def pdf_resumen_mes(mes: str) -> bytes:
    """Resumen mensual: costos y ganancia por proveedor + totales de cobranza."""
    costos = reportes.resumen_costos_ganancia(mes)
    filas_v = reportes.resumen_ventas_cliente(mes)

    pdf = _pdf_base(f"CONTROL MENSUAL - {_limpia(mes)}")
    pdf.ln(1)
    _titulo_seccion(pdf, "Resumen de costos y ganancia")
    pdf.ln(1)

    filas_costos = [
        [
            _limpia(f["Proveedor"]),
            _limpia(f["Cliente"]),
            f"{f['Total_Facturado']:,.2f}",
            f"{f['Pct_Compra']:g}%",
            f"{f['Compra']:,.2f}",
            f"{f['Pct_Venta']:g}%",
            f"{f['Venta']:,.2f}",
            f"{f['Utilidad']:,.2f}",
        ]
        for f in costos
    ]
    if costos:
        filas_costos.append(
            [
                "TOTALES",
                "",
                f"{sum(f['Total_Facturado'] for f in costos):,.2f}",
                "",
                f"{sum(f['Compra'] for f in costos):,.2f}",
                "",
                f"{sum(f['Venta'] for f in costos):,.2f}",
                f"{sum(f['Utilidad'] for f in costos):,.2f}",
            ]
        )
    _tabla_datos(
        pdf,
        [34, 64, 30, 18, 28, 18, 28, 30],
        ["Proveedor", "Cliente", "Total Facturado", "% Comp", "Compra", "% Venta", "Venta", "Utilidad"],
        filas_costos,
        ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
    )

    pdf.add_page()
    _titulo_seccion(pdf, "Ventas resumen por cliente")
    pdf.ln(1)

    filas_ventas = [
        [
            str(f["Nro"]),
            _limpia(f["Cliente"]),
            _limpia(f["Rubro"]),
            f"{f['Monto']:,.2f}",
            f"{f['Cobrar']:,.2f}",
            f"{f['Pct']:g}%",
            f"{f['Cobrado']:,.2f}",
            f"{f['Saldo']:,.2f}",
        ]
        for f in filas_v
    ]
    if filas_v:
        filas_ventas.append(
            [
                "",
                "TOTALES",
                "",
                f"{sum(f['Monto'] for f in filas_v):,.2f}",
                f"{sum(f['Cobrar'] for f in filas_v):,.2f}",
                "",
                f"{sum(f['Cobrado'] for f in filas_v):,.2f}",
                f"{sum(f['Saldo'] for f in filas_v):,.2f}",
            ]
        )
    _tabla_datos(
        pdf,
        [12, 80, 26, 30, 30, 16, 28, 28],
        ["#", "Cliente", "Rubro", "Monto", "Cobrar", "%", "Cobrado", "Saldo"],
        filas_ventas,
        ("CENTER", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
    )
    return bytes(pdf.output())


def pdfs_por_empresa_zip(mes: str) -> tuple[bytes, str]:
    """Un PDF por empresa cliente con ventas en el mes, empaquetado en ZIP."""
    db.reconciliar_ventas_mes(mes)
    clientes = sorted({v["Cliente_Razon_Social"] for v in db.leer_ventas_mes(mes)})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for cliente in clientes:
            z.writestr(f"{cliente}.pdf", pdf_empresa(cliente, mes))
    nombre = f"pdfs por empresa - {mes}.zip"
    return buffer.getvalue(), nombre
