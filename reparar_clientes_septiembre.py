"""Reparación urgente de septiembre: asigna cada venta al comprador real."""

import json
import re
import sqlite3
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymupdf
from openpyxl import load_workbook

import respaldos
from config import CARPETA_ARCHIVOS, RUTA_DB

MES = "2026_09_Septiembre"
EXCEL_COSTOS = Path("septiembre 2026") / "resumen de costos y ganancia mes de septiembre  2026.xlsx"
EXCEL_VENTAS = Path("septiembre 2026") / "RESUMEN DE VENTAS  COMPLETAS  SEPTIMEBRE 2026.xlsx"

CLIENTES_ACTIVOS = {
    "Premier Fitness Club SRL": 5.0,
    "Edson Willy Alba Lobo": 5.0,
    "Aurora Quiroga de Campos": 5.0,
    "Nathalia Campos Valdivia": 5.0,
    "CAMPCAT SRL": 4.0,
    "Unilimpio SRL": 4.5,
    "Rocha Consultores S.R.L.": 5.0,
    "Maprin S.R.L.": 5.0,
    "P&GES SRL": 5.0,
    "Sergio Aparicio": 5.0,
    "Estelita Terrazas": 5.0,
    "Ulices Rodriguez Condori": 5.0,
    "Rodo Ernesto Ledezma": 5.0,
    "David Antezana": 5.0,
}

ALIASES = [
    (("P&GES",), "P&GES SRL"),
    (("PYGES",), "P&GES SRL"),
    (("MAPRIN",), "Maprin S.R.L."),
    (("ROCHA",), "Rocha Consultores S.R.L."),
    (("SERGIO", "APARICIO"), "Sergio Aparicio"),
    (("RODO", "LEDEZMA"), "Rodo Ernesto Ledezma"),
    (("AURORA", "QUIROGA"), "Aurora Quiroga de Campos"),
    (("EDSON", "ALBA"), "Edson Willy Alba Lobo"),
    (("NATHAL", "CAMPOS"), "Nathalia Campos Valdivia"),
    (("ULIC",), "Ulices Rodriguez Condori"),
    (("ULIS",), "Ulices Rodriguez Condori"),
    (("ESTELITA",), "Estelita Terrazas"),
    (("PREMIER",), "Premier Fitness Club SRL"),
    (("UNILIMPIO",), "Unilimpio SRL"),
    (("CAMPCAT",), "CAMPCAT SRL"),
    (("DAVID", "ANTEZANA"), "David Antezana"),
]

