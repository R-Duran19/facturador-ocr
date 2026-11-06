"""Traspasa TODOS los datos de un mes a otro (facturas, ventas, pagos y PDFs).
Los enlaces (venta_facturas, cobros) se conservan porque los IDs no cambian.

Uso: venv/Scripts/python.exe mover_mes.py 2026_11_Noviembre 2026_10_Octubre [--si]
"""

import argparse
import shutil
import sys
from pathlib import Path

import config
import db
import respaldos


def mover(origen: str, destino: str, raiz: Path = None) -> dict:
    raiz = Path(raiz) if raiz else Path(".")
    db.inicializar()
    conn = db.conexion()
    carpeta_archivos = Path(config.CARPETA_ARCHIVOS)

    n_facturas = conn.execute("UPDATE facturas SET mes=? WHERE mes=?", (destino, origen)).rowcount
    n_ventas = conn.execute("UPDATE ventas SET mes=? WHERE mes=?", (destino, origen)).rowcount
    n_pagos = conn.execute("UPDATE pagos_proveedor SET mes=? WHERE mes=?", (destino, origen)).rowcount

    movidos = 0
    for r in conn.execute(
        "SELECT id, ruta_archivo FROM facturas WHERE mes=? AND TRIM(COALESCE(ruta_archivo,''))<>''", (destino,)
    ).fetchall():
        rel = str(r["ruta_archivo"]).replace("\\", "/")
        prefijo = carpeta_archivos.as_posix().strip("/") + "/"
        if rel.startswith(prefijo):
            rel = rel[len(prefijo):]
        origen_abs = raiz / carpeta_archivos / rel
        if not origen_abs.exists():
            continue
        destino_rel = destino + rel[len(origen):] if rel.startswith(origen + "/") or rel.startswith(origen + "\\") else f"{destino}/{Path(rel).name}"
        destino_abs = raiz / carpeta_archivos / destino_rel
        destino_abs.parent.mkdir(parents=True, exist_ok=True)
        final = destino_abs
        n = 2
        while final.exists():
            final = destino_abs.with_name(f"{destino_abs.stem}_{n}{destino_abs.suffix}")
            n += 1
        shutil.move(str(origen_abs), str(final))
        conn.execute(
            "UPDATE facturas SET ruta_archivo=? WHERE id=?",
            (final.relative_to(raiz / carpeta_archivos).as_posix(), r["id"]),
        )
        movidos += 1

    MESES_ES = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    def _legible(clave: str) -> str:
        try:
            anio, num, _ = str(clave).split("_", 2)
            return f"{MESES_ES[int(num) - 1]} {anio}"
        except Exception:
            return str(clave)

    leg_origen, leg_destino = _legible(origen), _legible(destino)
    if leg_origen != leg_destino:
        n_deudas = conn.execute(
            "UPDATE deudas_manuales SET mes_origen=? WHERE mes_origen=?", (leg_destino, leg_origen)
        ).rowcount
    else:
        n_deudas = 0

    conn.commit()

    carpeta_origen = raiz / carpeta_archivos / origen
    if carpeta_origen.exists():
        for sub in sorted(carpeta_origen.rglob("*"), reverse=True):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
        try:
            carpeta_origen.rmdir()
        except OSError:
            pass

    conn.close()
    return {
        "facturas": n_facturas,
        "ventas": n_ventas,
        "pagos": n_pagos,
        "pdfs_movidos": movidos,
        "deudas_renombradas": n_deudas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Traspasa todas las facturas/ventas/pagos de un mes a otro.")
    parser.add_argument("origen", help="mes origen (ej: 2026_11_Noviembre)")
    parser.add_argument("destino", help="mes destino (ej: 2026_10_Octubre)")
    parser.add_argument("--si", action="store_true", help="no pedir confirmación")
    args = parser.parse_args()

    db.inicializar()
    conn = db.conexion()
    n_origen = conn.execute("SELECT COUNT(*) FROM facturas WHERE mes=?", (args.origen,)).fetchone()[0]
    n_destino = conn.execute("SELECT COUNT(*) FROM facturas WHERE mes=?", (args.destino,)).fetchone()[0]
    conn.close()
    print(f"Traspasar '{args.origen}' ({n_origen} facturas) -> '{args.destino}' (ya tiene {n_destino})")
    print("Se mueven también ventas, pagos y los PDFs. Se crea backup antes.")

    if not args.si:
        respuesta = input("Escribí MOVER para confirmar: ").strip()
        if respuesta != "MOVER":
            print("Cancelado.")
            return 1

    backup = respaldos.crear_backup(f"antes-mover-{args.origen[:7]}")
    print(f"Backup: {backup}")
    resumen = mover(args.origen, args.destino)
    print("Traspaso completo. Resumen:")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
