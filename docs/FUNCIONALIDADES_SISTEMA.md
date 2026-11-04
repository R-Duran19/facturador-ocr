# Sistema de Gestión Fiscal y OCR — Funcionalidades y Roadmap

**Documento funcional y técnico**
**Versión:** 1.0
**Fecha:** octubre 2026
**Alcance:** sistema actual (interfaz NiceGUI + SQLite + Gemini) y evolución propuesta.
**Uso:** base para documentación de producto, presentación al cliente y planificación de nuevas fases.

---

## 1. Resumen ejecutivo

El sistema automatiza el ciclo de **compra y venta de crédito fiscal**:

1. Se reciben facturas en imagen o PDF.
2. La IA (Google Gemini) extrae los datos fiscales.
3. Las facturas se guardan en una base local (SQLite) asociadas a un mes y a un proveedor-persona.
4. Con esas facturas se crean **ventas** al cliente (la empresa emisora de la factura), aplicando un porcentaje de venta.
5. Se registran **cobros** de clientes (totales o parciales) y **pagos** a proveedores.
6. Se generan reportes de costos, utilidad, cobranza y pagos en pantalla, Excel y PDF.

Es una aplicación **de un solo usuario**, pensada para ejecutarse en una PC local o en un servidor pequeño, con todos los datos en un archivo `facturas.db` y los archivos originales en la carpeta `archivos/`.

**Estado general:** el núcleo operativo está implementado y en uso. Faltan módulos de notificaciones, API externa, usuarios/roles, auditoría, vencimientos de cobro y varias mejoras de IA y reportería.

---

## 2. Propósito y alcance

### 2.1 Qué resuelve hoy

- Digitalizar facturas sin cargar datos a mano.
- Evitar duplicados y errores de tipeo.
- Saber cuánto se compró, cuánto se vendió y cuánta utilidad hay por mes.
- Saber cuánto se debe pagar a cada proveedor-persona.
- Saber cuánto se debe cobrar a cada empresa cliente.
- Exportar la información en formatos que el negocio ya usa (Excel y PDF).

### 2.2 Qué no resuelve todavía

- No emite facturas ni se conecta con el sistema tributario (SIN).
- No envía notificaciones ni recordatorios automáticos.
- No tiene API para integrarse con otros sistemas.
- No maneja múltiples usuarios ni permisos.
- No controla fechas de vencimiento de cobros ni antigüedad de deuda.
- No administra stock, inventario ni contabilidad formal.

---

## 3. Arquitectura técnica

### 3.1 Stack

| Componente | Tecnología |
|---|---|
| Interfaz web | NiceGUI (Python) |
| Base de datos | SQLite en modo WAL (`facturas.db`) |
| OCR / IA | Google Gemini (`google-genai`) |
| Procesamiento PDF | PyMuPDF (`pymupdf`) |
| Imágenes | Pillow (`PIL`) |
| Excel | pandas + openpyxl |
| PDF de reportes | fpdf2 |
| Variables de entorno | python-dotenv |
| Interfaz legacy | Streamlit (`app.py`) |

### 3.2 Capas

```text
webui/                  Capa de interfaz (NiceGUI)
  main.py               Arranque, seguridad HTTP, backups programados
  plantilla.py          Login, sesión, encabezado, menú lateral
  componentes.py        Widgets reutilizables
  pag_*.py              Una página por módulo

ocr_queue.py            Servicio de cola OCR (hilos, estados, reintentos)
extractor.py            Motor OCR Gemini (texto/visión, caché, costos)
campos.py               Esquema dinámico de extracción y prompt

db.py                   Capa de datos (única fuente de verdad)
reportes.py             Cálculos de reportes
exportador.py           Excel mensual y Excel de control
pdf_reportes.py         PDF resumen y PDFs por empresa
archivos.py             Guardado de originales como PDF
respaldos.py            Backups de la base
config.py               Configuración por variables de entorno

facturas.db             Base de datos
archivos/               Originales guardados
exports/                Archivos generados
backups/                Copias de seguridad
```

### 3.3 Principios de diseño aplicados

- La interfaz no ejecuta SQL: siempre pasa por `db.py`.
- Los campos esenciales viven en columnas; los campos configurables en un JSON (`extra`), sin migraciones.
- El OCR corre en segundo plano con una cola multihilo.
- El LLM nunca se considera confiable: la respuesta se valida contra un esquema Pydantic.
- Todo el SQL es parametrizado.
- La configuración sensible va en `.env`.

### 3.4 Despliegue

- Local: `python -m webui.main` (puerto 8080 por defecto).
- Legacy: `streamlit run app.py` (puerto 8501).
- Para publicar: `APP_PASSWORD` + Cloudflare Tunnel o VPS con HTTPS.
- Portable: copiar la carpeta completa (o al menos `facturas.db`, `.env`, `service_account.json`, `archivos/`).

---

## 4. Conceptos del negocio

| Concepto | Significado en el sistema |
|---|---|
| Mes | Carpeta lógica con formato `AAAA_MM_Mes` (ej. `2026_09_Septiembre`). Agrupa facturas, ventas y pagos. |
| Proveedor | Persona que trae las facturas (Anahi, Gladys, Carmen, etc.). Tiene un % de compra pactado. |
| Cliente | Empresa a la que se le vende el crédito fiscal. Tiene un % de venta y un rubro. |
| Factura | Documento con NIT emisor, razón social, número, fecha, montos, crédito fiscal y % de compra. |
| Venta | Operación que agrupa una o varias facturas y define cuánto se le cobra al cliente. |
| Cobro | Pago (total o parcial) que el cliente hace sobre una venta. |
| Pago | Pago que el negocio hace al proveedor-persona por las facturas que trajo. |
| Utilidad | Diferencia entre lo que se cobra al cliente y lo que se paga al proveedor. |

### 4.1 Fórmulas principales

