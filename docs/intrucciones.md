# ESPECIFICACIÓN TÉCNICA: SISTEMA DE OCR Y GESTIÓN FISCAL

## 1. Visión General del Proyecto
Desarrollar una aplicación web ligera y 100% modular en Python utilizando **Streamlit**, el SDK de **Gemini** y **Google Sheets** (`gspread`). 
El sistema automatiza el registro de facturas para compra y venta de crédito fiscal, permitiendo subir múltiples fotos/PDFs, extraer datos con IA estructurada, validarlos en una tabla editable en pantalla y guardarlos en una hoja de Google Sheets. NO se almacenan imágenes en servidores para ahorrar costos; solo se procesan en memoria y se extraen los datos.

---

## 2. Estructura del Proyecto

Crea una carpeta llamada `facturador-ocr` y dentro crea exactamente estos archivos:

```text
facturador-ocr/
├── .env
├── requirements.txt
├── service_account.json
├── config.py
├── sheets_manager.py
├── extractor.py
└── app.py
```

---

## 3. Archivo: `.env`
Contiene las variables de entorno privadas. (Reemplaza con tus datos reales).

```ini
GEMINI_API_KEY=tu_api_key_de_google_ai_studio_aqui
GOOGLE_SHEET_MASTER_ID=el_id_de_tu_google_sheet_aqui
GEMINI_MODEL=gemini-2.5-flash
```

---

## 4. Archivo: `requirements.txt`
Lista de dependencias necesarias.

```text
streamlit>=1.35.0
google-genai>=0.1.1
gspread>=6.1.0
google-auth>=2.29.0
pillow>=10.3.0
pydantic>=2.7.0
python-dotenv>=1.0.1
pandas>=2.2.0
pdf2image>=1.17.0
pypdf>=4.2.0
```

---

## 5. Archivo: `config.py`
Configuraciones centrales y el esquema de IA para extraer exactamente lo que necesitamos.

```python
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_MASTER_ID = os.getenv("GOOGLE_SHEET_MASTER_ID")
SERVICE_ACCOUNT_FILE = "service_account.json"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Esquema de extracción Pydantic
class FacturaExtraida(BaseModel):
    nit_emisor: Optional[str] = Field(None, description="NIT o RUC del emisor de la factura")
    razon_social: Optional[str] = Field(None, description="Nombre o razón social del emisor")
    nro_factura: Optional[str] = Field(None, description="Número correlativo de la factura")
    cod_autorizacion: Optional[str] = Field(None, description="Código de autorización o CUF")
    fecha_emision: Optional[str] = Field(None, description="Fecha de emisión en formato YYYY-MM-DD")
    monto_total: float = Field(0.0, description="Importe total a pagar")
    credito_fiscal: float = Field(0.0, description="Base imponible válida para crédito fiscal")
    observaciones: Optional[str] = Field(None, description="Notas relevantes o irregularidades detectadas")

PROMPT_SISTEMA = """
Eres un asistente tributario y contable de alta precisión. 
Analiza la imagen o PDF de la factura adjunta y extrae exclusivamente los campos requeridos en el esquema.
Si un dato no es legible o no existe, usa null o 0.0. No inventes información.
"""
```

---

## 6. Archivo: `extractor.py`
Se encarga de procesar las imágenes/PDFs y comunicarse con Gemini.

```python
import io
from PIL import Image
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, MODEL_NAME, PROMPT_SISTEMA, FacturaExtraida

client = genai.Client(api_key=GEMINI_API_KEY)

def procesar_archivo(file_bytes: bytes, filename: str) -> dict:
    """Convierte el archivo a imagen si es necesario y ejecuta el OCR con Gemini."""
    try:
        if filename.lower().endswith(".pdf"):
            import pdf2image
            images = pdf2image.convert_from_bytes(file_bytes, first_page=1, last_page=1)
            img = images[0]
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            img_bytes = buffer.getvalue()
            mime_type = "image/jpeg"
        else:
            img_bytes = file_bytes
            mime_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                PROMPT_SISTEMA
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FacturaExtraida,
                temperature=0.0,
            ),
        )
        
        datos = FacturaExtraida.model_validate_json(response.text).model_dump()
        datos["nombre_archivo"] = filename
        return datos

    except Exception as e:
        return {
            "nombre_archivo": filename,
            "nit_emisor": "ERROR",
            "razon_social": f"Error: {str(e)}",
            "nro_factura": "",
            "cod_autorizacion": "",
            "fecha_emision": "",
            "monto_total": 0.0,
            "credito_fiscal": 0.0,
            "observaciones": str(e)
        }
```