PROVEEDORES = {
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

FALLBACK_INCERPAZ_NRO = {
    "2102": "Rocha Consultores S.R.L.",
    "2088": "Rocha Consultores S.R.L.",
    "2112": "Maprin S.R.L.",
    "2148": "Maprin S.R.L.",
}

FALLBACK_INCERPAZ_MONTO = {
    37678.62: "Rocha Consultores S.R.L.",
    13080.00: "Rocha Consultores S.R.L.",
    13900.00: "Maprin S.R.L.",
    6963.46: "Maprin S.R.L.",
}

GENERICOS = re.compile(
    r"^(CANTIDAD|DESCRIPCION|DESCRIPCIÓN|PRODUCTO|FACTURA|NIT|COD|CODIGO|CÓDIGO|FECHA|"
    r"CLIENTE|SEÑOR|SENOR|NOMBRE|RAZON|RAZÓN|DIRECCION|DIRECCIÓN|TELEFONO|TELÉFONO|"
    r"SUCURSAL|PUNTO|MONTO|TOTAL|IMPORTE|SON|OBSERVACIONES|AUTORIZACION|AUTORIZACIÓN)\b",
    re.I,
)


def norm(valor):
    s = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    s = s.upper().replace("&", " & ")
    s = re.sub(r"[^A-Z0-9& ]", " ", s)
    s = re.sub(r"\bS\s*R\s*L\b", "SRL", s)
    s = re.sub(r"\bS\s*A\b", "SA", s)
    s = re.sub(r"^EMPRESA\s+", "", s)
    s = re.sub(r"\s*&\s*", "&", s)
    return " ".join(s.split())


def canon(nombre):
    n = norm(nombre)
    if not n:
        return ""
    for claves, destino in ALIASES:
        if all(k in n for k in claves):
            return destino
    return n


def normalizar_proveedor(nombre):
    n = norm(nombre)
    for clave, destino in PROVEEDORES.items():
        if clave in n:
            return destino
    return str(nombre or "").strip()


def leer_grupos():
    ws = load_workbook(EXCEL_COSTOS, data_only=True).active
    grupos = []
    proveedor = None
    for fila in ws.iter_rows(min_row=3, max_col=9, values_only=True):
        if fila[0] and "TOTAL" in norm(fila[0]):
            break
        if fila[0]:
            proveedor = normalizar_proveedor(fila[0])
        if not fila[1] or fila[2] in (None, ""):
            continue
        cliente = canon(fila[1])
        if cliente and cliente not in CLIENTES_ACTIVOS:
            CLIENTES_ACTIVOS[cliente] = float(fila[5] or 5)
        grupos.append(
            {
                "proveedor": proveedor,
                "cliente": cliente,
                "nominal": round(float(fila[2]), 2),
                "pct_venta": float(fila[5] or 5),
            }
        )
    return grupos


def leer_rubros():
    ws = load_workbook(EXCEL_VENTAS, data_only=True).active
    rubros = {}
    for fila in ws.iter_rows(min_row=3, max_col=3, values_only=True):
        if not fila[1]:
            continue
        cliente = canon(fila[1])
        if cliente and fila[2]:
            rubros.setdefault(cliente, str(fila[2]).strip().upper())
    return rubros


def crear_catalogo(conn):
    rubros = leer_rubros()
    conn.execute("DELETE FROM clientes")
    for nombre, pct in CLIENTES_ACTIVOS.items():
        conn.execute(
            "INSERT INTO clientes (id,nombre,nit,telefono,notas,rubro,pct_venta) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4())[:8], nombre, "", "", "", rubros.get(nombre, "CONST"), float(pct)),
        )
    conn.commit()


def texto_pdf(ruta_rel):
    ruta = Path(CARPETA_ARCHIVOS) / Path(str(ruta_rel or "").replace("\\", "/"))
    if not ruta.exists():
        return ""
    try:
        doc = pymupdf.open(ruta)
        texto = "\n".join(pagina.get_text() for pagina in doc)
        doc.close()
        return texto
    except Exception:
        return ""


def limpiar_candidato(linea, emisor):
    s = " ".join(str(linea or "").split())
    s = re.sub(r"^[^A-Za-zÁÉÍÓÚÑ]+", "", s).strip(" :.-")
    if len(s) < 3 or len(s) > 90:
        return ""
    n = norm(s)
    if not n or n in {"NOMBRE", "RAZON SOCIAL", "NOMBRE RAZON SOCIAL", "CLIENTE", "SENOR", "SENORES"}:
        return ""
    if n.startswith("RAZON SOCIAL") or n.startswith("NOMBRE RAZON"):
        return ""
    if GENERICOS.match(s):
        return ""
    if re.fullmatch(r"[\d\W_]+", s):
        return ""
    if emisor and (norm(emisor) == n or norm(emisor) in n):
        return ""
    if re.match(r"^(AV\.|AVENIDA|CALLE|ZONA|CARRETERA|KM\.|TELEFONO|SUCURSAL|NO\.)\b", s, re.I):
        return ""
    if not re.search(r"[A-Za-zÁÉÍÓÚÑ]{3}", s):
        return ""
    return s


def extraer_comprador(texto, emisor):
    lineas = [" ".join(l.split()) for l in texto.splitlines() if l.strip()]
    etiquetas = re.compile(
        r"(Nombre\s*/\s*Raz[oó]n\s*Social|Nombre\s+o\s+Raz[oó]n\s+Social|Nombre|Se[ñn]or(?:\(es\)|es)?|Cliente)",
        re.I,
    )
    for i, linea in enumerate(lineas):
        m = etiquetas.search(linea)
        if not m:
            continue
        candidato = limpiar_candidato(linea[m.end():], emisor)
        if candidato:
            return candidato
        for j in range(i + 1, min(i + 6, len(lineas))):
            candidato = limpiar_candidato(lineas[j], emisor)
            if candidato:
                return candidato
        for j in range(i - 1, max(i - 3, -1), -1):
            candidato = limpiar_candidato(lineas[j], emisor)
            if candidato:
                return candidato
    n = norm(texto)
    encontrados = []
    for claves, destino in ALIASES:
        if all(k in n for k in claves):
            encontrados.append(destino)
    encontrados = list(dict.fromkeys(encontrados))
    return encontrados[0] if len(encontrados) == 1 else ""


def extraer_nit_comprador(texto, nit_emisor):
    lineas = [" ".join(l.split()) for l in texto.splitlines() if l.strip()]
    etiqueta = re.compile(r"NIT\s*/\s*CI\s*/\s*CEX|NIT\s*/\s*CI|NIT\s*/\s*C\s*/\s*CEX", re.I)
    emisor = re.sub(r"\D", "", str(nit_emisor or ""))
    for i, linea in enumerate(lineas):
        m = etiqueta.search(linea)
        if not m:
            continue
        numeros = re.findall(r"\d[\d\s-]{5,}", linea[m.end():])
        for j in range(i + 1, min(i + 5, len(lineas))):
            numeros.extend(re.findall(r"\d[\d\s-]{5,}", lineas[j]))
        for numero in numeros:
            numero = re.sub(r"\D", "", numero)
            if 6 <= len(numero) <= 12 and numero != emisor:
                return numero
    return ""


def asignar(conn):
    facturas = list(
        conn.execute(
            "SELECT id, proveedor, nro_factura, monto_total, ruta_archivo, razon_social, nit_emisor "
            "FROM facturas WHERE mes=?",
            (MES,),
        )
    )
    extraidos = []
    for f in facturas:
        texto = texto_pdf(f["ruta_archivo"])
        comprador = extraer_comprador(texto, f["razon_social"])
        cliente = canon(comprador)
        nit = extraer_nit_comprador(texto, f["nit_emisor"])
        if cliente not in CLIENTES_ACTIVOS:
            if f["proveedor"] == "Anahi":
                cliente = "P&GES SRL"
            elif f["proveedor"] == "Incerpaz":
                cliente = FALLBACK_INCERPAZ_NRO.get(str(f["nro_factura"] or ""))
                if not cliente:
                    cliente = FALLBACK_INCERPAZ_MONTO.get(round(float(f["monto_total"] or 0), 2), "")
            else:
                cliente = ""
        conn.execute(
            "UPDATE facturas SET razon_social_cliente=?, nit_cliente=? WHERE id=?",
            (cliente or "", nit or "", f["id"]),
        )
        extraidos.append((f["id"], cliente, nit))
    conn.commit()

    contadores = {}
    for _, cliente, nit in extraidos:
        if cliente and nit:
            contadores.setdefault(cliente, Counter())[nit] += 1
    for cliente, ctr in contadores.items():
        nit = ctr.most_common(1)[0][0]
        conn.execute(
            "UPDATE facturas SET nit_cliente=? WHERE mes=? AND razon_social_cliente=? AND TRIM(nit_cliente)=''",
            (nit, MES, cliente),
        )
        conn.execute("UPDATE clientes SET nit=? WHERE nombre=?", (nit, cliente))
    conn.commit()


def exportar_ventas(conn, ids):
    if not ids:
        return
    q = ",".join("?" * len(ids))
    datos = []
    for venta in conn.execute(f"SELECT * FROM ventas WHERE id IN ({q})", ids):
        links = [dict(r) for r in conn.execute("SELECT * FROM venta_facturas WHERE venta_id=?", (venta["id"],))]
        datos.append({"venta": dict(venta), "links": links})
    destino = Path("backups") / f"ventas_antes_fix_clientes_{datetime.now():%Y%m%d_%H%M%S}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Respaldo de ventas: {destino}")