| Cálculo | Fórmula |
|---|---|
| A pagar al proveedor | `Σ (Monto_Total × Porcentaje_Compra / 100)` |
| A cobrar al cliente | `Monto_Total × Pct_Venta / 100` (o el precio editado en la venta) |
| Utilidad | `Venta − Compra` |
| Saldo de venta | `Precio_Cobrado − Σ cobros` |
| Saldo de proveedor | `A_Pagar − Σ pagos` |
| % compra ponderado | `Compra / Total_Facturado × 100` |
| % venta ponderado | `Venta / Total_Facturado × 100` |

### 4.2 Estados

| Entidad | Estados |
|---|---|
| Factura (`Estado_Pago`) | `PENDIENTE`, `PAGADO` (manual, por factura) |
| Venta (`Estado_Cobro`) | `PENDIENTE`, `PARCIAL`, `COBRADO` (derivado de los cobros) |
| Pago a proveedor | `PENDIENTE`, `PARCIAL`, `PAGADO` (derivado de los pagos) |
| Archivo en cola | `EN_COLA`, `PROCESANDO`, `OK`, `DUPLICADO`, `ERROR` |

> Nota: el `Estado_Pago` de la factura es un dato manual e independiente del estado de pagos al proveedor. El estado real de la deuda con el proveedor se calcula en `resumen_pagos_proveedores`.

---

## 5. Mapa de módulos

| Módulo | Ruta | Estado | Qué hace |
|---|---|---|---|
| Portada / Carga de facturas | `/` | Implementado | Subida múltiple por proveedor, OCR y cola en vivo |
| Gestión del mes | `/gestion` | Implementado | Explorador tipo carpeta: proveedores, ventas, reportes |
| Ventas y cobros | `/ventas` | Implementado | Cobros a clientes y pagos a proveedores |
| Buscar facturas | `/facturas` | Implementado | Búsqueda global, edición, carga manual, export |
| Pagos a proveedores | `/pagos` | Implementado (ruta secundaria) | Detalle y registro de pagos |
| Reportes del mes | `/reportes` | Implementado (ruta secundaria) | Reportes y exportaciones |
| Configuración | `/configuracion` | Implementado | Proveedores, clientes, campos y sistema |
| Login / sesión | — | Implementado (opcional) | Contraseña, bloqueo, vencimiento |
| Respaldos | — | Implementado | Backup de la base al iniciar y cada 24 h |
| Interfaz legacy Streamlit | `app.py` | Implementado (legacy) | Versión anterior con 7 pestañas |

> Las rutas `/pagos` y `/reportes` existen y funcionan, pero el menú lateral actual no las muestra: sus funciones están integradas dentro de Gestión del mes y Ventas y cobros. Conviene unificarlas o agregarlas al menú para evitar confusión.

---

## 6. Funcionalidades implementadas

### 6.1 Portada / Carga de facturas (`/`)

- Selector de **mes de trabajo** con opción de escribir un mes nuevo.
- Botón **Nuevo mes** con diálogo de año y mes; crea el mes al instante.
- Franja de métricas del mes: facturas, comprado, vendido, por cobrar y utilidad.
- Tarjeta de **gasto de IA** (hoy, mes, histórico) con aviso de billing activo/inactivo.
- Sección de ayuda "¿Cómo funciona?".
- **Espacios de carga por proveedor**:
  - Cada espacio tiene un proveedor y un `% compra` de solo lectura tomado de su ficha.
  - El `% compra` se actualiza en tiempo real al cambiar de proveedor.
  - Se pueden agregar y quitar espacios.
  - Cada espacio mantiene su propia cola local de archivos.
- **Carga de archivos**:
  - Múltiples archivos, arrastrar o hacer clic.
  - Acepta JPG, JPEG, PNG y PDF.
  - Límite de 10 MB por archivo.
  - Rechazo de archivos vacíos, corruptos o con extensión no permitida.
  - Si se repite un nombre, se renombra automáticamente (`_2`).
  - Se pueden quitar archivos de la cola antes de procesar.
- **Confirmación antes de procesar**:
  - Cantidad de archivos, proveedor, mes, % compra y costo estimado de IA.
  - El costo estimado se calcula con el promedio histórico de costo por llamada.
- **Cola global de procesamiento**:
  - Progreso por lote y por archivo.
  - Contadores de OK, duplicados y errores.
  - Suma de montos guardados.
  - Ventas creadas automáticamente.
  - Acciones para duplicados ("Adjuntar PDF a la existente") y errores ("Reintentar").
  - Limpieza de lotes terminados.
  - Actualización automática cada 1,5 segundos.

### 6.2 Procesamiento OCR con IA

- Motor: **Google Gemini** con salida JSON estructurada.
- **Modo dual**:
  - PDF con texto nativo: se envía el texto extraído (más rápido y barato).
  - PDF escaneado o imagen: se renderiza a PNG a 200 DPI y se envía como visión.
- Límites: máximo 3 páginas por PDF, 10 MB por archivo.
- Esquema de extracción **dinámico**: se construye con los campos activos marcados como "Pedir a la IA".
- Prompt dinámico con instrucciones fiscales y descripción de cada campo.
- `temperature=0` para reducir variaciones.
- **Reintentos**: hasta 3 intentos por modelo ante errores transitorios (429, 503, cuota, timeout, etc.), con backoff lineal.
- **Modelos fallback**: lista configurable por `.env`.
- **Validación de archivos**: magic bytes (PDF/JPEG/PNG), tamaño y verificación de imágenes.
- **Caché por hash SHA-256**: volver a subir el mismo archivo devuelve el resultado guardado sin consumir API.
- **Deduplicación**: clave `NIT_Emisor + Nro_Factura + Cod_Autorizacion`; avisa y espera decisión, no bloquea.
- **Auto-venta**: al guardar una factura, crea o incrementa automáticamente la venta al emisor con el `% venta` de la ficha del cliente (5 % por defecto si no existe).
- **Registro de costo de IA**: tokens de entrada y salida por llamada, convertidos a USD con precios configurables.
- **Manejo de error**: si la extracción falla, la factura queda en estado `ERROR` con el detalle en Observaciones y opción de reintentar.
- **Reconciliación de ventas**: si una factura quedó sin venta (por ejemplo por un fallo previo), los reportes crean la venta faltante automáticamente y, si la razón social está vacía, la completan usando el NIT.

