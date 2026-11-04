# PLAN: Facturador OCR — Sistema de Compra/Venta de Crédito Fiscal

## 1. Objetivo del sistema
Aplicación web ligera (Streamlit) de usuario único que automatiza el registro de facturas para **compra de crédito fiscal** a distribuidores y su **reventa** a clientes:
1. Subir múltiples fotos/PDFs de facturas.
2. Extracción de datos con IA (Gemini multimodal) usando esquema estructurado.
3. Validación/edición en pantalla (tabla editable) con detección de duplicados.
4. Guardado en Google Sheets (maestro) con tabs por mes.
5. Gestión posterior: CRUD de facturas, registro de ventas/cobros y balance mensual.

No se almacenan imágenes: todo se procesa en memoria.

## 2. Decisiones confirmadas
| # | Tema | Decisión |
|---|------|----------|
| 1 | Motor OCR | **Híbrido**: SDK `google-genai` con `response_schema` (salida JSON nativa) + reintentos con backoff y cadena de modelos fallback (herencia de InvoiceParser-AI) |
| 2 | Campos extraídos | Spec (8 campos) + `subtotal_neto` + `nit_cliente` (si aparece) |
| 3 | Balance | Completo: compras, crédito comprado/vendido/disponible, cobros pendientes, ganancia |
| 4 | Gestión post-guardado | CRUD completo de facturas guardadas (editar, Estado_Pago, eliminar) |
| 5 | Duplicados | Avisar (marcar en rojo) y permitir decidir antes de guardar |
| 6 | API key | Usar la del proyecto InvoiceParser-AI (⚠️ verificar formato; si es inválida, crear una nueva en AI Studio `AIza...`) |
| 7 | Ventas | Montos agregados (cliente + crédito vendido + precio cobrado), sin vincular facturas individuales |
| 8 | PDFs multipágina | Hasta 3 páginas (render 200 DPI, como el referencia) |
| 9 | Proveedor | Valor inicial del sidebar + columna editable por fila |
| 10 | Despliegue | **Híbrido**: local ahora (`streamlit run app.py`), preparado para servidor después (toda configuración por variables de entorno / secrets, cero cambios de código) |

## 3. Estructura del proyecto
```text
facturador-ocr/
├── .env                  # GEMINI_API_KEY, GOOGLE_SHEET_MASTER_ID, GEMINI_MODEL, GEMINI_FALLBACK_MODELS
├── requirements.txt
├── service_account.json  # credenciales Google (no versionar)
├── config.py             # settings + esquema Pydantic + prompt
├── extractor.py          # motor OCR (adaptado de InvoiceParser-AI)
├── sheets_manager.py     # capa Google Sheets (CRUD + agregados)
├── app.py                # UI Streamlit
├── README.md             # uso + despliegue local/servidor
└── docs/
    └── plan.md           # este documento
```

## 4. Qué se importa de InvoiceParser-AI (H:\2Proyectos Ricardo\InvoiceParser-AI)
| Fuente | Qué tomar | Adaptación |
|--------|-----------|------------|
| `utils/llm_utils.py` | Cliente LLM vía endpoint compatible (solo referencia de fallbacks) | Se reemplaza por `google.genai.Client` nativo |
| `nodes/llm.py` | Backoff lineal (3s/6s/9s) + cadena de modelos fallback (3 intentos/modelo) para errores 429/503/overload | Integrar con SDK nativo |
| `nodes/ingestion.py` | Validación de archivos con magic bytes (JPEG `\xff\xd8\xff`, PNG, `%PDF`), límite de tamaño | Simplificado dentro de `extractor.py` |
| `nodes/extraction.py` + `utils/pdf_utils.py` | Detección PDF texto nativo vs escaneado; render PyMuPDF→PNG 200 DPI, máx 3 páginas | Importar lógica; en PDF con texto nativo enviar el archivo directo a Gemini (también lee PDFs) |
| `models/prompts.py` | Estilo de prompt estricto (solo JSON, no inventar, null si falta) | Reescribir para contexto fiscal (NIT, crédito fiscal) — el original es Perú (RUC, IGV, detracción) |

## 5. Esquema de extracción (Pydantic en `config.py`)
```python
class FacturaExtraida(BaseModel):
    nit_emisor: Optional[str]          # NIT o RUC del emisor
    razon_social: Optional[str]        # nombre del emisor
    nro_factura: Optional[str]
    cod_autorizacion: Optional[str]    # CUF / código de autorización
    fecha_emision: Optional[str]       # YYYY-MM-DD
    subtotal_neto: Optional[float]     # monto antes de crédito fiscal (si figura)
    monto_total: float = 0.0
    credito_fiscal: float = 0.0        # base imponible para crédito fiscal
    nit_cliente: Optional[str]         # si aparece en la factura
    observaciones: Optional[str]       # irregularidades, ilegible, etc.
```
Prompt: asistente tributario de alta precisión; null/0.0 si falta; no inventar; temperature=0; `response_schema` nativo del SDK.

