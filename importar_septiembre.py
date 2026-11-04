"""Importador de la carpeta mensual del cliente (ej. septiembre 2026).

Lee proveedor/compra/*.xlsx (facturas + % compra) y proveedor/venta*/*.xlsx (% venta),
crea clientes (emisores con nombre canónico), facturas y ventas — replicando el mes.
Filas sin NOMBRE heredan el emisor del archivo. Nombres variantes se unifican
(MAPRIN S.R.L. = maprin srl = MAPRIN, AURORA QUIROGA = AURORA QUIROGA DE CAMPOS...).

Uso: venv/Scripts/python.exe importar_septiembre.py ["carpeta"] ["mes"]
"""

import json
import os
import sys
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime

from openpyxl import load_workbook

import db
import respaldos

CARPETA_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "septiembre 2026")
MES_DEFAULT = "2026_09_Septiembre"

MAPA_PROVEEDORES = {
    "ANAHI": "Anahi",
    "ANTONIO": "Antonio",
    "CARMEN": "Carmen",
    "DIONISIA": "Dio",
    "DIO": "Dio",
    "GARY": "Gary",
    "GLADYS": "Gladys",
    "INCERPAZ": "Incerpaz",
    "JHIMMY": "Jhimmy",
    "JHYMMY": "Jhimmy",
    "JAVI": "Javi",
    "LAURA": "Laura",
}

PCT_NUEVOS = {"Antonio": 3.0, "Incerpaz": 1.5, "Laura": 3.0}

def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper().strip()
    return " ".join(s.split())