---

## 7. Archivo: `sheets_manager.py`
Se conecta a Google Sheets para guardar la información y crear las hojas automáticamente si no existen.

```python
import gspread
from google.oauth2.service_account import Credentials
from config import SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_MASTER_ID
import uuid

SCOPES = [
    "[https://www.googleapis.com/auth/spreadsheets](https://www.googleapis.com/auth/spreadsheets)",
    "[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive)"
]

def obtener_cliente():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def obtener_o_crear_hoja_mes(nombre_mes: str):
    gc = obtener_cliente()
    sh = gc.open_by_key(GOOGLE_SHEET_MASTER_ID)
    hojas_existentes = [ws.title for ws in sh.worksheets()]
    
    tab_compras = f"{nombre_mes}_COMPRAS"
    if tab_compras not in hojas_existentes:
        ws = sh.add_worksheet(title=tab_compras, rows=1000, cols=12)
        ws.append_row([
            "ID", "Nombre_Archivo", "Proveedor_Asignado", "NIT_Emisor", 
            "Razon_Social", "Nro_Factura", "Cod_Autorizacion", 
            "Fecha_Emision", "Monto_Total", "Credito_Fiscal", "Estado_Pago", "Observaciones"
        ])
    
    if "PROVEEDORES" not in hojas_existentes:
        ws_prov = sh.add_worksheet(title="PROVEEDORES", rows=500, cols=4)
        ws_prov.append_row(["NIT", "Nombre_Proveedor", "Telefono", "Comision_Pactada_Pct"])

    if "CLIENTES_VENTAS" not in hojas_existentes:
        ws_ventas = sh.add_worksheet(title="CLIENTES_VENTAS", rows=1000, cols=7)
        ws_ventas.append_row(["ID_Venta", "Mes", "Cliente_Razon_Social", "Monto_Credito_Vendido", "Precio_Cobrado", "Estado_Cobro", "Notas"])

    return sh

def registrar_facturas_batch(nombre_mes: str, proveedor: str, lista_facturas: list):
    sh = obtener_o_crear_hoja_mes(nombre_mes)
    ws = sh.worksheet(f"{nombre_mes}_COMPRAS")
    filas = []
    for f in lista_facturas:
        filas.append([
            str(uuid.uuid4())[:8],
            f.get("nombre_archivo", ""),
            proveedor,
            f.get("nit_emisor", ""),
            f.get("razon_social", ""),
            f.get("nro_factura", ""),
            f.get("cod_autorizacion", ""),
            f.get("fecha_emision", ""),
            f.get("monto_total", 0.0),
            f.get("credito_fiscal", 0.0),
            "PENDIENTE",
            f.get("observaciones", "")
        ])
    ws.append_rows(filas)

def leer_proveedores():
    try:
        gc = obtener_cliente()
        sh = gc.open_by_key(GOOGLE_SHEET_MASTER_ID)
        ws = sh.worksheet("PROVEEDORES")
        records = ws.get_all_records()
        return [str(r["Nombre_Proveedor"]) for r in records if "Nombre_Proveedor" in r and str(r["Nombre_Proveedor"]).strip()]
    except Exception:
        return ["Sin Asignar"]
```

---

## 8. Archivo: `app.py`
La interfaz gráfica visual que verá el cliente.

