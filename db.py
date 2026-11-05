import json
import re
import sqlite3
from collections import defaultdict
import unicodedata
import uuid
from datetime import date as datetime_date
from pathlib import Path

from config import COMPRAS_HEADERS, RUTA_DB

DB_PATH = Path(RUTA_DB)

CLAVE_COL = {
    "ID": "id",
    "Nombre_Archivo": "nombre_archivo",
    "Proveedor_Asignado": "proveedor",
    "NIT_Emisor": "nit_emisor",
    "Razon_Social": "razon_social",
    "Razon_Social_Cliente": "razon_social_cliente",
    "Nro_Factura": "nro_factura",
    "Cod_Autorizacion": "cod_autorizacion",
    "Fecha_Emision": "fecha_emision",
    "Subtotal_Neto": "subtotal_neto",
    "Monto_Total": "monto_total",
    "Credito_Fiscal": "credito_fiscal",
    "Porcentaje_Compra": "pct_compra",
    "NIT_Cliente": "nit_cliente",
    "Estado_Pago": "estado_pago",
    "Observaciones": "observaciones",
    "Venta_ID": "venta_id",
    "Ruta_Archivo": "ruta_archivo",
}
COL_CLAVE = {v: k for k, v in CLAVE_COL.items()}
CLAVES_CORE = set(COMPRAS_HEADERS)
CLAVES_SISTEMA = {"ID", "Nombre_Archivo", "Proveedor_Asignado", "Venta_ID"}

CAMPOS_MONTO = {
    "Subtotal_Neto",
    "Monto_Total",
    "Credito_Fiscal",
    "Porcentaje_Compra",
    "Monto_Credito_Vendido",
    "Precio_Cobrado",
    "Comision_Pactada_Pct",
    "Pct_Venta",
}

CAMPOS_INICIALES = [
    ("Nombre_Archivo", "Archivo", "texto", "Nombre del archivo original", 1, 1, 0, 1),
    ("Proveedor_Asignado", "Proveedor", "texto", "Proveedor asignado al momento de cargar", 1, 1, 0, 2),
    ("NIT_Emisor", "NIT Emisor", "texto", "NIT o RUC del emisor de la factura", 1, 1, 1, 3),
    ("Razon_Social", "Razón Social Emisor", "texto", "Nombre o razón social del emisor", 1, 1, 1, 4),
    ("Razon_Social_Cliente", "Razón Social Cliente", "texto", "Nombre o razón social del comprador/cliente", 1, 1, 1, 4),
    ("Nro_Factura", "N° Factura", "texto", "Numero correlativo de la factura", 1, 1, 1, 5),
    ("Cod_Autorizacion", "Cód. Autorización", "texto", "Codigo de autorizacion o CUF", 1, 1, 1, 6),
    ("Fecha_Emision", "Fecha", "fecha", "Fecha de emision en formato YYYY-MM-DD", 1, 1, 1, 7),
    ("Subtotal_Neto", "Subtotal", "numero", "Monto neto antes de impuestos si figura", 1, 0, 0, 8),
    ("Monto_Total", "Monto Factura", "numero", "Importe total nominal de la factura", 1, 1, 1, 9),
    ("Credito_Fiscal", "Crédito Fiscal", "numero", "Base imponible valida para credito fiscal", 1, 1, 1, 10),
    ("Porcentaje_Compra", "% Compra", "numero", "Porcentaje de compra negociado para este lote", 1, 1, 0, 11),
    ("NIT_Cliente", "NIT Cliente", "texto", "NIT o CI del comprador/cliente", 1, 1, 1, 12),
    ("Estado_Pago", "Estado Pago", "texto", "PENDIENTE o PAGADO", 1, 1, 0, 13),
    ("Observaciones", "Observaciones", "texto", "Notas relevantes o irregularidades detectadas", 1, 1, 1, 14),
    ("Venta_ID", "Venta", "texto", "ID de la venta que incluye esta factura", 1, 1, 0, 15),
    ("Ruta_Archivo", "PDF", "texto", "Archivo original guardado", 1, 0, 0, 16),
]

_inicializada = False