def _a_float(v) -> float:
    try:
        return round(float(str(v).replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return 0.0


def _fecha_iso(v) -> str:
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d") if 2000 <= v.year <= 2100 else ""
        except ValueError:
            return ""
    texto = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.strptime(texto, fmt)
            if 2000 <= d.year <= 2100:
                return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _pct_de_header(ws) -> float:
    for fila in ws.iter_rows(min_row=1, max_row=1, values_only=True):
        for c in fila:
            try:
                num = float(str(c).strip())
                if 0 < num < 1:
                    return round(num * 100, 2)
                if 0 < num <= 30:
                    return round(num, 2)
            except (TypeError, ValueError):
                continue
    return 0.0


def _texto_nit(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _filas_datos(ws):
    filas = []
    for fila in ws.iter_rows(min_row=2, values_only=True):
        if any("TOTALES" in str(c).upper() for c in fila if c):
            continue
        try:
            fecha, nombre, nit, empresa, factura, monto = fila[1], fila[2], fila[3], fila[4], fila[5], fila[6]
        except IndexError:
            continue
        f = {
            "fecha": _fecha_iso(fecha),
            "nit_cliente": _texto_nit(nit),
            "comprador": str(nombre).strip() if nombre else "",
            "emisor": str(empresa).strip() if empresa else "",
            "nro": str(factura).strip() if factura is not None else "",
            "monto": _a_float(monto),
        }
        if f["monto"] > 0 and f["comprador"]:
            filas.append(f)
    return filas


def _archivos_xlsx(ruta: str):
    if not os.path.isdir(ruta):
        return []
    return [
        os.path.join(ruta, a)
        for a in sorted(os.listdir(ruta))
        if a.lower().endswith(".xlsx") and not a.startswith("~$")
    ]


def importar_carpeta(carpeta: str = CARPETA_DEFAULT, mes: str = MES_DEFAULT) -> dict:
    respaldos.crear_backup("antes-import")
    conn = db.conexion()
    for tabla in ("facturas", "ventas", "venta_facturas", "cobros", "clientes", "pagos_proveedor", "gastos_ia", "extraction_cache"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()

    total_facturas = 0
    total_ventas = 0
    clientes_nuevos = 0

    carpetas_prov = [
        d
        for d in os.listdir(carpeta)
        if os.path.isdir(os.path.join(carpeta, d)) and _norm(d) in MAPA_PROVEEDORES
    ]

    for carpeta_prov in sorted(carpetas_prov):
        proveedor = MAPA_PROVEEDORES[_norm(carpeta_prov)]
        if not conn.execute("SELECT 1 FROM proveedores WHERE nombre=?", (proveedor,)).fetchone():
            conn.execute(
                "INSERT INTO proveedores (id, nit, nombre, telefono, comision_pct) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4())[:8], "", proveedor, "", PCT_NUEVOS.get(proveedor, 5.0)),
            )

        grupos = defaultdict(
            lambda: {"facturas": [], "pct_venta": None, "nit": "", "comprador": "", "emisores": set()}
        )

        for ruta in _archivos_xlsx(os.path.join(carpeta, carpeta_prov, "compra")):
            ws = load_workbook(ruta, data_only=True).active
            pct_compra = _pct_de_header(ws)
            for f in _filas_datos(ws):
                cliente = db.canon_cliente(f["comprador"])
                g = grupos[cliente]
                g["comprador"] = g["comprador"] or f["comprador"]
                g["nit"] = g["nit"] or f["nit_cliente"]
                emisor = f["emisor"] or proveedor
                g["emisores"].add(emisor)
                fid = str(uuid.uuid4())[:8]
                extra = json.dumps(
                    {"Comprador_Original": f["comprador"], "Emisor_Original": emisor},
                    ensure_ascii=False,
                )
                conn.execute(
                    "INSERT INTO facturas (id, mes, nombre_archivo, proveedor, nit_emisor, razon_social, "
                    "razon_social_cliente, nro_factura, cod_autorizacion, fecha_emision, subtotal_neto, "
                    "monto_total, credito_fiscal, pct_compra, nit_cliente, estado_pago, observaciones, "
                    "venta_id, ruta_archivo, extra) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fid, mes, f"{f['nro'] or 'sin-numero'}.pdf", proveedor, "", emisor, cliente,
                        f["nro"], "", f["fecha"], 0.0, f["monto"], f["monto"], pct_compra,
                        f["nit_cliente"], "PENDIENTE", "Importada de Excel · comprador " + f["comprador"],
                        "", "", extra,
                    ),
                )
                g["facturas"].append((fid, f["monto"]))
                total_facturas += 1

        raiz_prov = os.path.join(carpeta, carpeta_prov)
        for sub in sorted(os.listdir(raiz_prov)):
            ruta_sub = os.path.join(raiz_prov, sub)
            if not os.path.isdir(ruta_sub) or not _norm(sub).startswith("VENTA"):
                continue
            for ruta in _archivos_xlsx(ruta_sub):
                ws = load_workbook(ruta, data_only=True).active
                pct_venta = _pct_de_header(ws)
                for f in _filas_datos(ws):
                    cliente = db.canon_cliente(f["comprador"])
                    if cliente in grupos:
                        if pct_venta:
                            grupos[cliente]["pct_venta"] = pct_venta
                        if f["nit_cliente"]:
                            grupos[cliente]["nit"] = grupos[cliente]["nit"] or f["nit_cliente"]

        for clave, g in grupos.items():
            if not g["facturas"]:
                continue
            nombre_cliente = clave
            nit = g["nit"]
            objetivo = db.norm_cliente(nombre_cliente)
            fila_cli = next(
                (
                    c
                    for c in conn.execute("SELECT id, nombre, pct_venta FROM clientes")
                    if db.norm_cliente(db.canon_cliente(c["nombre"])) == objetivo
                ),
                None,
            )
            if not fila_cli:
                id_cli = str(uuid.uuid4())[:8]
                conn.execute(
                    "INSERT INTO clientes (id, nombre, nit, telefono, notas, rubro, pct_venta) VALUES (?,?,?,?,?,?,?)",
                    (id_cli, nombre_cliente, nit, "", "", "", g["pct_venta"] or 5.0),
                )
                clientes_nuevos += 1
                id_cli_ref, pct_cliente = id_cli, g["pct_venta"] or 5.0
            else:
                id_cli_ref = fila_cli["id"]
                pct_cliente = _a_float(fila_cli["pct_venta"]) or g["pct_venta"] or 5.0
                if nit:
                    conn.execute("UPDATE clientes SET nit=? WHERE id=? AND (nit IS NULL OR nit='')", (nit, id_cli_ref))

            id_venta = str(uuid.uuid4())[:8]
            nominal = round(sum(m for _, m in g["facturas"]), 2)
            precio = round(nominal * pct_cliente / 100.0, 2)
            conn.execute(
                "INSERT INTO ventas (id, mes, cliente, monto_credito, precio_cobrado, estado_cobro, entregado, notas) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (id_venta, mes, nombre_cliente, nominal, precio, "PENDIENTE", "", f"Importado · proveedor {proveedor}"),
            )
            for fid, _ in g["facturas"]:
                conn.execute("INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)", (id_venta, fid))
                conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (id_venta, fid))
            total_ventas += 1

    conn.commit()
    conteo = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("proveedores", "clientes", "facturas", "ventas", "venta_facturas")
    }
    conn.close()
    return {
        "facturas": total_facturas,
        "ventas": total_ventas,
        "clientes_nuevos": clientes_nuevos,
        "conteo": conteo,
    }


if __name__ == "__main__":
    carpeta = sys.argv[1] if len(sys.argv) > 1 else CARPETA_DEFAULT
    mes = sys.argv[2] if len(sys.argv) > 2 else MES_DEFAULT
    db.inicializar()
    resultado = importar_carpeta(carpeta, mes)
    print("IMPORT:", {k: v for k, v in resultado.items() if k != "conteo"})
    print("CONTENIDO BD:", resultado["conteo"])
