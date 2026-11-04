import os
from typing import Optional, List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


def _env(clave: str, por_defecto: str = "") -> str:
    valor = os.getenv(clave)
    if valor:
        return valor
    try:
        import streamlit as st

        if clave in st.secrets:
            return str(st.secrets[clave])
    except Exception:
        pass
    return por_defecto


GEMINI_API_KEY = _env("GEMINI_API_KEY")
GOOGLE_SHEET_MASTER_ID = _env("GOOGLE_SHEET_MASTER_ID")
SERVICE_ACCOUNT_FILE = _env("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
MODEL_NAME = _env("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS = [
    m.strip()
    for m in _env("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-2.0-flash").split(",")
    if m.strip()
]
MAX_RETRIES = int(_env("GEMINI_MAX_RETRIES", "3"))
GEMINI_TIMEOUT_SEG = int(_env("GEMINI_TIMEOUT_SEG", "120"))
BACKOFF_BASE_SEG = 3
MAX_FILE_MB = 10
MAX_PDF_PAGES = 3
PDF_RENDER_DPI = int(_env("PDF_RENDER_DPI", "200"))
UMBRAL_TEXTO_NATIVO = int(_env("UMBRAL_TEXTO_NATIVO", "60"))
MAX_WORKERS = int(_env("MAX_WORKERS", "4"))
RUTA_DB = _env("RUTA_DB", "facturas.db")
CARPETA_EXPORTS = _env("CARPETA_EXPORTS", "exports")
CARPETA_ARCHIVOS = _env("CARPETA_ARCHIVOS", "archivos")
CARPETA_RESPALDOS = _env("CARPETA_RESPALDOS", "backups")
RETENCION_RESPALDOS = int(_env("RETENCION_RESPALDOS", "30"))
APP_PASSWORD = _env("APP_PASSWORD")
SESION_HORAS = float(_env("SESION_HORAS", "12"))
MAX_INTENTOS_LOGIN = int(_env("MAX_INTENTOS_LOGIN", "10"))
PRECIO_IA_ENTRADA = float(_env("PRECIO_IA_ENTRADA", "0.30"))
PRECIO_IA_SALIDA = float(_env("PRECIO_IA_SALIDA", "2.50"))
BILLING_ACTIVO = _env("BILLING_ACTIVO", "0").lower() in ("1", "true", "si", "sí")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HOJA_PROVEEDORES = "PROVEEDORES"
HOJA_VENTAS = "CLIENTES_VENTAS"
HOJA_CLIENTES = "CLIENTES"
SUFIJO_COMPRAS = "_COMPRAS"

COMPRAS_HEADERS = [
    "ID",
    "Nombre_Archivo",
    "Proveedor_Asignado",
    "NIT_Emisor",
    "Razon_Social",
    "Razon_Social_Cliente",
    "Nro_Factura",
    "Cod_Autorizacion",
    "Fecha_Emision",
    "Subtotal_Neto",
    "Monto_Total",
    "Credito_Fiscal",
    "Porcentaje_Compra",
    "NIT_Cliente",
    "Estado_Pago",
    "Observaciones",
    "Venta_ID",
    "Ruta_Archivo",
]

PROVEEDORES_HEADERS = ["NIT", "Nombre_Proveedor", "Telefono", "Comision_Pactada_Pct"]

CLIENTES_HEADERS = ["ID_Cliente", "Nombre_Razon_Social", "NIT", "Telefono", "Notas"]

VENTAS_HEADERS = [
    "ID_Venta",
    "Mes",
    "Cliente_Razon_Social",
    "Monto_Credito_Vendido",
    "Precio_Cobrado",
    "Estado_Cobro",
    "Facturas_IDs",
    "Notas",
]

ESTADOS_PAGO = ["PENDIENTE", "PAGADO"]
ESTADOS_COBRO = ["PENDIENTE", "PARCIAL", "COBRADO"]
