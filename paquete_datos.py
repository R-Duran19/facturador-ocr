"""Paquete de datos: exporta catalogo + meses (+ PDFs) a un .zip para otra instalacion,
y lo importa en una instalación nueva sin tocar lo que ya tiene (merge additive con backup previo)."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import config
import db
import respaldos

__all__ = ["exportar", "importar"]

_TABLAS_MES = {
    "facturas": "SELECT * FROM facturas WHERE mes=? ORDER BY creado_en, id",
    "ventas": "SELECT * FROM ventas WHERE mes=? ORDER BY creado_en, id",
}


def _filas(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


def _columnas(conn, tabla):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")]


def exportar(meses=None):
    """Genera (bytes, nombre) del paquete. meses=None exporta todos."""
    db.inicializar()
    conn = db.conexion()
    catalogo = {
        "clientes": _filas(conn, "SELECT * FROM clientes ORDER BY nombre"),
        "proveedores": _filas(conn, "SELECT * FROM proveedores ORDER BY nombre"),
        "campos_config": _filas(conn, "SELECT * FROM campos_config ORDER BY orden, clave"),
    }
    if not meses:
        meses = [
            r["mes"]
            for r in conn.execute(
                "SELECT DISTINCT mes FROM facturas UNION SELECT DISTINCT mes FROM ventas ORDER BY mes"
            )
        ]
    datos = {
        "version": 1,
        "generado": date.today().isoformat(),
        "catalogo": catalogo,
        "deudas_manuales": _filas(conn, "SELECT * FROM deudas_manuales ORDER BY creado_en"),
        "cobros_deudas": _filas(conn, "SELECT * FROM cobros WHERE COALESCE(deuda_id,'') <> ''"),
        "meses": {},
    }
    rutas_pdf = set()
    for mes in meses:
        bloque = {nombre: _filas(conn, sql, (mes,)) for nombre, sql in _TABLAS_MES.items()}
        ids_ventas = [v["id"] for v in bloque["ventas"]]
        if ids_ventas:
            q = ",".join("?" * len(ids_ventas))
            bloque["venta_facturas"] = _filas(conn, f"SELECT * FROM venta_facturas WHERE venta_id IN ({q})", ids_ventas)
            bloque["cobros"] = _filas(conn, f"SELECT * FROM cobros WHERE venta_id IN ({q})", ids_ventas)
        else:
            bloque["venta_facturas"] = []
            bloque["cobros"] = []
        bloque["pagos_proveedor"] = _filas(conn, "SELECT * FROM pagos_proveedor WHERE mes=?", (mes,))
        datos["meses"][mes] = bloque
        for f in bloque["facturas"]:
            if f.get("ruta_archivo"):
                rutas_pdf.add(f["ruta_archivo"].replace("\\", "/"))
    conn.close()

    prefijo = Path(config.CARPETA_ARCHIVOS).as_posix().strip("/") + "/"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("datos.json", json.dumps(datos, ensure_ascii=False))
        for ruta in sorted(rutas_pdf):
            rel = ruta if ruta.startswith(prefijo) else (prefijo + ruta)
            p = Path(rel)
            if p.exists():
                z.write(p, p.as_posix())
    nombre = f"paquete_datos_{date.today().strftime('%Y%m%d')}.zip"
    return buffer.getvalue(), nombre


def importar(contenido_zip: bytes, raiz: Path = None) -> dict:
    """Importa el paquete en esta instalacion. Crea backup antes y extrae los PDFs."""
    raiz = Path(raiz) if raiz else Path(".")
    db.inicializar()
    respaldos.crear_backup("antes-import-datos")
    resumen = {}

    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as z:
        datos = json.loads(z.read("datos.json").decode("utf-8"))
        catalogo = datos.get("catalogo", {})
        conn = db.conexion()

        def _upsert_por_match(tabla, filas, sql_match, campo_match):
            cols = _columnas(conn, tabla)
            nuevos = act = 0
            for fila in filas:
                d = {k: v for k, v in fila.items() if k in cols}
                existente = conn.execute(sql_match, (fila.get(campo_match),)).fetchone()
                if existente:
                    sets = [k for k in d if k not in ("id", campo_match)]
                    if sets:
                        conn.execute(
                            f"UPDATE {tabla} SET {', '.join(f'{k}=?' for k in sets)} WHERE {campo_match}=?",
                            (*[d[k] for k in sets], fila.get(campo_match)),
                        )
                    act += 1
                else:
                    ks = list(d.keys())
                    conn.execute(
                        f"INSERT INTO {tabla} ({', '.join(ks)}) VALUES ({', '.join('?' * len(ks))})",
                        [d[k] for k in ks],
                    )
                    nuevos += 1
            return {"nuevos": nuevos, "actualizados": act}

        def _reponer(tabla, filas):
            cols = _columnas(conn, tabla)
            n = 0
            for fila in filas:
                d = {k: v for k, v in fila.items() if k in cols}
                ks = list(d.keys())
                conn.execute(
                    f"INSERT OR REPLACE INTO {tabla} ({', '.join(ks)}) VALUES ({', '.join('?' * len(ks))})",
                    [d[k] for k in ks],
                )
                n += 1
            return n

        resumen["clientes"] = _upsert_por_match(
            "clientes", catalogo.get("clientes", []), "SELECT id FROM clientes WHERE nombre=?", "nombre"
        )
        resumen["proveedores"] = _upsert_por_match(
            "proveedores", catalogo.get("proveedores", []), "SELECT id FROM proveedores WHERE nombre=?", "nombre"
        )
        resumen["campos_config"] = _upsert_por_match(
            "campos_config", catalogo.get("campos_config", []), "SELECT clave FROM campos_config WHERE clave=?", "clave"
        )
        conn.commit()

        for mes, bloque in datos.get("meses", {}).items():
            for tabla in ("facturas", "ventas", "venta_facturas", "cobros", "pagos_proveedor"):
                resumen[tabla] = resumen.get(tabla, 0) + _reponer(tabla, bloque.get(tabla, []))
        resumen["deudas_manuales"] = _reponer("deudas_manuales", datos.get("deudas_manuales", []))
        resumen["cobros_deudas"] = _reponer("cobros", datos.get("cobros_deudas", []))
        conn.commit()
        conn.close()

        n_archivos = 0
        for info in z.infolist():
            if info.filename == "datos.json":
                continue
            partes = Path(info.filename).parts
            if ".." in partes or Path(info.filename).is_absolute():
                continue
            destino = raiz / info.filename
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(z.read(info))
            n_archivos += 1
        resumen["archivos"] = n_archivos
    return resumen
