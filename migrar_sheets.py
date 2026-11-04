import uuid

import sheets_manager as sm
import db


def main():
    print("=" * 60)
    print("MIGRACION: Google Sheets -> SQLite (facturas.db)")
    print("=" * 60)
    db.inicializar()

    conn = db.conexion()

    proveedores = sm.leer_proveedores_full()
    for p in proveedores:
        conn.execute(
            "INSERT OR IGNORE INTO proveedores (id, nit, nombre, telefono, comision_pct) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4())[:8], p["NIT"], p["Nombre_Proveedor"], p["Telefono"], p["Comision_Pactada_Pct"]),
        )
    print(f"Proveedores migrados: {len(proveedores)}")

    try:
        clientes = sm.leer_clientes()
    except Exception:
        clientes = []
    for c in clientes:
        conn.execute(
            "INSERT OR IGNORE INTO clientes (id, nombre, nit, telefono, notas) VALUES (?,?,?,?,?)",
            (c["ID_Cliente"] or str(uuid.uuid4())[:8], c["Nombre_Razon_Social"], c["NIT"], c["Telefono"], c["Notas"]),
        )
    print(f"Clientes migrados: {len(clientes)}")

    facturas = sm.leer_todas_compras()
    n_fact = 0
    for f in facturas:
        valores = db._registro_a_valores(f)
        valores = valores[:-1] + ((f.get("Mes") or ""), valores[-1])
        columnas = [db.CLAVE_COL[c] for c in db.COMPRAS_HEADERS] + ["mes", "extra"]
        conn.execute(
            f"INSERT OR IGNORE INTO facturas ({', '.join(columnas)}) VALUES ({', '.join('?' for _ in columnas)})",
            valores,
        )
        n_fact += 1
    print(f"Facturas migradas: {n_fact}")

    meses = [
        ws.title[: -len(sm.SUFIJO_COMPRAS)]
        for ws in sm.obtener_hoja().worksheets()
        if ws.title.endswith(sm.SUFIJO_COMPRAS)
    ]
    n_ven = 0
    for mes in meses:
        for v in sm.leer_ventas_mes(mes):
            conn.execute(
                "INSERT OR IGNORE INTO ventas (id, mes, cliente, monto_credito, precio_cobrado, estado_cobro, notas) VALUES (?,?,?,?,?,?,?)",
                (
                    v["ID_Venta"] or str(uuid.uuid4())[:8],
                    v["Mes"],
                    v["Cliente_Razon_Social"],
                    v["Monto_Credito_Vendido"],
                    v["Precio_Cobrado"],
                    v["Estado_Cobro"],
                    v["Notas"],
                ),
            )
            ids_facturas = [i.strip() for i in str(v.get("Facturas_IDs", "")).split(",") if i.strip()]
            for fid in ids_facturas:
                conn.execute(
                    "INSERT OR IGNORE INTO venta_facturas (venta_id, factura_id) VALUES (?,?)",
                    (v["ID_Venta"], fid),
                )
                conn.execute("UPDATE facturas SET venta_id=? WHERE id=?", (v["ID_Venta"], fid))
            n_ven += 1
    print(f"Ventas migradas: {n_ven}")

    conn.commit()
    conteo = {
        "proveedores": conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0],
        "clientes": conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
        "facturas": conn.execute("SELECT COUNT(*) FROM facturas").fetchone()[0],
        "ventas": conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0],
    }
    conn.close()
    print("\nContenido final de facturas.db:", conteo)
    print("El Google Sheet NO se modifica: queda como respaldo historico.")
    print("=" * 60)


if __name__ == "__main__":
    main()
