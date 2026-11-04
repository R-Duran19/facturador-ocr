"""Reportes mensuales: réplica de los Excel del cliente.

1. resumen_costos_ganancia(mes): por (proveedor-persona, cliente) —
   total facturado, %compra, compra, %venta, venta, utilidad.
2. resumen_ventas_cliente(mes): por cliente —
   monto nominal, cobrar, %, proveedor, entregado, cobrado, saldo, estado.
"""

from collections import defaultdict

import db

__all__ = ["resumen_costos_ganancia", "resumen_ventas_cliente"]


def _ventas_del_mes(mes: str) -> list:
    return db.leer_ventas_mes(mes)


def resumen_costos_ganancia(mes: str) -> list:
    """Filas: proveedor, cliente, total facturado, %compra, compra, %venta, venta, utilidad."""
    db.reconciliar_ventas_mes(mes)
    grupos = defaultdict(
        lambda: {"nominal": 0.0, "compra": 0.0, "venta": 0.0, "proveedores": set()}
    )
    for venta in _ventas_del_mes(mes):
        ids = [i.strip() for i in venta["Facturas_IDs"].split(",") if i.strip()]
        if not ids:
            continue
        facturas = [f for f in db.leer_facturas_mes(mes) if f["ID"] in set(ids)]
        if not facturas:
            continue
        nominal = sum(f["Monto_Total"] for f in facturas)
        compra = sum(f["Monto_Total"] * (f.get("Porcentaje_Compra") or 0) / 100.0 for f in facturas)
        proveedores = tuple(sorted({f["Proveedor_Asignado"] for f in facturas if f["Proveedor_Asignado"]}))
        clave = (" & ".join(proveedores) if proveedores else "—", venta["Cliente_Razon_Social"])
        g = grupos[clave]
        g["nominal"] += nominal
        g["compra"] += compra
        g["venta"] += venta["Precio_Cobrado"]
        g["proveedores"].update(proveedores)

    filas = []
    for (proveedor, cliente), g in grupos.items():
        pct_compra = g["compra"] / g["nominal"] * 100.0 if g["nominal"] > 0 else 0.0
        pct_venta = g["venta"] / g["nominal"] * 100.0 if g["nominal"] > 0 else 0.0
        filas.append(
            {
                "Proveedor": proveedor,
                "Cliente": cliente,
                "Total_Facturado": round(g["nominal"], 2),
                "Pct_Compra": round(pct_compra, 2),
                "Compra": round(g["compra"], 2),
                "Pct_Venta": round(pct_venta, 2),
                "Venta": round(g["venta"], 2),
                "Utilidad": round(g["venta"] - g["compra"], 2),
            }
        )
    filas.sort(key=lambda f: (f["Proveedor"], f["Cliente"]))
    return filas


def resumen_ventas_cliente(mes: str, incluir_todos: bool = False) -> list:
    """Filas consolidadas POR EMPRESA (como el Excel del cliente): una fila por cliente
    aunque tenga ventas de varios proveedores. incluir_todos agrega el catálogo con ceros."""
    db.reconciliar_ventas_mes(mes)
    clientes = {c["Nombre_Razon_Social"]: c for c in db.leer_clientes()}
    ventas = _ventas_del_mes(mes)
    facturas_mes = db.leer_facturas_mes(mes)
    ids_mes = {f["ID"]: f for f in facturas_mes}

    grupos = {}
    for v in ventas:
        g = grupos.setdefault(
            v["Cliente_Razon_Social"],
            {"nominal": 0.0, "cobrar": 0.0, "cobrado": 0.0, "proveedores": set()},
        )
        g["nominal"] += v["Monto_Nominal"]
        g["cobrar"] += v["Precio_Cobrado"]
        g["cobrado"] += v["Total_Cobrado"]
        ids = {i.strip() for i in v["Facturas_IDs"].split(",") if i.strip()}
        for f in facturas_mes:
            if f["ID"] in ids and f["Proveedor_Asignado"]:
                g["proveedores"].add(f["Proveedor_Asignado"])

    filas = []
    for i, (cliente, g) in enumerate(sorted(grupos.items(), key=lambda kv: -kv[1]["cobrar"]), 1):
        info = clientes.get(cliente, {})
        pct = g["cobrar"] / g["nominal"] * 100.0 if g["nominal"] > 0 else 0.0
        estado = "COBRADO" if g["cobrar"] - g["cobrado"] <= 0.005 else ("PARCIAL" if g["cobrado"] > 0 else "PENDIENTE")
        filas.append(
            {
                "Nro": i,
                "Cliente": cliente,
                "Rubro": info.get("Rubro", ""),
                "Monto": round(g["nominal"], 2),
                "Cobrar": round(g["cobrar"], 2),
                "Pct": round(pct, 2),
                "Proveedor": " / ".join(sorted(g["proveedores"])) or "—",
                "Entregado": "",
                "Cobrado": round(g["cobrado"], 2),
                "Saldo": round(g["cobrar"] - g["cobrado"], 2),
                "Estado": estado,
            }
        )

    if incluir_todos:
        presentes = {f["Cliente"] for f in filas}
        for nombre, info in clientes.items():
            if nombre in presentes:
                continue
            filas.append(
                {
                    "Nro": 0,
                    "Cliente": nombre,
                    "Rubro": info.get("Rubro", ""),
                    "Monto": 0.0,
                    "Cobrar": 0.0,
                    "Pct": float(info.get("Pct_Venta") or 0),
                    "Proveedor": "",
                    "Entregado": "",
                    "Cobrado": 0.0,
                    "Saldo": 0.0,
                    "Estado": "—",
                }
            )
        filas = sorted(filas, key=lambda f: (-f["Monto"], f["Cliente"].lower()))
        for i, f in enumerate(filas, 1):
            f["Nro"] = i
    return filas
