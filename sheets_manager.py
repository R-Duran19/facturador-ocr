import uuid

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

from config import (
    CLIENTES_HEADERS,
    COMPRAS_HEADERS,
    GOOGLE_SHEET_MASTER_ID,
    HOJA_CLIENTES,
    HOJA_PROVEEDORES,
    HOJA_VENTAS,
    PROVEEDORES_HEADERS,
    SCOPES,
    SERVICE_ACCOUNT_FILE,
    SUFIJO_COMPRAS,
    VENTAS_HEADERS,
)

CAMPOS_MONTO = {
    "Subtotal_Neto",
    "Monto_Total",
    "Credito_Fiscal",
    "Monto_Credito_Vendido",
    "Precio_Cobrado",
    "Comision_Pactada_Pct",
}

_gc = None
_hoja = None


def _a_float(valor) -> float:
    try:
        texto = str(valor).replace(",", "").strip()
        if not texto or texto.lower() in ("nan", "none"):
            return 0.0
        return round(float(texto), 2)
    except (ValueError, TypeError):
        return 0.0


def obtener_cliente():
    global _gc
    if _gc is None:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        _gc = gspread.authorize(creds)
    return _gc


def obtener_hoja():
    global _hoja
    if _hoja is None:
        if not GOOGLE_SHEET_MASTER_ID or "PEGA" in GOOGLE_SHEET_MASTER_ID:
            raise RuntimeError("GOOGLE_SHEET_MASTER_ID no configurado en .env")
        _hoja = obtener_cliente().open_by_key(GOOGLE_SHEET_MASTER_ID)
    return _hoja


def _preparar_ws(sh, titulo: str, headers: list, permitir_rebuild: bool = True, filas: int = 1000):
    existentes = {ws.title: ws for ws in sh.worksheets()}
    ws = existentes.get(titulo)
    if ws is None:
        ws = sh.add_worksheet(title=titulo, rows=filas, cols=len(headers) + 2)
        ws.append_row(headers)
        return ws
    actual = ws.row_values(1) or []
    actual = actual[: len(headers)]
    if actual == headers:
        return ws
    if actual and headers[: len(actual)] == actual and len(headers) > len(actual):
        fin = rowcol_to_a1(1, len(headers))
        ws.update(values=[headers], range_name=f"A1:{fin}")
        return ws
    if permitir_rebuild:
        sh.del_worksheet(ws)
        ws = sh.add_worksheet(title=titulo, rows=filas, cols=len(headers) + 2)
        ws.append_row(headers)
        return ws
    return ws


def obtener_o_crear_hoja_base():
    sh = obtener_hoja()
    _preparar_ws(sh, HOJA_PROVEEDORES, PROVEEDORES_HEADERS, filas=500)
    _preparar_ws(sh, HOJA_CLIENTES, CLIENTES_HEADERS, filas=500)
    _preparar_ws(sh, HOJA_VENTAS, VENTAS_HEADERS)
    return sh


def obtener_o_crear_hoja_mes(nombre_mes: str):
    sh = obtener_o_crear_hoja_base()
    _preparar_ws(sh, f"{nombre_mes}{SUFIJO_COMPRAS}", COMPRAS_HEADERS, permitir_rebuild=False)
    return sh


def mapear_extraccion(datos: dict, proveedor: str, estado_pago: str = "PENDIENTE") -> dict:
    registro = {h: "" for h in COMPRAS_HEADERS}
    registro.update(
        {
            "Nombre_Archivo": datos.get("nombre_archivo", ""),
            "Proveedor_Asignado": proveedor,
            "NIT_Emisor": datos.get("nit_emisor") or "",
            "Razon_Social": datos.get("razon_social") or "",
            "Razon_Social_Cliente": datos.get("razon_social_cliente") or datos.get("Razon_Social_Cliente") or "",
            "Nro_Factura": datos.get("nro_factura") or "",
            "Cod_Autorizacion": datos.get("cod_autorizacion") or "",
            "Fecha_Emision": datos.get("fecha_emision") or "",
            "Subtotal_Neto": _a_float(datos.get("subtotal_neto") or 0.0),
            "Monto_Total": _a_float(datos.get("monto_total") or 0.0),
            "Credito_Fiscal": _a_float(datos.get("credito_fiscal") or 0.0),
            "NIT_Cliente": datos.get("nit_cliente") or "",
            "Estado_Pago": estado_pago,
            "Observaciones": datos.get("observaciones") or "",
            "Venta_ID": "",
        }
    )
    return registro