Modelos (configurables por .env):
- Principal: `gemini-2.5-flash` (según spec)
- Fallbacks: lista del `.env` (inicialmente `gemini-flash-latest`, `gemini-3.5-flash-lite`)

## 6. Modelo de datos Google Sheets (maestro)
- **`{MES}_COMPRAS`** (ej. `2026_09_Septiembre_COMPRAS`):
  `ID | Nombre_Archivo | Proveedor_Asignado | NIT_Emisor | Razon_Social | Nro_Factura | Cod_Autorizacion | Fecha_Emision | Subtotal_Neto | Monto_Total | Credito_Fiscal | NIT_Cliente | Estado_Pago | Observaciones`
- **`PROVEEDORES`**: `NIT | Nombre_Proveedor | Telefono | Comision_Pactada_Pct`
- **`CLIENTES_VENTAS`**: `ID_Venta | Mes | Cliente_Razon_Social | Monto_Credito_Vendido | Precio_Cobrado | Estado_Cobro | Notas`
- ID corto `uuid4()[:8]` por registro (necesario para CRUD).
- Creación automática de tabs si no existen. Corregir el bug de la spec: scopes con URLs duplicadas `[url](url)`.

## 7. UI (`app.py`) — pestañas
1. **📥 Carga de Facturas**: uploader múltiple (jpg/jpeg/png/pdf) → extracción con barra de progreso → tabla editable (incluye `Proveedor_Asignado` precargado del sidebar y `Estado_Pago=PENDIENTE`) → detección de duplicados contra el mes (filas marcadas en rojo + decisión de incluir/omitir) → guardar batch en Sheets.
2. **🗂 Facturas Guardadas**: tabla del mes seleccionado; editar celdas, cambiar `Estado_Pago` (PENDIENTE/PAGADO), eliminar registros (por ID).
3. **👥 Distribuidores**: alta/edición/baja en `PROVEEDORES`.
4. **💼 Ventas y Cobros**: registrar venta (cliente, crédito vendido, precio cobrado, estado), cambiar `Estado_Cobro` (PENDIENTE/COBRADO).
5. **📊 Estado de Cuenta**: métricas del mes + anual:
   - N° facturas y total compras
   - Crédito fiscal comprado / vendido / **disponible** (comprado − vendido)
   - Cobrado vs pendiente de cobro
   - **Ganancia bruta** = Σ Precio_Cobrado − Σ Crédito_Vendido

## 8. Fases de implementación
| Fase | Contenido | Verificación |
|------|-----------|--------------|
| 0. Setup | venv Python 3.11+, `requirements.txt`, `.env` (key del referencia + Sheet ID), `service_account.json` | `pip install` OK; script de prueba de key y conexión a Sheets |
| 1. `config.py` | Settings desde env, esquema Pydantic, prompt | Validación de esquema con datos de ejemplo |
| 2. `extractor.py` | Motor OCR: magic bytes, PDF nativo vs escaneado, render 200 DPI ≤3 págs, llamada Gemini con schema + retries/fallback | Probar con 2-3 facturas reales (foto + PDF escaneado + PDF nativo) |
| 3. `sheets_manager.py` | Creación de tabs, guardado batch, CRUD por ID, proveedores, ventas, funciones de agregación | Script de prueba: crear tab, insertar, leer, actualizar, eliminar |
| 4. `app.py` | UI completa con las 5 pestañas y session_state correcto | Prueba manual end-to-end |
| 5. Cierre | Duplicados, pulido de balance, README (uso + despliegue local y servidor/secrets) | Flujo completo con facturas reales del cliente |

## 9. Riesgos y notas
- ⚠️ **API key del referencia**: formato `AQ.???` no es válido para Gemini (`AIza...`). Verificarla en Fase 0; si falla, pedir una nueva (2 min en AI Studio).
- El modelo `gemini-3.5-flash-lite` del referencia debe existir realmente; al ser configurable por `.env` se puede ajustar sin tocar código.
- Free tier de Gemini: los fallbacks + backoff mitigan saturación/cuota.
- `service_account.json` y `.env` nunca se suben a git (`.gitignore`).
- Despliegue híbrido: `config.py` leerá de `os.getenv` primero (compatible con Streamlit Cloud secrets / variables de servidor) y de `.env` como fallback local.
