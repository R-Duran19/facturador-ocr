"""Chequeo de salud del sistema: Python, dependencias, .env, Gemini, base y carpetas.

CLI:    venv/Scripts/python.exe check_setup.py   (o verificar.bat)
UI:     Configuración → Sistema → botón "Salud del sistema"
"""

import sys

import config

__all__ = ["verificar_salud"]


def verificar_salud(probar_gemini: bool = True) -> list:
    """Devuelve [{chequeo, estado(OK/FALLA/AVISO), detalle}]. Nunca lanza excepciones."""
    chequeos = []

    def agregar(nombre: str, ok: bool, detalle: str, aviso: bool = False) -> None:
        chequeos.append(
            {"chequeo": nombre, "estado": "AVISO" if aviso else ("OK" if ok else "FALLA"), "detalle": detalle}
        )

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    buena = version.startswith(("3.11", "3.12"))
    agregar("Python", buena, f"Python {version}" + ("" if buena else " (se recomienda 3.12)"), aviso=not buena)

    faltan = []
    for modulo in ("nicegui", "pydantic", "dotenv", "pandas", "openpyxl", "fpdf", "pymupdf", "PIL", "google.genai"):
        try:
            __import__(modulo)
        except Exception:
            faltan.append(modulo)
    agregar("Dependencias", not faltan, "todas instaladas" if not faltan else f"faltan: {', '.join(faltan)}")

    tiene_key = bool(config.GEMINI_API_KEY) and "tu_api_key" not in config.GEMINI_API_KEY
    agregar(
        "API de Gemini (.env)",
        tiene_key,
        f"configurada ({config.GEMINI_API_KEY[:8]}...)" if tiene_key else "GEMINI_API_KEY vacía o mal configurada en .env",
    )

    from pathlib import Path

    problemas = []
    for carpeta in (config.CARPETA_ARCHIVOS, config.CARPETA_EXPORTS, config.CARPETA_RESPALDOS):
        try:
            p = Path(carpeta)
            p.mkdir(parents=True, exist_ok=True)
            t = p / "_health.tmp"
            t.write_text("x", encoding="utf-8")
            t.unlink()
        except Exception:
            problemas.append(str(carpeta))
    agregar(
        "Carpetas (archivos/exports/backups)",
        not problemas,
        "escribibles" if not problemas else f"sin permiso: {', '.join(problemas)}",
    )

    try:
        import respaldos

        n = len(respaldos.listar_backups())
        agregar("Backups", n > 0, f"{n} copias en {config.CARPETA_RESPALDOS}/", aviso=n == 0)
    except Exception as e:
        agregar("Backups", False, str(e))

    try:
        import db

        db.inicializar()
        conn = db.conexion()
        conteo = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("proveedores", "clientes", "facturas", "ventas", "cobros", "pagos_proveedor")
        }
        conn.close()
        agregar("Base de datos", True, ", ".join(f"{k}: {v}" for k, v in conteo.items()))
    except Exception as e:
        agregar("Base de datos", False, str(e))

    try:
        import db

        activos = [c["clave"] for c in db.listar_campos() if c["activo"] and c["en_ia"]]
        agregar("Campos que extrae la IA", bool(activos), ", ".join(activos) or "ninguno activo")
    except Exception as e:
        agregar("Campos que extrae la IA", False, str(e))

    if probar_gemini:
        if tiene_key:
            try:
                from google import genai

                client = genai.Client(api_key=config.GEMINI_API_KEY)
                resp = client.models.generate_content(
                    model=config.MODEL_NAME, contents="Responde únicamente con la palabra: OK"
                )
                texto = (resp.text or "").strip()[:40]
                agregar("Gemini (prueba real)", bool(texto), f"{config.MODEL_NAME} respondió: {texto}")
            except Exception as e:
                agregar("Gemini (prueba real)", False, str(e)[:180])
        else:
            agregar("Gemini (prueba real)", False, "sin API key no se puede probar", aviso=True)

    return chequeos


def main() -> int:
    print("=" * 60)
    print("SALUD DEL SISTEMA - Facturador OCR")
    print("=" * 60)
    resultados = verificar_salud()
    fallas = 0
    for r in resultados:
        marca = {"OK": "[OK]   ", "FALLA": "[FALLA]", "AVISO": "[AVISO]"}[r["estado"]]
        if r["estado"] == "FALLA":
            fallas += 1
        print(f" {marca} {r['chequeo']:<30} {r['detalle']}")
    print("=" * 60)
    print("RESULTADO: " + ("TODO OK" if fallas == 0 else f"{fallas} FALLA(S) — revisa arriba"))
    print("=" * 60)
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