SQL_TABLAS = """
CREATE TABLE IF NOT EXISTS proveedores (
    id TEXT PRIMARY KEY,
    nit TEXT DEFAULT '',
    nombre TEXT UNIQUE NOT NULL,
    telefono TEXT DEFAULT '',
    comision_pct REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS clientes (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    nit TEXT DEFAULT '',
    telefono TEXT DEFAULT '',
    notas TEXT DEFAULT '',
    rubro TEXT DEFAULT '',
    pct_venta REAL DEFAULT 5.0
);
CREATE TABLE IF NOT EXISTS facturas (
    id TEXT PRIMARY KEY,
    mes TEXT NOT NULL,
    nombre_archivo TEXT DEFAULT '',
    proveedor TEXT DEFAULT '',
    nit_emisor TEXT DEFAULT '',
    razon_social TEXT DEFAULT '',
    razon_social_cliente TEXT DEFAULT '',
    nro_factura TEXT DEFAULT '',
    cod_autorizacion TEXT DEFAULT '',
    fecha_emision TEXT DEFAULT '',
    subtotal_neto REAL DEFAULT 0,
    monto_total REAL DEFAULT 0,
    credito_fiscal REAL DEFAULT 0,
    pct_compra REAL DEFAULT 0,
    nit_cliente TEXT DEFAULT '',
    estado_pago TEXT DEFAULT 'PENDIENTE',
    observaciones TEXT DEFAULT '',
    venta_id TEXT DEFAULT '',
    extra TEXT DEFAULT '{}',
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_facturas_mes ON facturas(mes);
CREATE INDEX IF NOT EXISTS idx_facturas_nro ON facturas(nro_factura);
CREATE INDEX IF NOT EXISTS idx_facturas_venta ON facturas(venta_id);
CREATE TABLE IF NOT EXISTS ventas (
    id TEXT PRIMARY KEY,
    mes TEXT NOT NULL,
    cliente TEXT NOT NULL,
    monto_credito REAL DEFAULT 0,
    precio_cobrado REAL DEFAULT 0,
    estado_cobro TEXT DEFAULT 'PENDIENTE',
    entregado TEXT DEFAULT '',
    notas TEXT DEFAULT '',
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ventas_mes ON ventas(mes);
CREATE TABLE IF NOT EXISTS venta_facturas (
    venta_id TEXT NOT NULL,
    factura_id TEXT NOT NULL,
    PRIMARY KEY (venta_id, factura_id)
);
CREATE TABLE IF NOT EXISTS campos_config (
    clave TEXT PRIMARY KEY,
    etiqueta TEXT NOT NULL,
    tipo TEXT DEFAULT 'texto',
    descripcion TEXT DEFAULT '',
    nucleo INTEGER DEFAULT 0,
    activo INTEGER DEFAULT 1,
    en_ia INTEGER DEFAULT 1,
    orden INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cobros (
    id TEXT PRIMARY KEY,
    venta_id TEXT NOT NULL,
    fecha TEXT DEFAULT (date('now')),
    monto REAL DEFAULT 0,
    nota TEXT DEFAULT '',
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cobros_venta ON cobros(venta_id);
CREATE TABLE IF NOT EXISTS deudas_manuales (
    id TEXT PRIMARY KEY,
    cliente TEXT NOT NULL,
    mes_origen TEXT DEFAULT '',
    fecha TEXT DEFAULT (date('now')),
    concepto TEXT DEFAULT '',
    monto REAL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_deudas_cliente ON deudas_manuales(cliente);
CREATE TABLE IF NOT EXISTS extraction_cache (
    hash TEXT PRIMARY KEY,
    resultado TEXT NOT NULL,
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS gastos_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT DEFAULT (date('now')),
    modelo TEXT DEFAULT '',
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    costo REAL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pagos_proveedor (
    id TEXT PRIMARY KEY,
    proveedor TEXT NOT NULL,
    mes TEXT NOT NULL,
    fecha TEXT DEFAULT (date('now')),
    monto REAL DEFAULT 0,
    metodo TEXT DEFAULT '',
    nota TEXT DEFAULT '',
    creado_en TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pagos_prov ON pagos_proveedor(proveedor, mes);
CREATE TABLE IF NOT EXISTS lotes_historial (
    id TEXT PRIMARY KEY,
    mes TEXT NOT NULL,
    proveedor TEXT NOT NULL,
    pct_compra REAL DEFAULT 0,
    total INTEGER DEFAULT 0,
    ok INTEGER DEFAULT 0,
    duplicados INTEGER DEFAULT 0,
    errores INTEGER DEFAULT 0,
    monto_guardado REAL DEFAULT 0,
    inicio TEXT DEFAULT '',
    fin TEXT DEFAULT '',
    duracion_seg REAL DEFAULT 0,
    costo_ia REAL DEFAULT 0,
    creado_en TEXT DEFAULT (datetime('now'))
);
"""


def conexion() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _migrar(conn: sqlite3.Connection) -> None:
    for sql in (
        "ALTER TABLE clientes ADD COLUMN rubro TEXT DEFAULT ''",
        "ALTER TABLE clientes ADD COLUMN pct_venta REAL DEFAULT 5.0",
        "ALTER TABLE clientes ADD COLUMN bancarizado TEXT DEFAULT '¿?'",
        "ALTER TABLE clientes ADD COLUMN contacto TEXT DEFAULT ''",
        "ALTER TABLE ventas ADD COLUMN entregado TEXT DEFAULT ''",
        "ALTER TABLE facturas ADD COLUMN pct_compra REAL DEFAULT 0",
        "ALTER TABLE cobros ADD COLUMN metodo TEXT DEFAULT ''",
        "ALTER TABLE facturas ADD COLUMN ruta_archivo TEXT DEFAULT ''",
        "ALTER TABLE facturas ADD COLUMN razon_social_cliente TEXT DEFAULT ''",
        "ALTER TABLE cobros ADD COLUMN deuda_id TEXT DEFAULT ''",
        "UPDATE ventas SET entregado='SI' WHERE entregado != '' AND entregado != 'SI' AND entregado != 'NO'",
    ):
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "UPDATE campos_config SET activo=0, en_ia=0 WHERE clave='Subtotal_Neto'"
    )
    conn.execute(
        "UPDATE campos_config SET activo=1, en_ia=1, "
        "descripcion='NIT o CI del comprador/cliente' WHERE clave='NIT_Cliente'"
    )
    conn.execute(
        "UPDATE campos_config SET etiqueta='Razón Social Emisor' WHERE clave='Razon_Social'"
    )
    conn.execute(
        "INSERT OR IGNORE INTO campos_config (clave, etiqueta, tipo, descripcion, nucleo, activo, en_ia, orden) VALUES (?,?,?,?,?,?,?,?)",
        ("Porcentaje_Compra", "% Compra", "numero", "Porcentaje de compra negociado para este lote", 1, 1, 0, 11),
    )
    conn.execute(
        "UPDATE campos_config SET etiqueta='Monto Factura' WHERE clave='Monto_Total' AND etiqueta='Total'"
    )


def inicializar():
    global _inicializada
    if _inicializada:
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = conexion()
    conn.executescript(SQL_TABLAS)
    _migrar(conn)
    for clave, etiqueta, tipo, desc, nucleo, activo, en_ia, orden in CAMPOS_INICIALES:
        conn.execute(
            "INSERT OR IGNORE INTO campos_config (clave, etiqueta, tipo, descripcion, nucleo, activo, en_ia, orden) VALUES (?,?,?,?,?,?,?,?)",
            (clave, etiqueta, tipo, desc, nucleo, activo, en_ia, orden),
        )
    conn.commit()
    conn.close()
    _inicializada = True


def _fila_a_registro(row: sqlite3.Row) -> dict:
    registro = {clave: row[col] for clave, col in CLAVE_COL.items()}
    registro["Mes"] = row["mes"]
    try:
        extra = json.loads(row["extra"] or "{}")
        if isinstance(extra, dict):
            registro.update(extra)
    except (ValueError, TypeError):
        pass
    return registro


def _registro_a_valores(registro: dict) -> tuple:
    valores = []
    extra = {}
    for clave, col in CLAVE_COL.items():
        if clave == "ID":
            valores.append(registro.get("ID") or str(uuid.uuid4())[:8])
        elif clave == "Venta_ID":
            valores.append(registro.get("Venta_ID") or "")
        else:
            v = registro.get(clave, "")
            if clave in CAMPOS_MONTO:
                valores.append(_a_float(v))
            else:
                valores.append("" if v is None else str(v))
    for clave, v in registro.items():
        if clave.startswith("_"):
            continue
        if clave not in CLAVES_CORE and clave not in ("Mes", "Eliminar", "Duplicado", "Incluir", "nombre_archivo"):
            if v is not None and (not isinstance(v, float) or v == v) and str(v).strip() != "":
                extra[clave] = v
    valores.append(json.dumps(extra, ensure_ascii=False))
    return tuple(valores)


