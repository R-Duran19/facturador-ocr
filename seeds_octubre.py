"""Seeders de clientes desde el Excel 'pedido octubre 2026'.

Carga nombre, rubro, contacto (nombre en WhatsApp del usuario), % venta,
bancarización, detalle del pedido y proveedores que lo traen.
Los clientes que ya existen solo reciben los datos que les falten.

Uso:
    python seeds_octubre.py            # carga y muestra avisos de datos faltantes
    python seeds_octubre.py --listar   # solo muestra lo que haría, sin escribir
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

import db

EXCEL = Path(__file__).parent / "docs" / "excels" / "pedido octubre       2026 (1).xlsx"

CONTACTOS_INVALIDOS = {"nose", "?", "¿?", "-", "x"}


def _norm(nombre: str) -> str:
    return " ".join(str(nombre or "").upper().replace(".", " ").replace(",", " ").split())


def _bancarizado(texto: str) -> str:
    t = " ".join(str(texto or "").lower().split())
    if "sin bancarizar" in t:
        return "NO"
    if "bancarizar" in t:
        return "SI"
    return "¿?"


def leer_pedidos() -> list:
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    ws = wb["Hoja1"]
    registros = []
    for f in ws.iter_rows(min_row=3, values_only=True):
        if not any(v not in (None, "") for v in f):
            continue
        nombre = str(f[1] or "").strip()
        if not nombre or nombre.lower().startswith("total"):
            continue
        registros.append(
            {
                "nombre": nombre,
                "rubro": str(f[2] or "").strip(),
                "contacto": str(f[3] or "").strip(),
                "pct": float(f[6]) if f[6] not in (None, "") else 5.0,
                "monto": float(f[5]) if f[5] not in (None, "") else None,
                "detalle": str(f[7] or "").strip(),
                "banc": _bancarizado(f[8]),
                "banc_raw": str(f[8] or "").strip(),
                "proveedores": str(f[9] or "").strip(),
            }
        )
    return registros


def avisos_del_registro(r: dict) -> list:
    """Datos faltantes/llamativos de un registro del pedido."""
    avisos = []
    if not r["rubro"]:
        avisos.append("rubro")
    if not r["contacto"]:
        avisos.append("contacto (WhatsApp)")
    elif r["contacto"].lower() in CONTACTOS_INVALIDOS:
        avisos.append(f'contacto invalido ("{r["contacto"]}")')
    if not r["proveedores"]:
        avisos.append("proveedor (quien lo trajo)")
    return avisos


def sembrar(listar: bool = False) -> dict:
    registros = leer_pedidos()
    existentes = {_norm(c["Nombre_Razon_Social"]): c for c in db.leer_clientes()}
    nuevos, actualizados = [], []
    avisos_totales: dict[str, list] = {}

    for r in registros:
        clave = _norm(r["nombre"])
        avisos = avisos_del_registro(r)
        if avisos:
            avisos_totales[r["nombre"]] = avisos

        notas = r["detalle"]
        if r["proveedores"]:
            notas = (notas + " | " if notas else "") + f"Proveedores: {r['proveedores']}"
        if r["banc_raw"]:
            notas = (notas + " | " if notas else "") + f"Bancarización: {r['banc_raw']}"
        if r["monto"] is not None:
            notas = (notas + " | " if notas else "") + f"Monto esperado (oct): {r['monto']:,.0f}"

        if listar:
            print(f"  · {r['nombre']:38} rub={r['rubro'] or '—':14} cont={r['contacto'] or '—':26} pct={r['pct']:g}% banc={r['banc']:3}")
            continue

        existente = existentes.get(clave)
        if existente:
            cambios = {}
            if not existente.get("Rubro") and r["rubro"]:
                cambios["rubro"] = r["rubro"]
            if not existente.get("Contacto") and r["contacto"]:
                cambios["contacto"] = r["contacto"]
            if existente.get("Bancarizado", "¿?") == "¿?" and r["banc"] != "¿?":
                cambios["bancarizado"] = r["banc"]
            if cambios:
                db.actualizar_cliente(existente["ID_Cliente"], **cambios)
                actualizados.append(r["nombre"])
            continue

        id_nuevo = db.agregar_cliente(
            r["nombre"],
            nit="",
            telefono="",
            notas=notas,
            rubro=r["rubro"],
            pct_venta=r["pct"],
            bancarizado=r["banc"],
            contacto=r["contacto"],
        )
        existentes[clave] = {"ID_Cliente": id_nuevo, **{k: v for k, v in r.items() if k in ("rubro", "contacto")}, "Bancarizado": r["banc"], "Rubro": r["rubro"], "Contacto": r["contacto"]}
        nuevos.append(r["nombre"])

    return {"registros": registros, "nuevos": nuevos, "actualizados": actualizados, "avisos": avisos_totales}


def main() -> None:
    listar = "--listar" in sys.argv
    res = sembrar(listar=listar)
    if listar:
        return
    print(f"Registros leidos: {len(res['registros'])}")
    print(f"Clientes nuevos:  {len(res['nuevos'])}")
    print(f"Clientes actualizados (completados datos faltantes): {len(res['actualizados'])}")
    for n in res["actualizados"]:
        print(f"   ~ {n}")
    if res["avisos"]:
        print(f"\nAVISO - DATOS FALTANTES ({len(res['avisos'])} clientes):")
        for nombre, faltan in res["avisos"].items():
            print(f"   ! {nombre}: falta {', '.join(faltan)}")
        print("\n   Completalos en Configuracion -> Clientes (panel DATOS FALTANTES).")
    total = db.leer_clientes()
    print(f"\nTotal clientes en el sistema: {len(total)}")
    incompletos = [
        c for c in total if not str(c.get("Contacto", "")).strip() or not str(c.get("Rubro", "")).strip()
    ]
    if incompletos:
        print(f"Aun con datos faltantes: {len(incompletos)} -> {', '.join(c['Nombre_Razon_Social'] for c in incompletos[:12])}")


if __name__ == "__main__":
    main()
