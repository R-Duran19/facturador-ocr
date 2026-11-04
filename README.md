# 📄 Facturador OCR — Compra/Venta de Crédito Fiscal

Sistema para un usuario: subís fotos/PDFs de facturas, la IA (Gemini) extrae los datos,
los gestionás, vendés el crédito fiscal a clientes y registrás cobros (totales o parciales).
Todo local y veloz sobre **SQLite**, interfaz **NiceGUI**, procesamiento en **cola en segundo plano**.

## Características
- 🚀 **OCR dual**: PDFs con texto nativo van solo como texto (3-5x más rápido/barato); escaneados → visión 200 DPI
- ⚡ **Cola multi-lote en background**: subís 50 PDFs del Proveedor A y seguís subiendo del Proveedor B; estados en vivo por archivo (EN_COLA / PROCESANDO / OK / DUPLICADA / ERROR)
- ♻️ **Caché por hash**: re-subir el mismo archivo es instantáneo y no consume API
- 🚨 **Deduplicación global** (avisa, no bloquea)
- ⚙️ **Campos configurables**: qué guardar y qué le pide la IA, editable desde la app (extras en JSON)
- 💰 **Ventas con cobros parciales**: saldos y estados PENDIENTE / PARCIAL / COBRADO automáticos
- 📤 **Export Excel** por mes con hoja por proveedor
- 🔒 **Login por password** (activable), backups automáticos con retención, cabeceras de seguridad
- 🧩 Campos núcleo en columnas SQL + extras en JSON → adaptable sin migraciones

## Arranque

```bash
venv\Scripts\activate
python -m webui.main        # interfaz nueva → http://127.0.0.1:8080
streamlit run app.py        # interfaz legacy (en paralelo hasta validación) → :8501
```

Primera vez: copiar `.env.example` a `.env` y completar `GEMINI_API_KEY` (AI Studio).
Verificar todo con `python check_setup.py`.

## Estructura
```text
├── webui/                  # interfaz NiceGUI (capa UI)
│   ├── main.py             # arranque, cabeceras de seguridad, backups programados
│   ├── plantilla.py        # sesión/login, header, drawer
│   ├── componentes.py      # widgets reutilizables
│   └── pag_*.py            # una página por archivo
├── ocr_queue.py            # cola OCR (máquina de estados, idempotente)
├── extractor.py            # motor Gemini (texto/visión + caché por hash)
├── campos.py               # esquema IA dinámico + prompt
├── db.py                   # capa de datos SQLite (única fuente de verdad)
├── exportador.py           # Excel mensual por proveedor
├── respaldos.py            # backups (API de backup de SQLite) + retención
├── migrar_sheets.py        # migración histórica Google Sheets → SQLite
├── app.py                  # (legacy) interfaz Streamlit
├── facturas.db             # LA BASE (respaldar)
└── docs/arquitectura.md    # decisiones de diseño
```

## Publicar en internet (cuando decidas)
1. Poné `APP_PASSWORD=tu_clave` en `.env`
2. **Cloudflare Tunnel (gratis, HTTPS incluido)**: instalá `cloudflared` → `cloudflared tunnel --url http://127.0.0.1:8080`
3. O VPS: `HOST=0.0.0.0` + Caddy/Nginx con HTTPS
- El login bloquea tras 10 intentos fallidos (15 min) y la sesión vence en 12 h

## Configuración (.env)
| Variable | Default | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | — | Key de Google AI Studio |
| `GEMINI_MODEL` | gemini-3.5-flash | Modelo principal (fallbacks configurables) |
| `MAX_WORKERS` | 4 | Procesos OCR en paralelo |
| `APP_PASSWORD` | (vacío = sin login) | Protección de la app |
| `RUTA_DB` | facturas.db | Ubicación de la base |

## Solución de problemas
| Problema | Qué hacer |
|---|---|
| Facturas en ERROR | Botón "Reintentar" en la cola; el detalle queda en la fila |
| Factura duplicada | Queda marcada en la cola: "Guardar igual" o descartar |
| Quiero otro campo en las facturas | Tab ⚙️ Campos → Agregar (eligen si la IA lo extrae) |
| Mover de PC | Copiar el proyecto completo (o al menos `facturas.db` + `.env`) |