def _a_float(valor) -> float:
    try:
        texto = str(valor).replace(",", "").strip()
        if not texto or texto.lower() in ("nan", "none"):
            return 0.0
        return round(float(texto), 2)
    except (ValueError, TypeError):
        return 0.0


def inicializada() -> bool:
    return DB_PATH.exists()


# ---------- CAMPOS ----------

def listar_campos(solo_activos: bool = False) -> list:
    inicializar()
    conn = conexion()
    sql = "SELECT * FROM campos_config ORDER BY orden, clave"
    if solo_activos:
        sql = "SELECT * FROM campos_config WHERE activo=1 ORDER BY orden, clave"
    filas = [dict(r) for r in conn.execute(sql)]
    conn.close()
    return filas


def agregar_campo(etiqueta: str, tipo: str, descripcion: str = "", en_ia: bool = True) -> str:
    inicializar()
    base = (
        etiqueta.strip().lower()
        .replace(" ", "_").replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    base = "".join(ch for ch in base if ch.isalnum() or ch == "_") or "campo"
    clave = base
    conn = conexion()
    n = 2
    while conn.execute("SELECT 1 FROM campos_config WHERE clave=?", (clave,)).fetchone():
        clave = f"{base}_{n}"
        n += 1
    orden = conn.execute("SELECT COALESCE(MAX(orden),0)+1 FROM campos_config").fetchone()[0]
    conn.execute(
        "INSERT INTO campos_config (clave, etiqueta, tipo, descripcion, nucleo, activo, en_ia, orden) VALUES (?,?,?,?,0,1,?,?)",
        (clave, etiqueta.strip(), tipo, descripcion.strip(), 1 if en_ia else 0, orden),
    )
    conn.commit()
    conn.close()
    return clave


def actualizar_campo(clave: str, **valores) -> None:
    inicializar()
    permitidos = {"etiqueta", "tipo", "descripcion", "activo", "en_ia", "orden"}
    sets, params = [], []
    for k, v in valores.items():
        if k in permitidos:
            sets.append(f"{k}=?")
            params.append(int(v) if isinstance(v, bool) else v)
    if not sets:
        return
    conn = conexion()
    conn.execute(f"UPDATE campos_config SET {', '.join(sets)} WHERE clave=?", (*params, clave))
    conn.commit()
    conn.close()


def eliminar_campo(clave: str) -> bool:
    inicializar()
    conn = conexion()
    fila = conn.execute("SELECT nucleo FROM campos_config WHERE clave=?", (clave,)).fetchone()
    if not fila or fila["nucleo"]:
        conn.close()
        return False
    conn.execute("DELETE FROM campos_config WHERE clave=?", (clave,))
    conn.commit()
    conn.close()
    return True


# ---------- FACTURAS ----------

def leer_facturas_mes(mes: str) -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT * FROM facturas WHERE mes=? ORDER BY creado_en, id", (mes,)).fetchall()
    conn.close()
    return [_fila_a_registro(r) for r in filas]


def leer_todas_compras() -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT * FROM facturas ORDER BY mes, creado_en, id").fetchall()
    conn.close()
    return [_fila_a_registro(r) for r in filas]


def registrar_facturas_batch(mes: str, registros: list) -> int:
    inicializar()
    conn = conexion()
    n = 0
    for r in registros:
        r = dict(r)
        r.setdefault("Mes", mes)
        valores = _registro_a_valores(r)
        valores = valores[:-1] + ((r.get("Mes") or mes), valores[-1])
        columnas = [CLAVE_COL[c] for c in COMPRAS_HEADERS] + ["mes", "extra"]
        conn.execute(
            f"INSERT OR REPLACE INTO facturas ({', '.join(columnas)}) VALUES ({', '.join('?' for _ in columnas)})",
            valores,
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def actualizar_factura(mes: str, registro: dict) -> bool:
    inicializar()
    conn = conexion()
    fila = conn.execute("SELECT id FROM facturas WHERE id=?", (registro.get("ID", ""),)).fetchone()
    if not fila:
        conn.close()
        return False
    valores = _registro_a_valores(registro)
    columnas = [CLAVE_COL[c] for c in COMPRAS_HEADERS] + ["extra"]
    sets = ", ".join(f"{c}=?" for c in columnas)
    conn.execute(f"UPDATE facturas SET {sets} WHERE id=?", (*valores, registro["ID"]))
    conn.commit()
    conn.close()
    return True


def eliminar_factura(mes: str, id_factura: str) -> bool:
    inicializar()
    conn = conexion()
    cur = conn.execute("DELETE FROM facturas WHERE id=?", (id_factura,))
    conn.execute("DELETE FROM venta_facturas WHERE factura_id=?", (id_factura,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def leer_claves_existentes(mes: str = None) -> set:
    inicializar()
    conn = conexion()
    if mes:
        filas = conn.execute(
            "SELECT nit_emisor, nro_factura, cod_autorizacion FROM facturas WHERE mes=?", (mes,)
        ).fetchall()
    else:
        filas = conn.execute(
            "SELECT nit_emisor, nro_factura, cod_autorizacion FROM facturas"
        ).fetchall()
    conn.close()
    return {
        (
            str(r["nit_emisor"]).strip().upper(),
            str(r["nro_factura"]).strip().upper(),
            str(r["cod_autorizacion"]).strip().upper(),
        )
        for r in filas
    }


def buscar_factura_similar(nit: str, nro: str, cod: str, monto: float = None):
    """Busca una factura existente por NIT + N° (el código de autorización se acepta
    si coincide o si alguno de los dos no lo tiene — ej. importado desde Excel).
    Si no hay NIT ni N° ni código no se considera duplicado jamás.
    Si el monto conocido difiere del guardado, NO es duplicado: son facturas distintas."""
    nit_l = str(nit).strip().upper()
    nro_l = str(nro).strip().upper()
    cod_l = str(cod or "").strip().upper()
    if not nit_l and not nro_l and not cod_l:
        return None
    inicializar()
    conn = conexion()
    fila = conn.execute(
        "SELECT * FROM facturas WHERE TRIM(UPPER(nit_emisor))=? AND TRIM(UPPER(nro_factura))=? "
        "AND (TRIM(cod_autorizacion)='' OR TRIM(UPPER(cod_autorizacion))=TRIM(UPPER(?))) LIMIT 1",
        (nit_l, nro_l, cod_l),
    ).fetchone()
    if fila and monto is not None:
        monto_db = _a_float(fila["monto_total"])
        if monto_db > 0 and abs(monto_db - _a_float(monto)) > 0.02:
            conn.close()
            return None
    conn.close()
    return _fila_a_registro(fila) if fila else None


def existe_duplicado(nit: str, nro: str, cod: str, monto: float = None) -> bool:
    return buscar_factura_similar(nit, nro, cod, monto=monto) is not None


def aplicar_pct_compra(mes: str, proveedor: str, pct: float) -> int:
    """Corrige el % de compra de TODAS las facturas de un proveedor en un mes.
    Los montos a pagar/utilidad se recalculan en vivo en los reportes."""
    inicializar()
    conn = conexion()
    cur = conn.execute(
        "UPDATE facturas SET pct_compra=? WHERE mes=? AND proveedor=?",
        (_a_float(pct), str(mes), str(proveedor)),
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def listar_meses() -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute(
        "SELECT DISTINCT mes FROM facturas UNION SELECT DISTINCT mes FROM ventas ORDER BY mes DESC"
    ).fetchall()
    conn.close()
    return [r["mes"] for r in filas if r["mes"]]


def leer_facturas_filtro(
    mes: str = None,
    proveedor: str = None,
    estado_pago: str = None,
    texto: str = None,
    solo_duplicadas_venta: bool = False,
    limite: int = 500,
    offset: int = 0,
) -> tuple:
    inicializar()
    condiciones, params = [], []
    if mes:
        condiciones.append("mes=?")
        params.append(mes)
    if proveedor:
        condiciones.append("proveedor=?")
        params.append(proveedor)
    if estado_pago:
        condiciones.append("estado_pago=?")
        params.append(estado_pago)
    if texto:
        condiciones.append(
            "(razon_social LIKE ? OR razon_social_cliente LIKE ? OR nro_factura LIKE ? "
            "OR cod_autorizacion LIKE ? OR nit_emisor LIKE ? OR nit_cliente LIKE ? OR nombre_archivo LIKE ?)"
        )
        like = f"%{texto.strip()}%"
        params.extend([like] * 7)
    if solo_duplicadas_venta:
        condiciones.append("venta_id != ''")
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    conn = conexion()
    total = conn.execute(f"SELECT COUNT(*) FROM facturas {where}", params).fetchone()[0]
    filas = conn.execute(
        f"SELECT * FROM facturas {where} ORDER BY creado_en DESC, id LIMIT ? OFFSET ?",
        (*params, limite, offset),
    ).fetchall()
    conn.close()
    return [_fila_a_registro(r) for r in filas], total


def obtener_cache(hash_archivo: str):
    inicializar()
    conn = conexion()
    fila = conn.execute("SELECT resultado FROM extraction_cache WHERE hash=?", (hash_archivo,)).fetchone()
    conn.close()
    if not fila:
        return None
    try:
        return json.loads(fila["resultado"])
    except (ValueError, TypeError):
        return None


def guardar_cache(hash_archivo: str, resultado: dict) -> None:
    inicializar()
    conn = conexion()
    conn.execute(
        "INSERT OR REPLACE INTO extraction_cache (hash, resultado) VALUES (?,?)",
        (hash_archivo, json.dumps(resultado, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def limpiar_cache(max_registros: int = 20000) -> int:
    inicializar()
    conn = conexion()
    cur = conn.execute(
        "DELETE FROM extraction_cache WHERE hash NOT IN (SELECT hash FROM extraction_cache ORDER BY creado_en DESC LIMIT ?)",
        (max_registros,),
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def registrar_gasto_ia(modelo: str, tokens_in: int, tokens_out: int, precio_in: float, precio_out: float) -> float:
    """Registra el consumo real de una llamada a Gemini. Devuelve el costo en USD."""
    inicializar()
    costo = round((tokens_in / 1_000_000) * precio_in + (tokens_out / 1_000_000) * precio_out, 6)
    conn = conexion()
    conn.execute(
        "INSERT INTO gastos_ia (modelo, tokens_in, tokens_out, costo) VALUES (?,?,?,?)",
        (str(modelo), int(tokens_in), int(tokens_out), costo),
    )
    conn.commit()
    conn.close()
    return costo


def leer_gasto_ia() -> dict:
    """Resumen de gasto: hoy, mes calendario y total histórico."""
    inicializar()
    conn = conexion()
    por_mes = [
        {
            "mes": r["mes"],
            "llamadas": r["llamadas"],
            "tokens_in": r["tokens_in"],
            "tokens_out": r["tokens_out"],
            "costo": round(r["costo"], 4),
        }
        for r in conn.execute(
            "SELECT strftime('%Y-%m', fecha) AS mes, COUNT(*) AS llamadas, SUM(tokens_in) AS tokens_in, "
            "SUM(tokens_out) AS tokens_out, SUM(costo) AS costo FROM gastos_ia GROUP BY mes ORDER BY mes DESC"
        )
    ]
    def _suma(condicion: str) -> float:
        fila = conn.execute(f"SELECT COALESCE(SUM(costo),0) FROM gastos_ia WHERE {condicion}").fetchone()
        return round(fila[0] or 0.0, 4)

    resumen = {
        "hoy": _suma("fecha = date('now')"),
        "mes": _suma("strftime('%Y-%m', fecha) = strftime('%Y-%m', 'now')"),
        "total": _suma("1=1"),
        "por_mes": por_mes,
    }
    conn.close()
    return resumen


# ---------- PROVEEDORES ----------

def leer_proveedores() -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT nombre FROM proveedores ORDER BY nombre").fetchall()
    conn.close()
    return [r["nombre"] for r in filas] or ["Sin Asignar"]


def leer_proveedores_full() -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
    conn.close()
    return [
        {
            "NIT": r["nit"],
            "Nombre_Proveedor": r["nombre"],
            "Telefono": r["telefono"],
            "Comision_Pactada_Pct": r["comision_pct"],
        }
        for r in filas
    ]


def agregar_proveedor(nit: str, nombre: str, telefono: str, comision: float) -> None:
    inicializar()
    conn = conexion()
    conn.execute(
        "INSERT OR IGNORE INTO proveedores (id, nit, nombre, telefono, comision_pct) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4())[:8], str(nit).strip(), str(nombre).strip(), str(telefono).strip(), _a_float(comision)),
    )
    conn.commit()
    conn.close()


def eliminar_proveedor(nombre: str) -> bool:
    inicializar()
    conn = conexion()
    cur = conn.execute("DELETE FROM proveedores WHERE nombre=?", (str(nombre).strip(),))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------- CLIENTES ----------

def leer_clientes() -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()
    conn.close()
    return [
        {
            "ID_Cliente": r["id"],
            "Nombre_Razon_Social": r["nombre"],
            "NIT": r["nit"],
            "Telefono": r["telefono"],
            "Notas": r["notas"],
            "Contacto": r["contacto"] if "contacto" in r.keys() else "",
            "Rubro": r["rubro"] if "rubro" in r.keys() else "",
            "Pct_Venta": r["pct_venta"] if "pct_venta" in r.keys() else 5.0,
            "Bancarizado": r["bancarizado"] if "bancarizado" in r.keys() else "¿?",
        }
        for r in filas
    ]


def agregar_cliente(nombre: str, nit: str = "", telefono: str = "", notas: str = "", rubro: str = "", pct_venta: float = 5.0, bancarizado: str = "¿?", contacto: str = "") -> str:
    inicializar()
    id_cliente = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO clientes (id, nombre, nit, telefono, notas, rubro, pct_venta, bancarizado, contacto) VALUES (?,?,?,?,?,?,?,?,?)",
        (id_cliente, str(nombre).strip(), str(nit).strip(), str(telefono).strip(), str(notas).strip(), str(rubro).strip(), _a_float(pct_venta), str(bancarizado).strip(), str(contacto).strip()),
    )
    conn.commit()
    conn.close()
    return id_cliente


def actualizar_cliente(id_cliente: str, **valores) -> bool:
    inicializar()
    permitidos = {"nombre", "nit", "telefono", "notas", "rubro", "pct_venta", "bancarizado", "contacto"}
    sets, params = [], []
    for k, v in valores.items():
        if k in permitidos:
            sets.append(f"{k}=?")
            params.append(_a_float(v) if k == "pct_venta" else str(v).strip())
    if not sets:
        return False
    conn = conexion()
    cur = conn.execute(f"UPDATE clientes SET {', '.join(sets)} WHERE id=?", (*params, id_cliente))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def eliminar_cliente(nombre: str) -> bool:
    inicializar()
    conn = conexion()
    cur = conn.execute("DELETE FROM clientes WHERE nombre=?", (str(nombre).strip(),))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def actualizar_proveedor(nombre_actual: str, **valores) -> bool:
    inicializar()
    permitidos = {"nit", "nombre", "telefono", "comision_pct"}
    sets, params = [], []
    for k, v in valores.items():
        if k in permitidos:
            sets.append(f"{k}=?")
            params.append(_a_float(v) if k == "comision_pct" else str(v).strip())
    if not sets:
        return False
    conn = conexion()
    cur = conn.execute(f"UPDATE proveedores SET {', '.join(sets)} WHERE nombre=?", (*params, str(nombre_actual).strip()))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------- VENTAS ----------

def registrar_venta(
    mes: str,
    cliente: str,
    monto_credito: float,
    precio_cobrado: float,
    estado: str,
    facturas_ids: list = None,
    notas: str = "",
    entregado: str = "",
) -> str:
    inicializar()
    id_venta = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO ventas (id, mes, cliente, monto_credito, precio_cobrado, estado_cobro, entregado, notas) VALUES (?,?,?,?,?,?,?,?)",
        (id_venta, mes, str(cliente).strip(), _a_float(monto_credito), _a_float(precio_cobrado), estado, str(entregado).strip(), str(notas).strip()),
    )
    ids = [str(i).strip() for i in (facturas_ids or [])]
    for fid in ids:
        conn.execute("INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)", (id_venta, fid))
        conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (id_venta, fid))
    conn.commit()
    conn.close()
    return id_venta


def leer_ventas_mes(mes: str) -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute("SELECT * FROM ventas WHERE mes=? ORDER BY creado_en, id", (mes,)).fetchall()
    links = {}
    for r in conn.execute("SELECT venta_id, factura_id FROM venta_facturas"):
        links.setdefault(r["venta_id"], []).append(r["factura_id"])
    nominales = {
        r["venta_id"]: _a_float(r["total"])
        for r in conn.execute(
            "SELECT vf.venta_id AS venta_id, SUM(f.monto_total) AS total "
            "FROM venta_facturas vf JOIN facturas f ON f.id = vf.factura_id "
            "GROUP BY vf.venta_id"
        )
    }
    cobrados = {
        r["venta_id"]: _a_float(r["total"])
        for r in conn.execute("SELECT venta_id, SUM(monto) AS total FROM cobros GROUP BY venta_id")
    }
    conn.close()
    return [
        {
            "ID_Venta": r["id"],
            "Mes": r["mes"],
            "Cliente_Razon_Social": r["cliente"],
            "Monto_Credito_Vendido": r["monto_credito"],
            "Precio_Cobrado": r["precio_cobrado"],
            "Estado_Cobro": r["estado_cobro"],
            "Entregado": r["entregado"] if "entregado" in r.keys() else "",
            "Monto_Nominal": nominales.get(r["id"], 0.0),
            "Total_Cobrado": cobrados.get(r["id"], 0.0),
            "Saldo": round(_a_float(r["precio_cobrado"]) - cobrados.get(r["id"], 0.0), 2),
            "Facturas_IDs": ",".join(links.get(r["id"], [])),
            "Notas": r["notas"],
        }
        for r in filas
    ]


def actualizar_venta(mes: str, venta: dict) -> bool:
    inicializar()
    conn = conexion()
    id_venta = venta.get("ID_Venta", "")
    fila = conn.execute("SELECT id FROM ventas WHERE id=?", (id_venta,)).fetchone()
    if not fila:
        conn.close()
        return False
    conn.execute(
        "UPDATE ventas SET cliente=?, monto_credito=?, precio_cobrado=?, estado_cobro=?, entregado=?, notas=? WHERE id=?",
        (
            venta.get("Cliente_Razon_Social", ""),
            _a_float(venta.get("Monto_Credito_Vendido", 0.0)),
            _a_float(venta.get("Precio_Cobrado", 0.0)),
            venta.get("Estado_Cobro", "PENDIENTE"),
            venta.get("Entregado", ""),
            venta.get("Notas", ""),
            id_venta,
        ),
    )
    viejos = {r["factura_id"] for r in conn.execute("SELECT factura_id FROM venta_facturas WHERE venta_id=?", (id_venta,))}
    nuevos = {i.strip() for i in str(venta.get("Facturas_IDs", "")).split(",") if i.strip()}
    for fid in viejos - nuevos:
        conn.execute("DELETE FROM venta_facturas WHERE venta_id=? AND factura_id=?", (id_venta, fid))
        conn.execute("UPDATE facturas SET venta_id='' WHERE id=? AND venta_id=?", (fid, id_venta))
    for fid in nuevos - viejos:
        conn.execute("INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)", (id_venta, fid))
        conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (id_venta, fid))
    conn.commit()
    conn.close()
    return True


CANON_CLIENTES = [
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


def norm_cliente(nombre: str) -> str:
    """Normaliza nombres para compararlos sin acentos, puntuación ni variantes societarias."""
    s = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode().upper()
    s = s.replace("&", " & ")
    s = re.sub(r"[^A-Z0-9& ]", " ", s)
    s = re.sub(r"\bS\s*R\s*L\b", "SRL", s)
    s = re.sub(r"^EMPRESA\s+", "", s)
    s = re.sub(r"\s*&\s*", "&", s)
    return " ".join(s.split())


def canon_cliente(nombre: str) -> str:
    """Devuelve el nombre canónico de la ficha si el nombre coincide con un alias conocido."""
    n = norm_cliente(nombre)
    if not n:
        return ""
    for claves, destino in CANON_CLIENTES:
        if all(k in n for k in claves):
            return destino
    return str(nombre or "").strip()


def cliente_por_nombre(nombre: str):
    """Busca cliente por nombre canónico y normalizado (sin acentos/puntuación)."""
    inicializar()
    objetivo = norm_cliente(canon_cliente(nombre))
    if not objetivo:
        return None
    conn = conexion()
    for r in conn.execute("SELECT * FROM clientes"):
        actual = norm_cliente(canon_cliente(r["nombre"]))
        directo = norm_cliente(r["nombre"])
        if actual == objetivo or directo == objetivo:
            conn.close()
            return {
                "ID_Cliente": r["id"],
                "Nombre_Razon_Social": r["nombre"],
                "NIT": r["nit"],
                "Telefono": r["telefono"],
                "Notas": r["notas"],
                "Rubro": r["rubro"] if "rubro" in r.keys() else "",
                "Pct_Venta": r["pct_venta"] if "pct_venta" in r.keys() else 5.0,
            }
    conn.close()
    return None


def auto_venta_de_facturas(mes: str, cliente_nombre: str, nit: str, facturas_ids: list, notas: str = "") -> dict:
    """Crea o incrementa automáticamente la venta de un cliente con las facturas indicadas.
    Precio = suma de montos nominales × % venta de la ficha del cliente. Sin intervención."""
    inicializar()
    nombre_cliente = canon_cliente(cliente_nombre)
    if not nombre_cliente:
        raise ValueError("Factura sin comprador/cliente")
    info = cliente_por_nombre(nombre_cliente)
    if not info:
        agregar_cliente(nombre_cliente, nit)
        info = cliente_por_nombre(nombre_cliente)
    pct = float(info.get("Pct_Venta") or 5.0)
    nombre = info["Nombre_Razon_Social"]

    conn = conexion()
    existente = conn.execute(
        "SELECT id FROM ventas WHERE mes=? AND cliente=? ORDER BY creado_en DESC LIMIT 1",
        (mes, nombre),
    ).fetchone()
    nominales = {}
    for r in conn.execute("SELECT id, monto_total FROM facturas"):
        nominales[r["id"]] = _a_float(r["monto_total"])
    nominal_nuevo = sum(nominales.get(i, 0.0) for i in facturas_ids)
    precio_nuevo = round(nominal_nuevo * pct / 100.0, 2)

    if existente:
        id_venta = existente["id"]
        conn.execute(
            "UPDATE ventas SET monto_credito = monto_credito + ?, precio_cobrado = precio_cobrado + ?, notas=? WHERE id=?",
            (_a_float(nominal_nuevo), precio_nuevo, str(notas).strip(), id_venta),
        )
    else:
        id_venta = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO ventas (id, mes, cliente, monto_credito, precio_cobrado, estado_cobro, entregado, notas) VALUES (?,?,?,?,?,?,?,?)",
            (id_venta, mes, nombre, _a_float(nominal_nuevo), precio_nuevo, "PENDIENTE", "", str(notas).strip()),
        )
    for fid in facturas_ids:
        conn.execute("INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)", (id_venta, fid))
        conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (id_venta, fid))
    conn.commit()
    conn.close()
    return {"id_venta": id_venta, "cliente": nombre, "nominal": round(nominal_nuevo, 2), "precio": precio_nuevo, "pct": pct}


def reconciliar_ventas_mes(mes: str) -> int:
    """Crea las ventas faltantes del mes agrupadas por COMPRADOR/cliente.

    Solo toca facturas sin venta y con Razon_Social_Cliente cargado. Las facturas
    sin comprador quedan intactas para asignación manual. Es idempotente.
    Devuelve la cantidad de facturas enlazadas.
    """
    inicializar()
    conn = conexion()
    conn.execute(
        "UPDATE facturas SET razon_social = ("
        "  SELECT f2.razon_social FROM facturas f2 "
        "  WHERE f2.nit_emisor = facturas.nit_emisor AND TRIM(f2.razon_social) <> '' LIMIT 1) "
        "WHERE mes=? AND TRIM(razon_social)='' AND TRIM(nit_emisor)<>'' "
        "AND EXISTS (SELECT 1 FROM facturas f3 WHERE f3.nit_emisor = facturas.nit_emisor AND TRIM(f3.razon_social) <> '')",
        (mes,),
    )
    conn.commit()
    filas = conn.execute(
        "SELECT id, razon_social_cliente, nit_cliente, proveedor FROM facturas "
        "WHERE mes=? AND (venta_id IS NULL OR venta_id='') "
        "AND TRIM(COALESCE(razon_social_cliente,''))<>''",
        (mes,),
    ).fetchall()
    conn.close()

    grupos = {}
    for r in filas:
        nombre = canon_cliente(r["razon_social_cliente"])
        if not nombre:
            continue
        clave = (norm_cliente(nombre), str(r["nit_cliente"] or ""))
        g = grupos.setdefault(clave, {"nombre": nombre, "nit": r["nit_cliente"] or "", "ids": []})
        g["ids"].append(r["id"])

    total = 0
    for g in grupos.values():
        try:
            auto_venta_de_facturas(mes, g["nombre"], g["nit"], g["ids"], notas="Reconciliación automática")
            total += len(g["ids"])
        except ValueError:
            continue
    return total


def eliminar_venta(venta: dict) -> bool:
    inicializar()
    id_venta = venta.get("ID_Venta", "")
    conn = conexion()
    cur = conn.execute("DELETE FROM ventas WHERE id=?", (id_venta,))
    conn.execute("DELETE FROM cobros WHERE venta_id=?", (id_venta,))
    conn.execute("UPDATE facturas SET venta_id='' WHERE venta_id=?", (id_venta,))
    conn.execute("DELETE FROM venta_facturas WHERE venta_id=?", (id_venta,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------- COBROS ----------

def _sincronizar_estado_venta(conn: sqlite3.Connection, venta_id: str) -> None:
    venta = conn.execute(
        "SELECT precio_cobrado FROM ventas WHERE id=?", (venta_id,)
    ).fetchone()
    if not venta:
        return
    total = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM cobros WHERE venta_id=?", (venta_id,)
    ).fetchone()[0]
    precio = _a_float(venta["precio_cobrado"])
    total = _a_float(total)
    if precio > 0 and total >= precio - 0.005:
        estado = "COBRADO"
    elif total > 0:
        estado = "PARCIAL"
    else:
        estado = "PENDIENTE"
    conn.execute("UPDATE ventas SET estado_cobro=? WHERE id=?", (estado, venta_id))


def registrar_cobro(venta_id: str, monto: float, fecha: str = None, nota: str = "", metodo: str = "") -> str:
    inicializar()
    id_cobro = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO cobros (id, venta_id, fecha, monto, nota, metodo) VALUES (?,?,?,?,?,?)",
        (id_cobro, venta_id, fecha or datetime_date.today().isoformat(), _a_float(monto), str(nota).strip(), str(metodo).strip()),
    )
    _sincronizar_estado_venta(conn, venta_id)
    conn.commit()
    conn.close()
    return id_cobro


def leer_cobros(venta_id: str = None) -> list:
    inicializar()
    conn = conexion()
    if venta_id:
        filas = conn.execute(
            "SELECT c.*, v.cliente, v.mes FROM cobros c JOIN ventas v ON v.id=c.venta_id WHERE c.venta_id=? ORDER BY c.fecha, c.creado_en",
            (venta_id,),
        ).fetchall()
    else:
        filas = conn.execute(
            "SELECT c.*, v.cliente, v.mes FROM cobros c JOIN ventas v ON v.id=c.venta_id ORDER BY c.fecha DESC, c.creado_en DESC"
        ).fetchall()
    conn.close()
    return [
        {
            "ID_Cobro": r["id"],
            "Venta_ID": r["venta_id"],
            "Cliente": r["cliente"],
            "Mes": r["mes"],
            "Fecha": r["fecha"],
            "Monto": r["monto"],
            "Metodo": r["metodo"] if "metodo" in r.keys() else "",
            "Nota": r["nota"],
        }
        for r in filas
    ]


def eliminar_cobro(id_cobro: str) -> bool:
    inicializar()
    conn = conexion()
    fila = conn.execute("SELECT venta_id FROM cobros WHERE id=?", (id_cobro,)).fetchone()
    if not fila:
        conn.close()
        return False
    conn.execute("DELETE FROM cobros WHERE id=?", (id_cobro,))
    _sincronizar_estado_venta(conn, fila["venta_id"])
    conn.commit()
    conn.close()
    return True


def leer_deudas_manuales(cliente: str = None) -> list:
    """Deudas cargadas a mano de meses anteriores, con cobrado/saldo/estado calculados."""
    inicializar()
    conn = conexion()
    sql = "SELECT * FROM deudas_manuales"
    params = ()
    if cliente:
        sql += " WHERE cliente=?"
        params = (cliente,)
    sql += " ORDER BY fecha, creado_en"
    deudas = []
    for r in conn.execute(sql, params).fetchall():
        cobrado = _a_float(conn.execute("SELECT COALESCE(SUM(monto),0) FROM cobros WHERE deuda_id=?", (r["id"],)).fetchone()[0])
        monto = _a_float(r["monto"])
        saldo = round(monto - cobrado, 2)
        estado = "COBRADO" if saldo <= 0.005 else ("PARCIAL" if cobrado > 0 else "PENDIENTE")
        deudas.append(
            {
                "ID_Deuda": r["id"],
                "Cliente": r["cliente"],
                "Mes_Origen": r["mes_origen"],
                "Fecha": r["fecha"],
                "Concepto": r["concepto"],
                "Monto": monto,
                "Cobrado": round(cobrado, 2),
                "Saldo": max(saldo, 0.0),
                "Estado": estado,
            }
        )
    conn.close()
    return deudas


def agregar_deuda_manual(cliente: str, mes_origen: str, fecha: str, monto: float, concepto: str = "") -> str:
    inicializar()
    id_deuda = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO deudas_manuales (id, cliente, mes_origen, fecha, concepto, monto) VALUES (?,?,?,?,?,?)",
        (
            id_deuda,
            str(cliente).strip(),
            str(mes_origen or "").strip(),
            str(fecha or "").strip() or datetime_date.today().isoformat(),
            str(concepto or "").strip(),
            _a_float(monto),
        ),
    )
    conn.commit()
    conn.close()
    return id_deuda


def eliminar_deuda_manual(id_deuda: str) -> bool:
    """Elimina la deuda solo si no tiene cobros registrados."""
    inicializar()
    conn = conexion()
    cobros = conn.execute("SELECT COUNT(*) FROM cobros WHERE deuda_id=?", (id_deuda,)).fetchone()[0]
    if cobros:
        conn.close()
        return False
    cur = conn.execute("DELETE FROM deudas_manuales WHERE id=?", (id_deuda,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def registrar_cobro_deuda(id_deuda: str, monto: float, fecha: str = None, nota: str = "", metodo: str = "") -> str:
    inicializar()
    id_cobro = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO cobros (id, venta_id, deuda_id, fecha, monto, nota, metodo) VALUES (?,?,?,?,?,?,?)",
        (id_cobro, "", id_deuda, fecha or datetime_date.today().isoformat(), _a_float(monto), str(nota).strip(), str(metodo).strip()),
    )
    conn.commit()
    conn.close()
    return id_cobro


# ---------- PAGOS A PROVEEDORES ----------

def registrar_pago_proveedor(proveedor: str, mes: str, monto: float, fecha: str = None, metodo: str = "", nota: str = "") -> str:
    inicializar()
    id_pago = str(uuid.uuid4())[:8]
    conn = conexion()
    conn.execute(
        "INSERT INTO pagos_proveedor (id, proveedor, mes, fecha, monto, metodo, nota) VALUES (?,?,?,?,?,?,?)",
        (id_pago, str(proveedor).strip(), mes, fecha or datetime_date.today().isoformat(), _a_float(monto), str(metodo).strip(), str(nota).strip()),
    )
    conn.commit()
    conn.close()
    return id_pago


def leer_pagos_proveedor(proveedor: str = None, mes: str = None) -> list:
    inicializar()
    conn = conexion()
    condiciones, params = [], []
    if proveedor:
        condiciones.append("proveedor=?")
        params.append(proveedor)
    if mes:
        condiciones.append("mes=?")
        params.append(mes)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    filas = conn.execute(f"SELECT * FROM pagos_proveedor {where} ORDER BY fecha DESC, creado_en DESC", params).fetchall()
    conn.close()
    return [
        {
            "ID_Pago": r["id"],
            "Proveedor": r["proveedor"],
            "Mes": r["mes"],
            "Fecha": r["fecha"],
            "Monto": r["monto"],
            "Metodo": r["metodo"],
            "Nota": r["nota"],
        }
        for r in filas
    ]


def eliminar_pago_proveedor(id_pago: str) -> bool:
    inicializar()
    conn = conexion()
    cur = conn.execute("DELETE FROM pagos_proveedor WHERE id=?", (id_pago,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def resumen_pagos_proveedores(mes: str) -> list:
    """Por proveedor del mes: a pagar (Σ monto × %compra), pagado, saldo, estado."""
    inicializar()
    conn = conexion()
    filas = conn.execute(
        "SELECT proveedor, monto_total, pct_compra FROM facturas WHERE mes=? AND proveedor != ''", (mes,)
    ).fetchall()
    pagados = {
        r["proveedor"]: _a_float(r["total"])
        for r in conn.execute(
            "SELECT proveedor, SUM(monto) AS total FROM pagos_proveedor WHERE mes=? GROUP BY proveedor", (mes,)
        )
    }
    conn.close()
    por_prov = defaultdict(lambda: {"a_pagar": 0.0, "facturas": 0})
    for f in filas:
        p = por_prov[f["proveedor"]]
        p["a_pagar"] += _a_float(f["monto_total"]) * _a_float(f["pct_compra"] or 0) / 100.0
        p["facturas"] += 1
    out = []
    for proveedor, d in sorted(por_prov.items()):
        a_pagar = round(d["a_pagar"], 2)
        pagado = round(pagados.get(proveedor, 0.0), 2)
        saldo = round(a_pagar - pagado, 2)
        if pagado <= 0:
            estado = "PENDIENTE"
        elif saldo <= 0.005:
            estado = "PAGADO"
        else:
            estado = "PARCIAL"
        out.append(
            {
                "Proveedor": proveedor,
                "Facturas": d["facturas"],
                "A_Pagar": a_pagar,
                "Pagado": pagado,
                "Saldo": saldo,
                "Estado": estado,
            }
        )
    return out


# ---------- HISTORIAL DE LOTES ----------

def guardar_lote_historial(
    id_lote: str,
    mes: str,
    proveedor: str,
    pct_compra: float,
    total: int,
    ok: int,
    duplicados: int,
    errores: int,
    monto_guardado: float,
    inicio: str,
    fin: str,
    duracion_seg: float,
    costo_ia: float,
) -> None:
    inicializar()
    conn = conexion()
    conn.execute(
        "INSERT OR REPLACE INTO lotes_historial (id, mes, proveedor, pct_compra, total, ok, duplicados, errores, "
        "monto_guardado, inicio, fin, duracion_seg, costo_ia) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            id_lote, mes, proveedor, _a_float(pct_compra), int(total), int(ok), int(duplicados), int(errores),
            _a_float(monto_guardado), inicio, fin, round(duracion_seg, 1), round(costo_ia, 6),
        ),
    )
    conn.commit()
    conn.close()


def leer_historial_lotes(limite: int = 50) -> list:
    inicializar()
    conn = conexion()
    filas = conn.execute(
        "SELECT * FROM lotes_historial ORDER BY creado_en DESC, id DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return [
        {
            "ID_Lote": r["id"],
            "Mes": r["mes"],
            "Proveedor": r["proveedor"],
            "Pct": r["pct_compra"],
            "Total": r["total"],
            "Ok": r["ok"],
            "Duplicados": r["duplicados"],
            "Errores": r["errores"],
            "Monto": r["monto_guardado"],
            "Inicio": r["inicio"],
            "Fin": r["fin"],
            "Duracion": r["duracion_seg"],
            "Costo_Ia": r["costo_ia"],
        }
        for r in filas
    ]


def venta_por_id(id_venta: str):
    """Devuelve la venta completa (con cobrado/saldo) sin importar el mes."""
    inicializar()
    conn = conexion()
    fila = conn.execute("SELECT * FROM ventas WHERE id=?", (id_venta,)).fetchone()
    if not fila:
        conn.close()
        return None
    links = [r["factura_id"] for r in conn.execute("SELECT factura_id FROM venta_facturas WHERE venta_id=?", (id_venta,))]
    cobrado = _a_float(conn.execute("SELECT COALESCE(SUM(monto),0) FROM cobros WHERE venta_id=?", (id_venta,)).fetchone()[0])
    conn.close()
    precio = _a_float(fila["precio_cobrado"])
    return {
        "ID_Venta": fila["id"],
        "Mes": fila["mes"],
        "Cliente_Razon_Social": fila["cliente"],
        "Monto_Credito_Vendido": _a_float(fila["monto_credito"]),
        "Precio_Cobrado": precio,
        "Estado_Cobro": fila["estado_cobro"],
        "Entregado": fila["entregado"] if "entregado" in fila.keys() else "",
        "Total_Cobrado": cobrado,
        "Saldo": round(precio - cobrado, 2),
        "Facturas_IDs": ",".join(links),
        "Notas": fila["notas"],
    }