def _fila_de_registro(registro: dict) -> list:
    fila = []
    for h in COMPRAS_HEADERS:
        valor = registro.get(h, "")
        if h in CAMPOS_MONTO:
            fila.append(_a_float(valor))
        elif valor is None or (isinstance(valor, float) and valor != valor):
            fila.append("")
        else:
            fila.append(str(valor))
    return fila


def _registro_de_fila(valores: list) -> dict:
    registro = {}
    for i, h in enumerate(COMPRAS_HEADERS):
        v = valores[i] if i < len(valores) else ""
        registro[h] = _a_float(v) if h in CAMPOS_MONTO else ("" if v is None else str(v))
    return registro


def registrar_facturas_batch(nombre_mes: str, registros: list) -> int:
    sh = obtener_o_crear_hoja_mes(nombre_mes)
    ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    filas = []
    for r in registros:
        r = dict(r)
        if not r.get("ID"):
            r["ID"] = str(uuid.uuid4())[:8]
        if not r.get("Estado_Pago"):
            r["Estado_Pago"] = "PENDIENTE"
        filas.append(_fila_de_registro(r))
    if filas:
        ws.append_rows(filas)
    return len(filas)


def leer_facturas_mes(nombre_mes: str) -> list:
    sh = obtener_hoja()
    try:
        ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    except gspread.WorksheetNotFound:
        return []
    return [_registro_de_fila(f) for f in ws.get_all_values()[1:] if any(str(c).strip() for c in f)]


def leer_todas_compras() -> list:
    sh = obtener_hoja()
    resultados = []
    for ws in sh.worksheets():
        if ws.title.endswith(SUFIJO_COMPRAS):
            mes = ws.title[: -len(SUFIJO_COMPRAS)]
            for f in ws.get_all_values()[1:]:
                if any(str(c).strip() for c in f):
                    registro = _registro_de_fila(f)
                    registro["Mes"] = mes
                    resultados.append(registro)
    return resultados


def _indice_fila_por_id(ws, id_busqueda: str):
    ids = ws.col_values(1)
    for i, valor in enumerate(ids):
        if str(valor).strip() == str(id_busqueda).strip():
            return i + 1
    return None


def actualizar_factura(nombre_mes: str, registro: dict) -> bool:
    sh = obtener_o_crear_hoja_mes(nombre_mes)
    ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    fila = _indice_fila_por_id(ws, registro.get("ID", ""))
    if fila is None:
        return False
    ws.update(values=[_fila_de_registro(registro)], range_name=f"A{fila}:{rowcol_to_a1(fila, len(COMPRAS_HEADERS))}")
    return True


def eliminar_factura(nombre_mes: str, id_factura: str) -> bool:
    sh = obtener_hoja()
    try:
        ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    except gspread.WorksheetNotFound:
        return False
    fila = _indice_fila_por_id(ws, id_factura)
    if fila is None:
        return False
    ws.delete_rows(fila)
    return True


def leer_claves_existentes(nombre_mes: str) -> set:
    claves = set()
    for r in leer_facturas_mes(nombre_mes):
        claves.add(
            (
                str(r.get("NIT_Emisor", "")).strip().upper(),
                str(r.get("Nro_Factura", "")).strip().upper(),
                str(r.get("Cod_Autorizacion", "")).strip().upper(),
            )
        )
    return claves