def reconstruir_ventas(conn):
    ids = [r["id"] for r in conn.execute("SELECT id FROM ventas WHERE mes=?", (MES,))]
    if ids:
        q = ",".join("?" * len(ids))
        cobros = conn.execute(f"SELECT COUNT(*) FROM cobros WHERE venta_id IN ({q})", ids).fetchone()[0]
        if cobros:
            raise SystemExit(f"Hay {cobros} cobros registrados; no se reconstruye para no perder datos.")
        exportar_ventas(conn, ids)
        conn.execute(f"DELETE FROM venta_facturas WHERE venta_id IN ({q})", ids)
        conn.execute("DELETE FROM ventas WHERE mes=?", (MES,))
    conn.execute("UPDATE facturas SET venta_id='' WHERE mes=?", (MES,))
    conn.commit()

    filas = list(
        conn.execute(
            "SELECT proveedor, razon_social_cliente AS cliente, SUM(monto_total) AS nominal, COUNT(*) AS n "
            "FROM facturas WHERE mes=? GROUP BY proveedor, razon_social_cliente "
            "ORDER BY proveedor, cliente",
            (MES,),
        )
    )
    for fila in filas:
        cliente = fila["cliente"]
        if not cliente:
            print(f"SIN CLIENTE: {fila['proveedor']} ({fila['n']} facturas, Bs {fila['nominal']:.2f})")
            continue
        nominal = round(float(fila["nominal"]), 2)
        pct = float(CLIENTES_ACTIVOS.get(cliente, 5.0))
        precio = round(nominal * pct / 100, 2)
        venta_id = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO ventas (id,mes,cliente,monto_credito,precio_cobrado,estado_cobro,entregado,notas) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (venta_id, MES, cliente, nominal, precio, "PENDIENTE", "", f"Reconstrucción septiembre · {fila['proveedor']}"),
        )
        for inv in conn.execute(
            "SELECT id FROM facturas WHERE mes=? AND proveedor=? AND razon_social_cliente=?",
            (MES, fila["proveedor"], cliente),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)",
                (venta_id, inv["id"]),
            )
            conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (venta_id, inv["id"]))
    conn.commit()


