"""Reportes en PDF: ventas completas por empresa y resumen mensual."""

import io
import zipfile
from datetime import date

from fpdf import FPDF

import db
import reportes

__all__ = ["pdf_empresa", "pdf_resumen_mes", "pdfs_por_empresa_zip"]


def _pdf_base(titulo: str) -> FPDF:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(23, 94, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(0, 12, titulo, new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    return pdf


def _tabla(pdf: FPDF, anchos: list, fila: list, estilo: str = "") -> None:
    if estilo == "header":
        pdf.set_font("helvetica", "B", 9.5)
        pdf.set_fill_color(220, 235, 225)
    elif estilo == "total":
        pdf.set_font("helvetica", "B", 9.5)
        pdf.set_fill_color(240, 240, 240)
    else:
        pdf.set_font("helvetica", "", 9)
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
    ficha = next(
        (c for c in db.leer_clientes() if c["Nombre_Razon_Social"] == cliente), {}
    )
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
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, f"WhatsApp / Contacto: {_limpia(contacto)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    anchos = [25, 62, 30, 22, 22, 25, 30]
    _tabla(pdf, anchos, ["Fecha", "Empresa emisora", "NIT", "Factura N", "Monto (Bs)", "% Venta", "A cobrar (Bs)"], "header")
    for f in facturas:
        venta = next((v for v in ventas if f["ID"] in [i.strip() for i in v["Facturas_IDs"].split(",")]), None)
        pct_venta = (venta["Precio_Cobrado"] / venta["Monto_Nominal"] * 100) if venta and venta["Monto_Nominal"] else 0
        _tabla(
            pdf,
            anchos,
            [
                _limpia(f["Fecha_Emision"] or "-"),
                _limpia(f["Razon_Social"] or "-"),
                _limpia(f["NIT_Emisor"] or "-"),
                _limpia(f["Nro_Factura"] or "-"),
                f"{f['Monto_Total']:,.2f}",
                f"{pct_venta:g}%",
                f"{f['Monto_Total'] * pct_venta / 100:,.2f}",
            ],
        )
    pdf.ln(4)
    _tabla(pdf, [45, 40], ["TOTAL FACTURADO (Bs)", f"{total_nominal:,.2f}"], "total")
    _tabla(pdf, [45, 40], ["TOTAL A COBRAR (Bs)", f"{total_cobrar:,.2f}"], "total")
    _tabla(pdf, [45, 40], ["COBRADO (Bs)", f"{total_cobrado:,.2f}"])
    _tabla(pdf, [45, 40], ["SALDO (Bs)", f"{saldo:,.2f}"], "total")
    pdf.set_font("helvetica", "", 8)
    pdf.ln(2)
    pdf.cell(0, 6, f"Generado el {date.today().isoformat()} - Facturador OCR", align="R")
    return bytes(pdf.output())


def pdf_resumen_mes(mes: str) -> bytes:
    """Resumen mensual: costos y ganancia por proveedor + totales de cobranza."""
    costos = reportes.resumen_costos_ganancia(mes)
    filas_v = reportes.resumen_ventas_cliente(mes)

    pdf = _pdf_base(f"CONTROL MENSUAL - {_limpia(mes)}")
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Resumen de costos y ganancia", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    anchos = [38, 60, 32, 18, 30, 18, 32, 32]
    _tabla(pdf, anchos, ["Proveedor", "Cliente", "Total Facturado", "% Comp", "Compra", "% Venta", "Venta", "Utilidad"], "header")
    for f in costos:
        _tabla(
            pdf,
            anchos,
            [
                _limpia(f["Proveedor"]),
                _limpia(f["Cliente"]),
                f"{f['Total_Facturado']:,.2f}",
                f"{f['Pct_Compra']:g}%",
                f"{f['Compra']:,.2f}",
                f"{f['Pct_Venta']:g}%",
                f"{f['Venta']:,.2f}",
                f"{f['Utilidad']:,.2f}",
            ],
        )
    if costos:
        _tabla(
            pdf,
            anchos,
            [
                "TOTALES",
                "",
                f"{sum(f['Total_Facturado'] for f in costos):,.2f}",
                "",
                f"{sum(f['Compra'] for f in costos):,.2f}",
                "",
                f"{sum(f['Venta'] for f in costos):,.2f}",
                f"{sum(f['Utilidad'] for f in costos):,.2f}",
            ],
            "total",
        )

    pdf.ln(6)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Ventas resumen por cliente", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    anchos2 = [12, 75, 28, 32, 32, 18, 30, 32]
    _tabla(pdf, anchos2, ["#", "Cliente", "Rubro", "Monto", "Cobrar", "%", "Cobrado", "Saldo"], "header")
    for f in filas_v:
        _tabla(
            pdf,
            anchos2,
            [
                str(f["Nro"]),
                _limpia(f["Cliente"]),
                _limpia(f["Rubro"]),
                f"{f['Monto']:,.2f}",
                f"{f['Cobrar']:,.2f}",
                f"{f['Pct']:g}%",
                f"{f['Cobrado']:,.2f}",
                f"{f['Saldo']:,.2f}",
            ],
        )
    if filas_v:
        _tabla(
            pdf,
            anchos2,
            [
                "",
                "TOTALES",
                "",
                f"{sum(f['Monto'] for f in filas_v):,.2f}",
                f"{sum(f['Cobrar'] for f in filas_v):,.2f}",
                "",
                f"{sum(f['Cobrado'] for f in filas_v):,.2f}",
                f"{sum(f['Saldo'] for f in filas_v):,.2f}",
            ],
            "total",
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