def vincular_facturas(nombre_mes: str, venta_id: str, ids_facturas: list) -> int:
    sh = obtener_o_crear_hoja_mes(nombre_mes)
    ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    ids = ws.col_values(1)
    objetivos = {str(i).strip() for i in ids_facturas}
    updates = []
    for i, valor in enumerate(ids[1:], start=2):
        if str(valor).strip() in objetivos:
            updates.append({"range": f"{rowcol_to_a1(i, len(COMPRAS_HEADERS))}", "values": [[venta_id]]})
    if updates:
        ws.batch_update(updates)
    return len(updates)


def desvincular_facturas(nombre_mes: str, venta_id: str) -> int:
    sh = obtener_hoja()
    try:
        ws = sh.worksheet(f"{nombre_mes}{SUFIJO_COMPRAS}")
    except gspread.WorksheetNotFound:
        return 0
    ids = ws.col_values(1)
    col_venta = ws.col_values(len(COMPRAS_HEADERS))
    updates = []
    for i in range(1, len(ids)):
        venta_actual = col_venta[i] if i < len(col_venta) else ""
        if str(venta_actual).strip() == str(venta_id).strip():
            updates.append({"range": f"{rowcol_to_a1(i + 1, len(COMPRAS_HEADERS))}", "values": [[""]]})
    if updates:
        ws.batch_update(updates)
    return len(updates)


def leer_proveedores() -> list:
    try:
        sh = obtener_hoja()
        ws = sh.worksheet(HOJA_PROVEEDORES)
        registros = ws.get_all_records()
        nombres = [
            str(r.get("Nombre_Proveedor", "")).strip()
            for r in registros
            if str(r.get("Nombre_Proveedor", "")).strip()
        ]
        return nombres or ["Sin Asignar"]
    except Exception:
        return ["Sin Asignar"]


def leer_proveedores_full() -> list:
    sh = obtener_hoja()
    ws = sh.worksheet(HOJA_PROVEEDORES)
    out = []
    for f in ws.get_all_values()[1:]:
        if any(str(c).strip() for c in f):
            out.append(
                {
                    "NIT": f[0] if len(f) > 0 else "",
                    "Nombre_Proveedor": f[1] if len(f) > 1 else "",
                    "Telefono": f[2] if len(f) > 2 else "",
                    "Comision_Pactada_Pct": _a_float(f[3] if len(f) > 3 else 0.0),
                }
            )
    return out


def agregar_proveedor(nit: str, nombre: str, telefono: str, comision: float) -> None:
    sh = obtener_o_crear_hoja_base()
    ws = sh.worksheet(HOJA_PROVEEDORES)
    ws.append_row([str(nit).strip(), str(nombre).strip(), str(telefono).strip(), _a_float(comision)])


def eliminar_proveedor(nombre: str) -> bool:
    sh = obtener_hoja()
    ws = sh.worksheet(HOJA_PROVEEDORES)
    nombres = ws.col_values(2)
    for i, v in enumerate(nombres):
        if str(v).strip() == str(nombre).strip() and i > 0:
            ws.delete_rows(i + 1)
            return True
    return False


def leer_clientes() -> list:
    sh = obtener_o_crear_hoja_base()
    ws = sh.worksheet(HOJA_CLIENTES)
    out = []
    for f in ws.get_all_values()[1:]:
        if any(str(c).strip() for c in f):
            out.append(
                {
                    "ID_Cliente": f[0] if len(f) > 0 else "",
                    "Nombre_Razon_Social": f[1] if len(f) > 1 else "",
                    "NIT": f[2] if len(f) > 2 else "",
                    "Telefono": f[3] if len(f) > 3 else "",
                    "Notas": f[4] if len(f) > 4 else "",
                }
            )
    return out