### 6.3 Cola de procesamiento (`ocr_queue.py`)

- `ThreadPoolExecutor` global con `MAX_WORKERS` (4 por defecto).
- Máquina de estados por archivo: `EN_COLA → PROCESANDO → OK / DUPLICADO / ERROR`.
- Múltiples lotes simultáneos de distintos proveedores.
- Idempotencia por hash y caché.
- Reintento automático de errores transitorios de la IA.
- Reintento manual por archivo.
- Opción de adjuntar el PDF de un duplicado a la factura existente.
- Opción de descartar un archivo.
- Historial de lotes en base (`lotes_historial`): existe a nivel de datos, pero todavía no tiene pantalla.

### 6.4 Gestión del mes (`/gestion`)

- Selector de mes y navegación tipo explorador con migas de pan.
- **Vista del mes**:
  - Tarjetas por proveedor con: cantidad de facturas, total facturado, a pagar, pagado, saldo y estado.
  - Tarjetas por cliente con: cantidad de ventas, facturado, a cobrar, saldo y estado.
  - Sección de reportes finales.
- **Vista de proveedor**:
  - Tabla única con facturas y ambos porcentajes: `% compra`, `% venta`, monto, a pagar, a cobrar, utilidad, estado de pago y estado de venta.
  - Totales al pie.
  - Al seleccionar una factura se abre el diálogo de edición.
  - Sección de pagos: resumen, pagos registrados, registro y eliminación de pagos.
- **Vista de cliente (ventas completas)**:
  - Total facturado, a cobrar, cobrado y saldo.
  - Detalle de facturas de todos los proveedores.
  - Descarga del PDF de la empresa.
  - Cobros registrados, eliminación y registro de nuevos cobros.

### 6.5 Ventas y cobros (`/ventas`)

- Selector de mes con dos accesos grandes:
  - **COBROS**: empresas a las que se les vendió.
  - **PAGOS**: proveedores que trajeron facturas.
- **Cobros**:
  - Tabla resumen por empresa: rubro, cantidad de facturas, monto, a cobrar, proveedores, entregado, cobrado, saldo y estado.
  - Detalle por empresa con facturas y porcentaje aplicado.
  - Registro de cobros parciales o totales, aplicados a una venta concreta.
  - Métodos: QR, Efectivo, Transferencia, Otro.
  - Fecha con calendario, nota opcional.
  - Listado y eliminación de cobros.
  - Estado de la venta recalculado automáticamente.
- **Nueva venta manual**:
  - Selección de cliente existente o alta de cliente nuevo.
  - Selección múltiple de facturas aún no vendidas del mes.
  - Suma automática del monto nominal.
  - Precio sugerido = nominal × `% venta` del cliente (editable).
  - Campo "Entregado" (pdf, físico, excel) y notas.
  - Vínculo real en base mediante `venta_facturas`.
- **Pagos**:
  - Tabla resumen por proveedor: facturas, empresas que trajo, a pagar, pagado, saldo y estado.
  - Detalle por proveedor con facturas y `% compra`.
  - Registro de pagos totales o parciales, con fecha, método y nota.
  - Listado y eliminación de pagos.

### 6.6 Pagos a proveedores (`/pagos`)

- Ruta independiente con la misma lógica de pagos.
- Total a pagar, pagado y saldo por mes.
- Tabla resumen y detalle por proveedor.
- Facturas del lote con monto, `% compra` y a pagar.
- Registro y eliminación de pagos.

### 6.7 Buscar facturas (`/facturas`)

- Filtros instantáneos:
  - Mes (incluye "TODOS").
  - Proveedor.
  - Estado de pago.
  - Texto libre por número, razón social o NIT.
- Métricas del filtro: cantidad, suma de montos, suma de crédito fiscal y cantidad de vendidas.
- Tabla dinámica: las columnas se generan desde la configuración de campos.
- Edición de cualquier factura en un diálogo único.
- Eliminación con confirmación.
- Descarga del PDF original si existe.
- **Carga manual** de facturas con selección de mes.
- **Exportación del mes a Excel** con hoja de resumen y una hoja por proveedor.

### 6.8 Reportes y exportaciones

- Selector de mes.
- Opción de incluir el catálogo completo de clientes con ceros.
- Tarjetas de métricas:
  - Total facturado.
  - Compra del mes.
  - Venta a clientes.
  - Utilidad.
  - Pagado a proveedores.
  - Falta pagar a proveedores.
  - Por cobrar a clientes.
- Gráfico de utilidad por proveedor.
- Gráfico histórico de compras por mes (últimos 12 meses).
- Tabla de **costos y ganancia** por proveedor y cliente con totales.
- Tabla de **ventas resumen por cliente** con totales.
- Exportaciones:
  - **Excel de control**: hojas "COSTOS Y GANANCIA" y "VENTAS".
  - **PDF resumen mensual**.
  - **ZIP con un PDF por empresa**.
- Los reportes reconciliarán automáticamente facturas sin venta antes de calcular.

### 6.9 Configuración — Proveedores

- Tabla con búsqueda.
- Alta, edición y eliminación.
- Campos: nombre, NIT, teléfono y `% compra`.
- Selector de porcentajes con presets (1,5 a 5) y valor libre.
- El `% compra` se usa por defecto en cada lote de ese proveedor.
- El nombre es único en la tabla de proveedores.

### 6.10 Configuración — Clientes

- Tabla con búsqueda.
- Alta, edición y eliminación.
- Campos: nombre/razón social, rubro, `% venta`, NIT, teléfono y notas.
- Rubros sugeridos: CONST, MERCA, CONST-MERCA, OTRO.
- Presets de `% venta` (3,5 a 5) y valor libre.
- El `% venta` se usa para sugerir el precio de la venta y para la auto-venta.

