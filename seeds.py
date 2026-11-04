"""Datos iniciales del negocio: proveedores-persona y clientes activos.

Idempotente: INSERT OR IGNORE — correr varias veces no duplica.
Se ejecuta desde Ajustes o con: python seeds.py
"""

import db

__all__ = ["sembrar", "PROVEEDORES", "CLIENTES"]

PROVEEDORES = [
    ("Anahi", "", "", 3.5),
    ("Gladys", "", "", 4.0),
    ("Carmen", "", "", 4.0),
    ("Gary", "", "", 3.0),
    ("Javi", "", "", 1.5),
    ("Jhimmy", "", "", 2.0),
    ("Dio", "", "", 3.0),
]

CLIENTES = [
    ("Estacion Yapacani", "", "CONST", 5.0),
    ("Natalia Lopez", "", "CONST", 5.0),
    ("Ulices Rodriguez Condori", "", "CONST", 5.0),
    ("Maprin SRL", "", "CONST", 5.0),
    ("Pyges SRL", "", "CONST", 5.0),
    ("Biokube Bolivia SRL", "", "CONST", 5.0),
    ("Industria Metalurgica Inproco SRL", "", "CONST", 5.0),
    ("Compania Grafica Industrial LTDA", "", "MERCA", 4.5),
    ("Sergio Osvaldo Aparicio Yuja", "", "CONST", 5.0),
    ("Rocha Consultores SRL", "", "CONST", 5.0),
    ("MFRA SRL", "", "CONST", 5.0),
    ("Stova SRL", "", "CONST", 5.0),
    ("Unilimpio", "", "MERCA", 4.0),
    ("Estacion de Servicio La Ramada SRL", "", "CONST", 5.0),
    ("Roqui SRL", "", "CONST", 5.0),
    ("Todo Acero", "", "CONST", 5.0),
    ("Campero", "", "CONST", 5.0),
]


def sembrar() -> dict:
    db.inicializar()
    conn = db.conexion()
    n_prov = 0
    for nombre, nit, tel, comision in PROVEEDORES:
        existe = conn.execute(
            "SELECT 1 FROM proveedores WHERE nombre=?", (nombre,)
        ).fetchone()
        if not existe:
            conn.execute(
                "INSERT OR IGNORE INTO proveedores (id, nit, nombre, telefono, comision_pct) VALUES (?,?,?,?,?)",
                (str(__import__("uuid").uuid4())[:8], nit, nombre, tel, comision),
            )
            n_prov += 1
    n_cli = 0
    for nombre, nit, rubro, pct in CLIENTES:
        existe = conn.execute("SELECT 1 FROM clientes WHERE nombre=?", (nombre,)).fetchone()
        if not existe:
            conn.execute(
                "INSERT INTO clientes (id, nombre, nit, telefono, notas, rubro, pct_venta) VALUES (?,?,?,?,?,?,?)",
                (str(__import__("uuid").uuid4())[:8], nombre, nit, "", "", rubro, pct),
            )
            n_cli += 1
    conn.commit()
    conn.close()
    return {"proveedores_nuevos": n_prov, "clientes_nuevos": n_cli}


if __name__ == "__main__":
    resultado = sembrar()
    print(f"Seeders OK: {resultado}")