def agregar_cliente(nombre: str, nit: str = "", telefono: str = "", notas: str = "") -> str:
    sh = obtener_o_crear_hoja_base()
    ws = sh.worksheet(HOJA_CLIENTES)
    id_cliente = str(uuid.uuid4())[:8]
    ws.append_row([id_cliente, str(nombre).strip(), str(nit).strip(), str(telefono).strip(), str(notas).strip()])
    return id_cliente


def eliminar_cliente(nombre: str) -> bool:
    sh = obtener_hoja()
    ws = sh.worksheet(HOJA_CLIENTES)
    nombres = ws.col_values(2)
    for i, v in enumerate(nombres):
        if str(v).strip() == str(nombre).strip() and i > 0:
            ws.delete_rows(i + 1)
            return True
    return False


def registrar_venta(
    nombre_mes: str,
    cliente: str,
    monto_credito: float,
    precio_cobrado: float,
    estado: str,
    facturas_ids: list = None,
    notas: str = "",
) -> str:
    sh = obtener_o_crear_hoja_base()
    ws = sh.worksheet(HOJA_VENTAS)
    id_venta = str(uuid.uuid4())[:8]
    ws.append_row(
        [
            id_venta,
            nombre_mes,
            str(cliente).strip(),
            _a_float(monto_credito),
            _a_float(precio_cobrado),
            estado,
            ",".join(str(i) for i in (facturas_ids or [])),
            str(notas).strip(),
        ]
    )
    if facturas_ids:
        vincular_facturas(nombre_mes, id_venta, facturas_ids)
    return id_venta


def leer_ventas_mes(nombre_mes: str) -> list:
    sh = obtener_hoja()
    try:
        ws = sh.worksheet(HOJA_VENTAS)
    except gspread.WorksheetNotFound:
        return []
    out = []
    for f in ws.get_all_values()[1:]:
        if any(str(c).strip() for c in f):
            out.append(
                {
                    "ID_Venta": f[0] if len(f) > 0 else "",
                    "Mes": f[1] if len(f) > 1 else "",
                    "Cliente_Razon_Social": f[2] if len(f) > 2 else "",
                    "Monto_Credito_Vendido": _a_float(f[3] if len(f) > 3 else 0.0),
                    "Precio_Cobrado": _a_float(f[4] if len(f) > 4 else 0.0),
                    "Estado_Cobro": f[5] if len(f) > 5 else "",
                    "Facturas_IDs": f[6] if len(f) > 6 else "",
                    "Notas": f[7] if len(f) > 7 else "",
                }
            )
    return [v for v in out if v["Mes"] == nombre_mes]


def actualizar_venta(nombre_mes: str, venta: dict) -> bool:
    sh = obtener_o_crear_hoja_base()
    ws = sh.worksheet(HOJA_VENTAS)
    fila = _indice_fila_por_id(ws, venta.get("ID_Venta", ""))
    if fila is None:
        return False
    valores = [
        venta.get("ID_Venta", ""),
        venta.get("Mes", nombre_mes),
        venta.get("Cliente_Razon_Social", ""),
        _a_float(venta.get("Monto_Credito_Vendido", 0.0)),
        _a_float(venta.get("Precio_Cobrado", 0.0)),
        venta.get("Estado_Cobro", "PENDIENTE"),
        venta.get("Facturas_IDs", ""),
        venta.get("Notas", ""),
    ]
    ws.update(values=[valores], range_name=f"A{fila}:{rowcol_to_a1(fila, len(VENTAS_HEADERS))}")
    return True


def eliminar_venta(venta: dict) -> bool:
    sh = obtener_hoja()
    try:
        ws = sh.worksheet(HOJA_VENTAS)
    except gspread.WorksheetNotFound:
        return False
    id_venta = venta.get("ID_Venta", "")
    fila = _indice_fila_por_id(ws, id_venta)
    if fila is None:
        return False
    if venta.get("Facturas_IDs"):
        desvincular_facturas(venta.get("Mes", ""), id_venta)
    ws.delete_rows(fila)
    return True
