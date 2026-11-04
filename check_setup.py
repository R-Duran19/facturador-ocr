import sys

import config


def main() -> int:
    print("=" * 60)
    print("VERIFICACION DE SETUP - Facturador OCR")
    print("=" * 60)
    ok = True

    print("\n[1] Variables de entorno (.env)")
    if not config.GEMINI_API_KEY or "PEGA" in config.GEMINI_API_KEY:
        print("  [FALTA] GEMINI_API_KEY no configurada")
        ok = False
    else:
        print(f"  [OK] GEMINI_API_KEY configurada ({config.GEMINI_API_KEY[:8]}...)")
        if not (config.GEMINI_API_KEY.startswith("AIza") or config.GEMINI_API_KEY.startswith("AQ.")):
            print("  [AVISO] Formato de key inusual (ni AIza ni AQ.). Verificala.")

    if not config.GOOGLE_SHEET_MASTER_ID or "PEGA" in config.GOOGLE_SHEET_MASTER_ID:
        print("  [AVISO] GOOGLE_SHEET_MASTER_ID no configurado (solo necesario para migrar desde Sheets)")
    else:
        print(f"  [OK] GOOGLE_SHEET_MASTER_ID configurado ({config.GOOGLE_SHEET_MASTER_ID[:12]}...)")

    print(f"\n[2] Modelo IA")
    print(f"  Principal:  {config.MODEL_NAME}")
    print(f"  Fallbacks:  {', '.join(config.FALLBACK_MODELS)}")

    import os

    print("\n[3] Credenciales de servicio")
    if not os.path.exists(config.SERVICE_ACCOUNT_FILE):
        print(f"  [FALTA] No existe '{config.SERVICE_ACCOUNT_FILE}'")
        ok = False
    else:
        print(f"  [OK] '{config.SERVICE_ACCOUNT_FILE}' encontrado")

    if ok:
        print("\n[4] Prueba de API de Gemini")
        try:
            from google import genai

            client = genai.Client(api_key=config.GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=config.MODEL_NAME, contents="Responde unicamente con la palabra: OK"
            )
            print(f"  [OK] Gemini respondio: {resp.text.strip()[:40]}")
        except Exception as e:
            print(f"  [ERROR] {e}")
            ok = False

        print("\n[5] Prueba de base de datos SQLite")
        try:
            import db

            db.inicializar()
            conn = db.conexion()
            conteo = {
                "proveedores": conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0],
                "clientes": conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
                "facturas": conn.execute("SELECT COUNT(*) FROM facturas").fetchone()[0],
                "ventas": conn.execute("SELECT COUNT(*) FROM ventas").fetchone()[0],
                "campos": conn.execute("SELECT COUNT(*) FROM campos_config").fetchone()[0],
            }
            conn.close()
            print(f"  [OK] facturas.db operativa: {conteo}")
        except Exception as e:
            print(f"  [ERROR] {e}")
            ok = False

        print("\n[6] Campos configurables")
        try:
            import db

            activos_ia = [c["clave"] for c in db.listar_campos() if c["activo"] and c["en_ia"]]
            print(f"  [OK] Campos que extrae la IA: {activos_ia}")
        except Exception as e:
            print(f"  [ERROR] {e}")
            ok = False

    print("\n" + "=" * 60)
    print("RESULTADO: " + ("TODO OK - podes correr: streamlit run app.py" if ok else "HAY PROBLEMAS - revisa los mensajes de arriba"))
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