### 6.11 Configuración — Campos

- Registro dinámico de campos de factura.
- Propiedades por campo:
  - Clave interna.
  - Etiqueta visible.
  - Tipo: texto, número, fecha o booleano.
  - Descripción para la IA.
  - Núcleo (protegido, no se puede eliminar).
  - Activo (se muestra y guarda).
  - Pedir a la IA (entra al esquema y al prompt).
  - Orden.
- Alta de campos nuevos, edición y eliminación (solo si no son núcleo).
- Los campos nuevos se guardan en el JSON `extra` de la factura.
- Desactivar un campo no borra su historial.

### 6.12 Configuración — Sistema

- Panel de **gasto de IA**: hoy, mes y total; tabla por mes con llamadas, tokens de entrada/salida y costo.
- Indicador de billing activo/inactivo.
- Conteos del sistema: facturas, ventas, proveedores, clientes, campos y caché OCR.
- Información del modelo principal y fallbacks.
- Estado del login (activado/desactivado).
- **Respaldos**: listado, tamaño y creación manual.
- **Seeders**: carga inicial de proveedores-persona y clientes activos.
- **Caché OCR**: vaciado manual.

### 6.13 Seguridad y sesión

- Login por contraseña opcional (`APP_PASSWORD`).
- Comparación de contraseña en tiempo constante (`secrets.compare_digest`).
- Bloqueo de 15 minutos tras 10 intentos fallidos por cliente.
- Sesión con vencimiento configurable (12 horas por defecto).
- Cierre de sesión manual.
- Cabeceras HTTP de seguridad: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- SQL parametrizado en toda la capa de datos.
- Validación de entrada de archivos y de respuesta del LLM.
- Secretos fuera del código, en `.env`.

### 6.14 Respaldos y archivos

- Backup automático al iniciar la aplicación.
- Backup automático cada 24 horas.
- Backup manual desde Configuración.
- Uso de la API de backup de SQLite (copia consistente).
- Retención configurable (30 copias por defecto).
- Carpeta `backups/`.
- Archivos originales:
  - Se guardan como PDF en `archivos/{mes}/{proveedor}/`.
  - Las imágenes JPG/PNG se convierten a PDF a 150 DPI.
  - El nombre se basa en el número de factura; si se repite, se agrega sufijo.
  - Se puede descargar el original desde la factura.

### 6.15 Migración, importación y utilidades

- `migrar_sheets.py`: migración histórica de Google Sheets a SQLite (idempotente).
- `sheets_manager.py`: capa Google Sheets usada solo por la migración.
- `importar_septiembre.py`: importación de una carpeta mensual con archivos Excel de compra y venta.
  - Reconstruye clientes, facturas y ventas.
  - **Atención:** antes de importar elimina las tablas de facturas, ventas, clientes, cobros, pagos, gastos y caché. Es una herramienta destructiva de un solo uso.
- `seeds.py`: datos iniciales de proveedores y clientes, idempotente.
- `check_setup.py`: diagnóstico de API key, credenciales, modelo, base de datos y campos.
- `app.py`: interfaz legacy en Streamlit con 7 pestañas (carga, registros, proveedores, clientes, ventas, balance y campos).

---

## 7. Flujos principales

### 7.1 Flujo de carga de facturas

```text
Usuario elige mes y proveedor
→ arrastra archivos
→ validación de extensión, tamaño y tipo real
→ caché por hash (si existe, resultado instantáneo)
→ PDF con texto: texto a Gemini
→ PDF escaneado o imagen: render 200 DPI y visión
→ respuesta validada con esquema Pydantic
→ deduplicación por NIT + número + autorización
→ guardado de factura y PDF original
→ auto-venta al emisor con % venta del cliente
→ actualización de la cola en pantalla
```

### 7.2 Flujo de cobro

```text
Factura guardada
→ venta creada o manual
→ cliente paga total o parcial
→ registro de cobro
→ estado de la venta: PENDIENTE / PARCIAL / COBRADO
→ reporte de cobranza actualizado
```

### 7.3 Flujo de pago a proveedor

```text
Facturas del proveedor en el mes
→ a pagar = Σ monto × % compra
→ registro de pago total o parcial
→ estado del proveedor: PENDIENTE / PARCIAL / PAGADO
→ reporte de pagos actualizado
```

---

## 8. Modelo de datos

Base SQLite con 11 tablas:

| Tabla | Rol |
|---|---|
| `proveedores` | Proveedores-persona: NIT, nombre, teléfono, comisión pactada |
| `clientes` | Empresas cliente: nombre, NIT, teléfono, notas, rubro, % venta |
| `facturas` | Facturas: mes, proveedor, datos fiscales, montos, % compra, estado, venta vinculada, ruta del PDF, `extra` JSON |
| `ventas` | Ventas: mes, cliente, monto nominal, precio a cobrar, estado, entregado, notas |
| `venta_facturas` | Relación N:M entre ventas y facturas |
| `cobros` | Cobros de clientes: venta, fecha, monto, método, nota |
| `pagos_proveedor` | Pagos a proveedores: proveedor, mes, fecha, monto, método, nota |
| `campos_config` | Configuración de campos: clave, etiqueta, tipo, descripción IA, núcleo, activo, en_ia, orden |
| `extraction_cache` | Caché OCR: hash SHA-256 → resultado JSON |
| `gastos_ia` | Consumo de IA: fecha, modelo, tokens, costo |
| `lotes_historial` | Historial de lotes OCR (backend listo, sin pantalla) |

Índices principales: mes de facturas, número de factura, venta vinculada, mes de ventas, cobros por venta, pagos por proveedor y mes.

---

## 9. Integraciones actuales

| Integración | Uso | Estado |
|---|---|---|
| Google Gemini | OCR de facturas | Activa |
| Google Sheets | Migración histórica únicamente | Parcial / legado |
| Google Drive | Scopes de la migración | Parcial / legado |
| SQLite | Persistencia local | Activa |
| Sistema de archivos | PDFs originales, exports y backups | Activa |