def validar(conn, grupos):
    print("\n=== FACTURA 673051c9 ===")
    factura = conn.execute(
        "SELECT id, proveedor, razon_social, razon_social_cliente, nit_cliente, monto_total, venta_id "
        "FROM facturas WHERE id='673051c9'"
    ).fetchone()
    print(dict(factura) if factura else "No encontrada")
    if factura and factura["venta_id"]:
        venta = conn.execute(
            "SELECT id, cliente, monto_credito, precio_cobrado FROM ventas WHERE id=?",
            (factura["venta_id"],),
        ).fetchone()
        print(dict(venta) if venta else "Venta no encontrada")

    print("\n=== VENTAS RECONSTRUIDAS ===")
    for v in conn.execute(
        "SELECT cliente, monto_credito, precio_cobrado, notas FROM ventas WHERE mes=? ORDER BY cliente, notas",
        (MES,),
    ):
        print(f"{v['cliente']:<34} Bs {v['monto_credito']:>13,.2f}   venta Bs {v['precio_cobrado']:>11,.2f}   {v['notas']}")

    print("\n=== COMPARACIÓN CONTRA EXCEL ===")
    db_grupos = {
        (r["proveedor"], r["cliente"]): round(float(r["nominal"]), 2)
        for r in conn.execute(
            "SELECT proveedor, razon_social_cliente AS cliente, SUM(monto_total) AS nominal "
            "FROM facturas WHERE mes=? GROUP BY proveedor, razon_social_cliente",
            (MES,),
        )
    }
    excel_grupos = {(g["proveedor"], g["cliente"]): g["nominal"] for g in grupos}
    claves = sorted(set(db_grupos) | set(excel_grupos))
    total_db = total_excel = 0.0
    for proveedor, cliente in claves:
        db = db_grupos.get((proveedor, cliente), 0.0)
        excel = excel_grupos.get((proveedor, cliente), 0.0)
        total_db += db
        total_excel += excel
        estado = "OK" if abs(db - excel) < 0.01 else "DIF"
        print(f"{estado}  {proveedor:<10} {cliente:<34} DB Bs {db:>13,.2f}   Excel Bs {excel:>13,.2f}   dif Bs {db - excel:>12,.2f}")
    print(f"\nTOTAL DB Bs {total_db:,.2f}   TOTAL Excel Bs {total_excel:,.2f}   diferencia Bs {total_db - total_excel:,.2f}")

    print("\n=== FACTURAS SIN CLIENTE ===")
    sin_cliente = list(
        conn.execute(
            "SELECT id, proveedor, nro_factura, monto_total FROM facturas "
            "WHERE mes=? AND TRIM(COALESCE(razon_social_cliente,''))='' ORDER BY proveedor, nro_factura",
            (MES,),
        )
    )
    for f in sin_cliente:
        print(dict(f))
    print(f"Total sin cliente: {len(sin_cliente)}")

    print("\n=== CONTROL COBOCE ===")
    print(
        "Ventas con cliente COBOCE:",
        conn.execute("SELECT COUNT(*) FROM ventas WHERE mes=? AND cliente LIKE '%COBOCE%'", (MES,)).fetchone()[0],
    )
    print(
        "Ventas totales:",
        conn.execute("SELECT COUNT(*) FROM ventas WHERE mes=?", (MES,)).fetchone()[0],
    )
    print(
        "Clientes en catálogo:",
        conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
    )
    print(
        "Venta total del mes:",
        round(conn.execute("SELECT COALESCE(SUM(precio_cobrado),0) FROM ventas WHERE mes=?", (MES,)).fetchone()[0], 2),
    )


def main():
    print("Creando backup de la base...")
    print("Backup:", respaldos.crear_backup("antes-fix-clientes"))
    grupos = leer_grupos()
    print(f"Grupos leídos del Excel: {len(grupos)}")
    conn = sqlite3.connect(RUTA_DB)
    conn.row_factory = sqlite3.Row
    try:
        columnas = {r["name"] for r in conn.execute("PRAGMA table_info(facturas)")}
        if "razon_social_cliente" not in columnas:
            conn.execute("ALTER TABLE facturas ADD COLUMN razon_social_cliente TEXT DEFAULT ''")
            conn.commit()
            print("Columna razon_social_cliente creada.")
        crear_catalogo(conn)
        print("Catálogo de clientes reconstruido.")
        asignar(conn)
        print("Compradores asignados.")
        reconstruir_ventas(conn)
        print("Ventas reconstruidas.")
        validar(conn, grupos)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
