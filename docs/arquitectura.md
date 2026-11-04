# ARQUITECTURA: Facturador OCR v3

## 1. Principios (skills aplicadas)
1. **Velocidad**: lecturas locales (SQLite, ms); OCR en background con cola; caché por hash.
2. **Capas con dependencias hacia abajo**: `webui/` (UI) → `ocr_queue` (servicio) → `db` (datos) → SQLite. La UI nunca toca SQL.
3. **Módulos profundos**: interfaz chica, implementación compleja oculta; `__all__` explícito; un concepto por archivo.
4. **Jobs**: máquina de estados (EN_COLA→PROCESANDO→OK/DUPLICADO/ERROR), idempotencia por hash, reintentos solo para errores transitorios (backoff), timeout por request.
5. **Seguridad**: validación en el borde (extensión + tamaño + magic bytes), SQL 100% parametrizado, password por `.env` con `secrets.compare_digest`, bloqueo por intentos, sesión con vencimiento, cabeceras de seguridad, salida del LLM validada contra esquema Pydantic (nunca confiable).

## 2. Estructura en capas
```text
webui/                 # CAPA UI (NiceGUI)
  main.py              # arranque + middleware cabeceras + backup programado
  plantilla.py         # guard de sesión, login, header/drawer (decorador @pagina)
  componentes.py       # widgets reutilizables
  pag_*.py             # una página por archivo (dashboard, carga, facturas,
                       #  ventas, maestros, campos, ajustes)
ocr_queue.py           # CAPA SERVICIO: ColaOCR (thread pool global, estados)
extractor.py           # CAPA SERVICIO: OCR Gemini dual (texto/visión) + caché
campos.py              # esquema IA dinámico (create_model) + prompt
exportador.py          # Excel por mes/proveedor
respaldos.py           # backups consistentes (API SQLite) + retención 30
db.py                  # CAPA DATOS: única fuente de verdad (SQLite WAL)
config.py              # settings por variables de entorno (12-factor)
facturas.db            # la base (respaldar)
```

## 3. Flujo de carga (el corazón)
1. Usuario elige mes+proveedor, arrastra N archivos → validación de borde (ext/tamaño).
2. `COLA.agregar_lote()` devuelve al instante; cada archivo va a un ThreadPool global.
3. Por archivo: hash → ¿caché? → sí: instantáneo. No: PDF con texto nativo → texto a Gemini; si no → render 200 DPI + visión.
4. Respuesta validada con esquema dinámico → dedup global → auto-guardado con estado.
5. UI sondea la cola cada 2 s; duplicados/errores esperan acción (Guardar igual / Reintentar / Descartar).

## 4. Modelo de datos
| Tabla | Rol |
|---|---|
| `facturas` | núcleo en columnas + `extra` JSON (campos configurables) |
| `proveedores`, `clientes` | maestros |
| `ventas`, `venta_facturas` | venta + relación N:M con facturas |
| `cobros` | pagos parciales; estado de venta derivado (PENDIENTE/PARCIAL/COBRADO) |
| `campos_config` | registro de campos (núcleo/activo/en_ia/orden) |
| `extraction_cache` | hash → resultado OCR (idempotencia) |

## 5. Escala y despliegue
- Volumen diseñado: 3-5k facturas/mes (~60k/año) — trivial para SQLite con índices; UI paginada.
- **Portable-first**: carpeta copiable; backup = copiar `facturas.db` (+ automáticos en `backups/`).
- Publicar: `APP_PASSWORD` + Cloudflare Tunnel (gratis, HTTPS) o VPS. MySQL/Postgres solo multiusuario: se reemplaza `db.py` manteniendo su interfaz.


## 2. Estructura
```text
├── app.py              # UI Streamlit (7 tabs)
├── db.py               # capa de datos SQLite (única fuente de verdad)
├── campos.py           # esquema IA dinámico + prompt según configuración de campos
├── extractor.py        # OCR Gemini (reintentos + fallback de modelos)
├── exportador.py       # Excel mensual con hoja por proveedor + resumen + ventas
├── migrar_sheets.py    # migración one-shot Google Sheets → SQLite
├── sheets_manager.py   # (histórico) capa Google Sheets, usada solo por la migración
├── config.py           # settings por variables de entorno
├── facturas.db         # LA BASE DE DATOS (respaldar este archivo)
├── exports/            # Excel generados
└── docs/
```

## 3. Modelo de datos (SQLite, modo WAL)
| Tabla | Contenido |
|---|---|
| `facturas` | columnas núcleo (id, mes, proveedor, nro_factura, cod_autorizacion, fecha, montos, estado_pago, venta_id...) + columna `extra` **JSON** para campos configurables |
| `proveedores` | id, nit, nombre (único), teléfono, comisión |
| `clientes` | id, nombre, nit, teléfono, notas |
| `ventas` | id, mes, cliente, crédito vendido, precio cobrado, estado cobro, notas |
| `venta_facturas` | relación N:M venta ↔ facturas (vinculación real, no strings) |
| `campos_config` | registro de campos: clave, etiqueta, tipo, descripción IA, núcleo, activo, en_ia, orden |

### ¿Por qué híbrido (columnas + JSON)?
- Lo **esencial** (lo que usa la lógica: montos, duplicados, estados, vínculos) va en **columnas**: indexable, rápido, consultable con SQL.
- Lo **configurable** va en **JSON** (`extra`): agregar/quitar campos no requiere ALTER TABLE ni migraciones.

## 4. Campos configurables (tab ⚙️)
- **Activo**: aparece/guarda en las tablas (desactivar NO borra historial).
- **Pedir a la IA**: se incluye en el esquema JSON estructurado y el prompt de Gemini (el esquema Pydantic se construye dinámicamente con `create_model`).
- **Núcleo**: campos del sistema protegidos (montos, factura, estados...) — no se pueden borrar.
- **Extras**: se crean al vuelo (ej. "Forma de Pago", "Placa", "N° Interno") y se almacenan en `extra`.

## 5. Flujo de la app
1. **📥 Carga**: subir fotos/PDFs → extracción **paralela** (hilos) → tabla editable con duplicados marcados → guardar.
2. **🗂 Facturas Guardadas**: CRUD completo + export Excel.
3. **👥 Proveedores / 🧑‍💼 Clientes**: maestros.
4. **💼 Ventas**: cliente + multiselección de facturas no vendidas → crédito sumado automáticamente → vínculo real en DB (eliminar venta libera facturas).
5. **📊 Estado de Cuenta**: métricas del mes con filtro por proveedor + acumulado anual + export.
6. **⚙️ Campos**: personalización del esquema.

## 6. Despliegue
- **Cualquier servidor** (Windows/Linux VPS/Docker): copiar carpeta + `venv` → `streamlit run app.py`. Backups = copiar `facturas.db` (y `.env`/`service_account.json`).
- **Streamlit Community Cloud**: el disco es efímero — ahí sí conviene apuntar `RUTA_DB` a un volumen persistente o migrar la capa a Postgres (solo se reemplaza `db.py`).
- MySQL/Postgres: solo cuando haya **multiusuario concurrente**. La interfaz de `db.py` está diseñada para ese salto.

## 7. Google (Gemini) vs Datos
- **Gemini** solo para OCR: API key en `.env`, sin dependencia para operar la base.
- El Google Sheet viejo queda como **respaldo histórico**; `migrar_sheets.py` es idempotente (INSERT OR IGNORE).