No existe integración con:

- Sistema tributario (SIN / facturación electrónica).
- Bancos o conciliación bancaria.
- WhatsApp, email o SMS.
- Pasarelas de pago o QR.
- ERPs o sistemas contables.
- Aplicaciones móviles.
- API pública o webhooks.

---

## 10. Limitaciones conocidas y deuda funcional

Estos puntos ya existen en el sistema, pero conviene corregirlos o completarlos:

1. **Sin fechas de vencimiento**: no hay campo de vencimiento en ventas ni en facturas; no se puede calcular antigüedad de deuda.
2. **Sin edición ni eliminación de ventas en la interfaz nueva**: `db.actualizar_venta` y `db.eliminar_venta` existen y se usan en la interfaz legacy, pero no están expuestos en NiceGUI. Una venta mal creada no se puede corregir desde la pantalla actual.
3. **Integridad por nombre**: proveedores y clientes se relacionan con facturas y ventas por nombre de texto, no por ID. Renombrar un cliente o proveedor no actualiza sus facturas/ventas históricas.
4. **Eliminación sin validación**: se puede eliminar un proveedor o cliente con facturas/ventas asociadas; los registros históricos quedan huérfanos.
5. **Caché OCR sin limpieza automática**: la función permite retener 20.000 registros, pero en la práctica solo se vacía manualmente desde Configuración.
6. **Historial de lotes sin pantalla**: la tabla `lotes_historial` se escribe, pero no hay vista para consultarla.
7. **Rutas duplicadas**: `/pagos` y `/reportes` existen, pero no están en el menú; la misma funcionalidad aparece dentro de Gestión y Ventas.
8. **Sin notificaciones persistentes**: solo hay avisos tipo toast en la sesión actual. No hay centro de notificaciones ni envío externo.
9. **Sin API**: no hay endpoints HTTP para integrar otros sistemas.
10. **Sin multiusuario ni roles**: una sola contraseña compartida; no hay permisos por módulo ni auditoría de acciones.
11. **Backup solo de la base**: los PDFs de `archivos/` y los exports no se respaldan automáticamente.
12. **Sin tests automatizados**: no hay suite de pruebas unitarias ni de integración.
13. **Importación destructiva**: `importar_septiembre.py` borra tablas antes de importar; requiere backup previo y no tiene vista previa.
14. **Supuesto cliente = emisor**: la auto-venta usa la razón social del emisor de la factura como cliente. En los Excel originales de septiembre, el cliente estaba en la columna NOMBRE (comprador) y el proveedor real en EMPRESA (emisor). Si el OCR extrae el emisor y el cliente es el comprador, los reportes por cliente quedan invertidos. Hay que validar este criterio con el negocio y, si corresponde, extraer también los datos del comprador.
15. **Solo bolivianos**: no hay moneda ni tipo de cambio.
16. **Sin IVA desglosado**: se guarda crédito fiscal, pero no un desglose impositivo completo.
17. **Sin fecha/hora de auditoría de cambios**: solo existe `creado_en`; no hay historial de modificaciones.
18. **Sin borrado lógico**: las eliminaciones son físicas.
19. **Sin bloqueo de concurrencia de usuarios**: SQLite en WAL tolera lecturas, pero no está diseñado para varios usuarios editando a la vez.
20. **Sin validación contra el padrón tributario**: no se verifica que el NIT o el CUF existan.

---

## 11. Funcionalidades faltantes y roadmap

Leyenda de estado:

- **No existe**: no hay implementación.
- **Parcial**: hay base técnica o una versión limitada.
- **Backend sin UI**: la lógica existe, falta pantalla.

### 11.1 Notificaciones y alertas

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Centro de notificaciones in-app | No existe | Bandeja persistente de avisos: errores OCR, backups, cobros vencidos, pagos pendientes | Alta |
| Recordatorios de cobro | No existe | Avisos por email/WhatsApp antes y después del vencimiento | Alta |
| Recordatorios de pago a proveedores | No existe | Calendario y avisos de pagos pendientes | Alta |
| Alertas de errores OCR y duplicados | Parcial | Hoy solo aparecen en la cola en vivo | Media |
| Alerta de backup fallido | No existe | Notificar al administrador si el backup no se genera | Alta |
| Alerta de cuota o costo de IA | No existe | Aviso al superar un umbral de gasto o de límite diario | Media |
| Resumen diario o semanal | No existe | Envío automático de KPIs y pendientes | Media |
| Notificaciones push / PWA | No existe | Avisos al celular o escritorio | Baja |
| Integración WhatsApp Business / Telegram / SMTP | No existe | Canal de envío de notificaciones y estados de cuenta | Media |
| Notificación al cliente de su estado de cuenta | No existe | Enviar PDF o resumen por email/WhatsApp | Alta |

### 11.2 API e integraciones

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| API REST con autenticación | No existe | Endpoints para facturas, ventas, cobros, pagos y reportes | Alta |
| Documentación OpenAPI / Swagger | No existe | Contrato formal para integradores | Media |
| Webhooks | No existe | Avisar a otros sistemas cuando se crea una venta, un cobro o termina un lote OCR | Media |
| Token de API por integración | No existe | Claves revocables y registro de uso | Media |
| Integración con SIN / facturación electrónica | No existe | Validar CUF, estado de factura y emisión | Alta |
| Conciliación bancaria | No existe | Importar extractos y cruzar cobros/pagos | Media |
| Pasarela de pago o links de cobro | No existe | Cobro con QR o link y conciliación automática | Media |
| Sincronización con Google Sheets / Drive | Parcial | Solo migración histórica, no bidireccional | Baja |
| Importación desde email o carpeta vigilada | No existe | Recibir facturas automáticamente | Media |
| App móvil o PWA | No existe | Acceso desde celular, cámara y notificaciones | Media |
| Integración con Zapier / Make / n8n | No existe | Automatizaciones sin desarrollo | Baja |
| Endpoint de salud / healthcheck | No existe | Monitoreo de disponibilidad | Media |