```python
import streamlit as st
import pandas as pd
import uuid
from extractor import procesar_archivo
from sheets_manager import (
    obtener_o_crear_hoja_mes, 
    registrar_facturas_batch, 
    leer_proveedores, 
    obtener_cliente
)
from config import GOOGLE_SHEET_MASTER_ID

st.set_page_config(page_title="Gestor Fiscal OCR", layout="wide", page_icon="📑")
st.title("📑 Sistema de Control Fiscal y Facturación")

with st.sidebar:
    st.header("⚙️ Configuración")
    mes_seleccionado = st.selectbox(
        "Mes de Operación:", 
        ["2026_09_Septiembre", "2026_10_Octubre", "2026_11_Noviembre", "2026_12_Diciembre"]
    )
    lista_proveedores = leer_proveedores()
    if not lista_proveedores:
        lista_proveedores = ["Sin Asignar"]
    proveedor_actual = st.selectbox("Distribuidor actual:", lista_proveedores)
    st.caption("Los datos se guardan directamente en Google Sheets.")

tab_ingesta, tab_proveedores, tab_ventas, tab_balance = st.tabs([
    "📥 Carga de Facturas", 
    "👥 Distribuidores", 
    "💼 Ventas y Cobros", 
    "📊 Estado de Cuenta"
])

with tab_ingesta:
    st.subheader(f"Extracción de Datos - {mes_seleccionado}")
    archivos = st.file_uploader(
        "Arrastra imágenes o PDFs de facturas aquí", 
        accept_multiple_files=True, 
        type=["jpg", "jpeg", "png", "pdf"]
    )

    if archivos and st.button("🚀 Extraer Datos con IA"):
        resultados = []
        progress_bar = st.progress(0)
        for idx, arch in enumerate(archivos):
            res = procesar_archivo(arch.read(), arch.name)
            resultados.append(res)
            progress_bar.progress((idx + 1) / len(archivos))
        
        st.session_state["facturas_procesadas"] = resultados
        st.success("Extracción completada. Puedes editar los datos en la tabla de abajo antes de guardarlos.")

    if "facturas_procesadas" in st.session_state and st.session_state["facturas_procesadas"]:
        df_editor = pd.DataFrame(st.session_state["facturas_procesadas"])
        df_modificado = st.data_editor(df_editor, use_container_width=True, num_rows="dynamic")

        if st.button("💾 Guardar en Google Sheets"):
            with st.spinner("Sincronizando..."):
                datos_finales = df_modificado.to_dict(orient="records")
                registrar_facturas_batch(mes_seleccionado, proveedor_actual, datos_finales)
                st.session_state["facturas_procesadas"] = []
                st.success("¡Datos guardados exitosamente!")
                st.rerun()

with tab_proveedores:
    st.subheader("Registrar Nuevo Proveedor")
    with st.form("nuevo_prov"):
        c1, c2, c3 = st.columns(3)
        nit = c1.text_input("NIT:")
        nombre = c2.text_input("Razón Social:")
        comision = c3.number_input("Comisión (%):", min_value=0.0)
        if st.form_submit_button("Guardar"):
            gc = obtener_cliente()
            sh = gc.open_by_key(GOOGLE_SHEET_MASTER_ID)
            ws = sh.worksheet("PROVEEDORES")
            ws.append_row([nit, nombre, "", comision])
            st.success("Guardado.")
            st.rerun()

with tab_ventas:
    st.subheader("Registrar Venta de Crédito Fiscal")
    with st.form("nueva_venta"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente:")
        monto_credito = c2.number_input("Crédito Vendido:", min_value=0.0)
        c3, c4 = st.columns(2)
        precio_cobrado = c3.number_input("Monto a Cobrar:", min_value=0.0)
        estado = c4.selectbox("Estado:", ["PENDIENTE", "COBRADO"])
        if st.form_submit_button("Registrar Venta"):
            gc = obtener_cliente()
            sh = gc.open_by_key(GOOGLE_SHEET_MASTER_ID)
            ws = sh.worksheet("CLIENTES_VENTAS")
            ws.append_row([str(uuid.uuid4())[:8], mes_seleccionado, cliente, monto_credito, precio_cobrado, estado, ""])
            st.success("Venta registrada.")

with tab_balance:
    st.subheader(f"Balance de {mes_seleccionado}")
    if st.button("🔄 Actualizar Balance"):
        try:
            gc = obtener_cliente()
            sh = gc.open_by_key(GOOGLE_SHEET_MASTER_ID)
            ws_c = sh.worksheet(f"{mes_seleccionado}_COMPRAS")
            df_c = pd.DataFrame(ws_c.get_all_records())
            
            total_facturas = df_c["Monto_Total"].replace('[\$,]', '', regex=True).astype(float).sum() if not df_c.empty else 0.0
            
            st.metric("Total Compras Registradas", f"{total_facturas:,.2f}")
            st.dataframe(df_c, use_container_width=True)
        except Exception as e:
            st.info("Aún no hay facturas registradas en este mes.")
```

---

## 9. Instrucciones de Despliegue Local para el Agente

1. Crea la carpeta y pega todos los archivos de arriba.
2. Abre tu terminal y crea un entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows usa: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Consigue tu archivo de credenciales de Google Cloud (`service_account.json`) y ponlo en la carpeta raíz.
4. Entra a tu Google Drive, crea un Google Sheet en blanco, cópiale el ID de la URL y ponlo en `.env`.
5. Comparte ese Google Sheet (botón "Compartir" arriba a la derecha) con el correo electrónico que viene dentro de tu `service_account.json`, dándole permisos de **Editor**.
6. Inicia la aplicación:
   ```bash
   streamlit run app.py
   ```