"""Borra datos de forma controlada, con backup previo.

Uso:
  python reset_datos.py --todo                          # TODO (facturas/ventas/cobros/pagos/deudas/PDFs)
  python reset_datos.py --todo --conservar-catalogo     # TODO pero deja clientes y proveedores
  python reset_datos.py --meses 2026_09_Septiembre      # borra solo ese mes
  python reset_datos.py --meses 2026_09_Septiembre 2026_10_Octubre --borrar-pdfs

Pide escribir BORRAR para confirmar (o pasa --si).
"""

import argparse
import shutil
import sys
from pathlib import Path

import config
import db
import respaldos


def borrar_meses(meses: list, borrar_pdfs: bool = False) -> dict:
    db.inicializar()
    conn = db.conexion()
    resumen = {}
    for mes in meses:
        ids_ventas = [r["id"] for r in conn.execute("SELECT id FROM ventas WHERE mes=?", (mes,))]
        n_fact = conn.execute("SELECT COUNT(*) FROM facturas WHERE mes=?", (mes,)).fetchone()[0]
        n_ventas = len(ids_ventas)
        if ids_ventas:
            q = ",".join("?" * len(ids_ventas))
            resumen["cobros_borrados"] = resumen.get("cobros_borrados", 0) + conn.execute(
                f"DELETE FROM cobros WHERE venta_id IN ({q})", ids_ventas
            ).rowcount
            conn.execute(f"DELETE FROM venta_facturas WHERE venta_id IN ({q})", ids_ventas)
        conn.execute("DELETE FROM venta_facturas WHERE factura_id IN (SELECT id FROM facturas WHERE mes=?)", (mes,))
        conn.execute("DELETE FROM ventas WHERE mes=?", (mes,))
        conn.execute("DELETE FROM facturas WHERE mes=?", (mes,))
        conn.execute("DELETE FROM pagos_proveedor WHERE mes=?", (mes,))
        info = {"facturas": n_fact, "ventas": n_ventas}
        if borrar_pdfs:
            carpeta = Path(config.CARPETA_ARCHIVOS) / mes
            if carpeta.exists():
                shutil.rmtree(carpeta, ignore_errors=True)
                info["pdfs"] = "borrados"
        resumen[mes] = info
    conn.commit()
    conn.close()
    return resumen


def borrar_todo(conservar_catalogo: bool = True, borrar_pdfs: bool = False) -> dict:
    db.inicializar()
    conn = db.conexion()
    resumen = {}
    tablas = [
        "cobros",
        "venta_facturas",
        "ventas",
        "facturas",
        "pagos_proveedor",
        "deudas_manuales",
        "gastos_ia",
        "extraction_cache",
        "lotes_historial",
    ]
    for tabla in tablas:
        try:
            resumen[tabla] = conn.execute(f"DELETE FROM {tabla}").rowcount
        except Exception as e:
            resumen[tabla] = f"error: {e}"
    if conservar_catalogo:
        resumen["catalogo"] = "conservado (clientes y proveedores)"
    else:
        resumen["clientes"] = conn.execute("DELETE FROM clientes").rowcount
        resumen["proveedores"] = conn.execute("DELETE FROM proveedores").rowcount
    conn.commit()
    conn.close()
    if borrar_pdfs:
        carpeta = Path(config.CARPETA_ARCHIVOS)
        if carpeta.exists():
            for sub in carpeta.iterdir():
                if sub.is_dir():
                    shutil.rmtree(sub, ignore_errors=True)
            resumen["pdfs"] = "borrados"
    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Borra meses o todos los datos (con backup previo).")
    parser.add_argument("--todo", action="store_true", help="borra TODOS los datos")
    parser.add_argument("--meses", nargs="+", help="meses a borrar (ej: 2026_09_Septiembre)")
    parser.add_argument("--conservar-catalogo", action="store_true", help="con --todo: deja clientes y proveedores")
    parser.add_argument("--borrar-pdfs", action="store_true", help="también borra los PDFs de los meses")
    parser.add_argument("--si", action="store_true", help="no pedir confirmación")
    args = parser.parse_args()

    if not args.todo and not args.meses:
        parser.print_help()
        return 1

    print("Se creará un backup antes de borrar.")
    if args.todo:
        print("Va a borrar TODOS los datos (facturas, ventas, cobros, pagos, deudas, caché).")
        if not args.conservar_catalogo:
            print("También borrará CLIENTES y PROVEEDORES.")
    else:
        print(f"Va a borrar los meses: {', '.join(args.meses)}")
    if args.borrar_pdfs:
        print("También borrará los PDFs correspondientes.")

    if not args.si:
        respuesta = input("Escribí BORRAR para confirmar: ").strip()
        if respuesta != "BORRAR":
            print("Cancelado.")
            return 1

    backup = respaldos.crear_backup("antes-reset")
    print(f"Backup: {backup}")

    if args.todo:
        resumen = borrar_todo(conservar_catalogo=args.conservar_catalogo, borrar_pdfs=args.borrar_pdfs)
    else:
        resumen = borrar_meses(args.meses, borrar_pdfs=args.borrar_pdfs)
    print("Listo. Resumen:")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