### 11.3 Uso de la IA — evolución

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| OCR con confianza por campo | No existe | Puntaje de confianza y cola de revisión para campos dudosos | Alta |
| Validación fiscal automática | No existe | Verificar NIT, CUF y estado de la factura contra el padrón/SIN | Alta |
| Matching inteligente de proveedores y clientes | No existe | Normalizar nombres, alias y NIT para evitar duplicados | Alta |
| Detección de duplicados difusos | Parcial | Hoy es exacta por NIT + número + autorización | Media |
| Extracción de líneas o ítems de factura | No existe | Detalle de productos, cantidades y precios | Media |
| Desglose de impuestos | No existe | IVA, subtotal, descuentos y retenciones | Media |
| Clasificación de documentos | No existe | Detectar factura, recibo, nota de crédito o foto inválida | Media |
| Separación de PDFs con varias facturas | No existe | Dividir un PDF que contiene más de un documento | Media |
| Asistente conversacional | No existe | Consultas en lenguaje natural sobre los datos | Media |
| Resúmenes automáticos de reportes | No existe | Narrativa mensual generada por IA | Baja |
| Predicción de flujo de caja | No existe | Proyección de cobros y pagos | Media |
| Aprendizaje de correcciones | No existe | Usar correcciones históricas como ejemplos para mejorar la extracción | Media |
| Mejora de imágenes de baja calidad | Parcial | Render y validación básica; no hay preprocesado avanzado | Baja |
| Presupuesto y límites de IA | Parcial | Se registra el costo, pero no se bloquea ni alerta por umbral | Media |
| Selección automática de modelo por costo/calidad | Parcial | Hay fallback, pero no una política de costo | Baja |
| Evaluación de precisión del OCR | No existe | Métricas de aciertos y errores por campo | Media |
| Cola persistente de OCR | No existe | Hoy la cola vive en memoria y se pierde al reiniciar | Media |

### 11.4 Gestión de cobros y ventas

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Fecha de vencimiento de venta | No existe | Base para recordatorios y mora | Alta |
| Reporte de antigüedad de deuda (aging) | No existe | 0-30, 31-60, 61-90, +90 días | Alta |
| Planes de pago y cuotas | No existe | Cuotas con vencimiento y estado | Media |
| Recibos o comprobantes de cobro y pago | No existe | PDF imprimible o enviable | Alta |
| Notas de crédito, anulación y refacturación | No existe | Corregir ventas sin borrar historial | Alta |
| Edición y eliminación de ventas en la UI nueva | Parcial | Backend listo, UI no expuesta | Alta |
| Sobrepagos y saldos a favor | No existe | Registrar y aplicar saldos | Media |
| Moneda y tipo de cambio | No existe | Hoy todo en bolivianos | Media |
| Impuestos, retenciones y descuentos | No existe | Cálculo fiscal completo | Media |
| Estado de cuenta del cliente exportable y enviable | Parcial | Existe PDF por empresa; falta envío | Alta |
| Recordatorios y promesas de pago | No existe | Gestión de cobranza | Alta |
| Links de pago o QR | No existe | Cobro digital | Media |
| Comisiones de vendedores o proveedores | Parcial | Existe % compra y % venta, no liquidación de comisiones | Media |
| Metas y proyecciones de venta | No existe | Seguimiento comercial | Baja |
| Ventas recurrentes | No existe | Plantillas o periodicidad | Baja |
| Cierre de caja diario | No existe | Arqueo de cobros por método | Media |
| Conciliación de cobros contra depósitos | No existe | Cruzar cobros con banco | Media |
| Bloqueo de crédito por mora | No existe | Límite o alerta por cliente moroso | Media |
| Historial de cambios por venta | No existe | Auditoría de ediciones y cobros | Media |
| Ventas consolidadas o multi-cliente | No existe | Agrupar varias ventas en una operación | Baja |

### 11.5 Reportes y BI

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Dashboard ejecutivo | Parcial | Hay métricas y dos gráficos; falta una vista gerencial | Alta |
| Reportes comparativos mes a mes y año a año | No existe | Tendencias y variaciones | Alta |
| Reporte de antigüedad de cobros y pagos | No existe | Aging de cartera y proveedores | Alta |
| Flujo de caja proyectado | No existe | Cobros esperados menos pagos comprometidos | Media |
| Reportes fiscales | Parcial | Crédito fiscal y montos; falta IVA y libro de compras/ventas | Media |
| Reportes por proveedor, cliente, rubro y empresa | Parcial | Hay tablas por proveedor/cliente; falta filtro y agrupación flexible | Media |
| Exportación CSV / Excel / PDF programada | Parcial | Exportación manual; falta programación y envío | Media |
| Pivot o tablero personalizable | No existe | Elegir filas, columnas y métricas | Baja |
| Historial de lotes OCR en pantalla | Backend sin UI | Costo, duración, OK, duplicados y errores por lote | Media |
| Reporte de precisión y costo de IA | Parcial | Costo por mes; falta precisión por campo | Media |
| Reporte de archivos faltantes u huérfanos | No existe | Facturas sin PDF, ventas sin factura, pagos sin respaldo | Media |
| Alertas y metas visuales | No existe | Semáforos de cobranza y rentabilidad | Baja |

### 11.6 Seguridad, usuarios y auditoría

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Multiusuario con roles | No existe | Administrador, operador, cobrador, solo lectura | Alta |
| Auditoría de acciones | No existe | Quién creó, editó o eliminó cada registro y cuándo | Alta |
| Contraseñas por usuario y hash | No existe | Hoy hay una única contraseña de aplicación | Alta |
| Doble factor (2FA) | No existe | Segunda capa de acceso | Baja |
| Recuperación de contraseña | No existe | Flujo de reseteo | Media |
| Permisos por módulo y acción | No existe | Restringir pagos, reportes o eliminaciones | Alta |
| Papelera / borrado lógico | No existe | Recuperar registros eliminados | Media |
| Registro de inicios de sesión | No existe | Historial de accesos | Media |
| Cifrado de base o campos sensibles | No existe | Protección en reposo | Baja |
| Rate limiting general | Parcial | Solo bloqueo de login | Media |
| HTTPS obligatorio | Parcial | Depende del despliegue (túnel o proxy) | Alta |
| Gestión de secretos | Parcial | `.env` local; falta un gestor dedicado | Baja |

### 11.7 Operación, infraestructura y calidad

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Tests automatizados | No existe | Unitarios de cálculos, integración de DB y flujos | Alta |
| Integración continua (CI) | No existe | Validar cambios automáticamente | Media |
| Docker o instalador | No existe | Despliegue reproducible | Media |
| Logs estructurados | Parcial | No hay logging centralizado | Media |
| Monitoreo y alertas de disponibilidad | No existe | Estado del servicio y errores | Media |
| Migraciones versionadas de base | Parcial | Migración ad-hoc en `db.py` | Media |
| Backup de archivos y exports | No existe | Hoy solo se respalda la base | Alta |
| Restauración desde la UI | No existe | Recuperar un backup sin acceso al sistema de archivos | Alta |
| Cola OCR persistente | No existe | Sobrevivir reinicios sin perder lotes | Media |
| Modo offline / PWA | No existe | Uso sin conexión y sincronización | Baja |
| Multi-sucursal o multi-empresa | No existe | Separar datos por empresa | Media |
| Healthcheck | No existe | Endpoint de estado para monitoreo | Media |
| Documentación de usuario | Parcial | README y documentos técnicos | Media |
| Internacionalización | No existe | Hoy solo español | Baja |

### 11.8 Datos y migraciones

| Funcionalidad | Estado | Descripción | Prioridad |
|---|---|---|---|
| Importación CSV/Excel con vista previa | Parcial | Existe importación específica de septiembre, sin preview | Alta |
| Importación no destructiva | No existe | La actual borra tablas antes de importar | Alta |
| Exportación completa y portabilidad | Parcial | Copiar carpeta o base; falta export formal | Media |
| Merge y deduplicación de clientes y proveedores | No existe | Unificar nombres y alias | Alta |
| Normalización de nombres | No existe | Evitar variantes del mismo cliente/proveedor | Alta |
| Limpieza de huérfanos | Parcial | Reconciliación de facturas sin venta | Media |
| Archivado o cierre de meses | No existe | Bloquear meses cerrados | Media |
| Validación de integridad referencial | No existe | Impedir borrar maestros con movimientos | Alta |
| Historial de meses y auditoría de datos | No existe | Consultas históricas avanzadas | Media |
| Multi-moneda en datos | No existe | Montos en una sola moneda | Baja |

### 11.9 Mejoras rápidas recomendadas (quick wins)

1. Agregar **fecha de vencimiento** a la venta y un **reporte de aging**.
2. Exponer **editar y eliminar venta** en la interfaz nueva.
3. Crear un **centro de notificaciones in-app** y alertas de backup/errores.
4. Implementar **recibos PDF** de cobro y pago.
5. Añadir **auditoría básica** (quién y cuándo) en facturas, ventas, cobros y pagos.
6. Validar la regla **cliente = emisor vs comprador** con datos reales.
7. Incluir **backup de `archivos/` y `exports/`**.
8. Agregar **tests** de las fórmulas de reportes y del flujo de cobros/pagos.
9. Mostrar el **historial de lotes OCR** en Configuración.
10. Exponer **merge de clientes/proveedores** y evitar borrados con movimientos.

---

## 12. Roadmap sugerido por fases

| Fase | Duración estimada | Contenido | Resultado |
|---|---|---|---|
| Fase 1 — Cobranza y control | 2 a 3 semanas | Vencimientos, aging, recibos PDF, edición/eliminación de ventas, auditoría básica, centro de notificaciones in-app, backup de archivos | Operación diaria más segura y cobranza medible |
| Fase 2 — Integraciones y reportería | 3 a 4 semanas | API REST con tokens, webhooks, documentación OpenAPI, dashboard ejecutivo, reportes comparativos, envío de estados de cuenta | Sistema integrable y con visión gerencial |
| Fase 3 — IA avanzada y automatización | 3 a 5 semanas | Confianza por campo, validación fiscal, matching de nombres, extracción de ítems e impuestos, clasificación de documentos, asistente conversacional | Menos revisión manual y mejores datos |
| Fase 4 — Multiusuario y escala | 3 a 4 semanas | Usuarios y roles, permisos, 2FA, multi-empresa, Docker, CI, monitoreo, restore desde UI | Sistema listo para equipo y crecimiento |
| Fase 5 — Ecosistema | Variable | Pasarela de pago/QR, conciliación bancaria, WhatsApp Business, PWA móvil, integración SIN, Zapier/Make | Automatización de punta a punta |

---

## 13. Anexos

### A. Variables de entorno principales

| Variable | Default | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | — | Clave de Google AI Studio |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo principal de OCR |
| `GEMINI_FALLBACK_MODELS` | lista | Modelos de respaldo |
| `GEMINI_MAX_RETRIES` | `3` | Reintentos por modelo |
| `GEMINI_TIMEOUT_SEG` | `120` | Timeout de la llamada |
| `RUTA_DB` | `facturas.db` | Ubicación de la base |
| `MAX_WORKERS` | `4` | OCR en paralelo |
| `PDF_RENDER_DPI` | `200` | Resolución de render de PDF |
| `UMBRAL_TEXTO_NATIVO` | `60` | Mínimo de texto para usar modo texto |
| `CARPETA_EXPORTS` | `exports` | Carpeta de exportaciones |
| `CARPETA_ARCHIVOS` | `archivos` | Carpeta de originales |
| `CARPETA_RESPALDOS` | `backups` | Carpeta de respaldos |
| `RETENCION_RESPALDOS` | `30` | Copias a conservar |
| `APP_PASSWORD` | vacío | Activa el login |
| `SESION_HORAS` | `12` | Vencimiento de sesión |
| `MAX_INTENTOS_LOGIN` | `10` | Intentos antes del bloqueo |
| `PRECIO_IA_ENTRADA` | `0.30` | USD por 1M tokens de entrada |
| `PRECIO_IA_SALIDA` | `2.50` | USD por 1M tokens de salida |
| `BILLING_ACTIVO` | `0` | Indica si el gasto de IA se cobra realmente |
| `GOOGLE_SHEET_MASTER_ID` | — | Solo para migración desde Sheets |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `service_account.json` | Credenciales de migración |

### B. Funciones internas clave

| Archivo | Función | Propósito |
|---|---|---|
| `db.py` | `inicializar` | Crea tablas e índices y aplica migraciones |
| `db.py` | `registrar_facturas_batch` | Inserta o reemplaza facturas |
| `db.py` | `leer_facturas_mes` / `leer_facturas_filtro` | Consultas de facturas |
| `db.py` | `registrar_venta` | Crea una venta y vincula facturas |
| `db.py` | `auto_venta_de_facturas` | Crea o incrementa la venta de un emisor |
| `db.py` | `reconciliar_ventas_mes` | Genera ventas faltantes de un mes |
| `db.py` | `registrar_cobro` | Registra un cobro y recalcula estado |
| `db.py` | `registrar_pago_proveedor` | Registra un pago a proveedor |
| `db.py` | `resumen_pagos_proveedores` | Calcula a pagar, pagado y saldo por proveedor |
| `db.py` | `obtener_cache` / `guardar_cache` | Caché OCR por hash |
| `db.py` | `registrar_gasto_ia` / `leer_gasto_ia` | Costo de IA por llamada y resúmenes |
| `ocr_queue.py` | `ColaOCR.agregar_lote` | Encola archivos y lanza el procesamiento |
| `ocr_queue.py` | `ColaOCR.resumen_lotes` | Estado de todos los lotes |
| `ocr_queue.py` | `ColaOCR.guardar_duplicado` | Adjunta un duplicado a la factura existente |
| `ocr_queue.py` | `ColaOCR.reintentar_archivo` | Reintenta un archivo con error |
| `extractor.py` | `procesar_archivo` | Punto de entrada del OCR |
| `extractor.py` | `_partes_de_archivo` | Decide texto nativo o visión |
| `extractor.py` | `_llamar_gemini` | Llamada con reintentos y fallbacks |
| `campos.py` | `construir_esquema_ia` | Esquema Pydantic dinámico |
| `campos.py` | `construir_prompt` | Prompt según campos activos |
| `reportes.py` | `resumen_costos_ganancia` | Reporte de costos y utilidad |
| `reportes.py` | `resumen_ventas_cliente` | Reporte de ventas por cliente |
| `exportador.py` | `exportar_mes_excel` | Excel mensual por proveedor |
| `exportador.py` | `exportar_reportes_mes` | Excel de control de dos hojas |
| `pdf_reportes.py` | `pdf_resumen_mes` | PDF resumen mensual |
| `pdf_reportes.py` | `pdf_empresa` | PDF de ventas de una empresa |
| `pdf_reportes.py` | `pdfs_por_empresa_zip` | ZIP con un PDF por empresa |
| `archivos.py` | `guardar_archivo_original` | Guarda el original como PDF |
| `respaldos.py` | `crear_backup` | Copia consistente de la base |
| `webui/plantilla.py` | `pagina` | Decorador de página con login y menú |
| `webui/main.py` | `main` | Arranque de la aplicación |

### C. Glosario

- **Crédito fiscal**: monto de IVA o base imponible que se puede compensar fiscalmente.
- **Proveedor-persona**: persona que trae facturas al negocio y recibe un porcentaje de compra.
- **Cliente-empresa**: empresa a la que se le vende el crédito fiscal y paga un porcentaje de venta.
- **Auto-venta**: venta creada automáticamente al guardar una factura, usando el emisor como cliente.
- **Reconciliación**: proceso que crea ventas faltantes para que los reportes no queden incompletos.
- **Lote**: conjunto de archivos procesados juntos para un proveedor y un mes.
- **Duplicado**: factura cuya combinación NIT + número + autorización ya existe.
- **Aging**: clasificación de la deuda por antigüedad.
- **Billing**: modo en el que el consumo de Gemini se cobra realmente en la cuenta de Google.

### D. Archivos del proyecto

```text
app.py                    Interfaz legacy Streamlit
archivos.py               Almacenamiento de originales
campos.py                 Esquema y prompt de IA
check_setup.py            Diagnóstico de instalación
config.py                 Configuración y constantes
db.py                     Capa de datos SQLite
exportador.py             Exportación Excel
extractor.py              Motor OCR Gemini
importar_septiembre.py    Importación histórica de septiembre
migrar_sheets.py          Migración Google Sheets a SQLite
ocr_queue.py              Cola OCR en segundo plano
pdf_reportes.py           Reportes PDF
reportes.py               Cálculos de reportes
respaldos.py              Backups
seeds.py                  Datos iniciales
sheets_manager.py         Capa Google Sheets (legado)
webui/main.py             Arranque NiceGUI
webui/plantilla.py        Login, sesión y plantilla
webui/componentes.py      Componentes reutilizables
webui/pag_carga.py        Portada y carga
webui/pag_gestion.py      Gestión del mes
webui/pag_ventas.py       Ventas y cobros
webui/pag_pagos.py        Pagos a proveedores
webui/pag_facturas.py     Búsqueda y CRUD de facturas
webui/pag_reportes.py     Reportes
webui/pag_configuracion.py Configuración general
webui/pag_maestros.py     Proveedores y clientes
webui/pag_campos.py       Campos configurables
webui/pag_ajustes.py      Sistema, backups y caché
```

---

**Fin del documento.**
