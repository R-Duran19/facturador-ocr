import hashlib
import io
import time
from typing import List, Optional, Tuple

import pymupdf
from google import genai
from google.genai import types
from PIL import Image

import campos
import db
from config import (
    BACKOFF_BASE_SEG,
    FALLBACK_MODELS,
    GEMINI_API_KEY,
    GEMINI_TIMEOUT_SEG,
    MAX_FILE_MB,
    MAX_PDF_PAGES,
    MAX_RETRIES,
    MODEL_NAME,
    PDF_RENDER_DPI,
    PRECIO_IA_ENTRADA,
    PRECIO_IA_SALIDA,
    UMBRAL_TEXTO_NATIVO,
)

__all__ = ["procesar_archivo"]

_cliente: Optional[genai.Client] = None

ERRORES_TRANSITORIOS = (
    "429",
    "503",
    "500",
    "unavailable",
    "overload",
    "high demand",
    "quota",
    "resource_exhausted",
    "rate limit",
    "deadline",
    "internal error",
    "connection",
)

FIRMAS = (
    (b"%PDF", "pdf"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
)

CLAVES_SISTEMA = {"Nombre_Archivo", "nombre_archivo"}


def _obtener_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        if not GEMINI_API_KEY or "PEGA" in GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada en .env")
        _cliente = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_SEG * 1000),
        )
    return _cliente


def _detectar_tipo(data: bytes, filename: str) -> str:
    for firma, tipo in FIRMAS:
        if data[: len(firma)] == firma:
            return tipo
    raise ValueError(f"El archivo '{filename}' no es un JPG, PNG o PDF válido.")


def _texto_nativo(data: bytes) -> Optional[str]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return None
    try:
        texto = ""
        for i in range(min(doc.page_count, MAX_PDF_PAGES)):
            texto += doc.load_page(i).get_text() + "\n"
    except Exception:
        return None
    finally:
        doc.close()
    limpio = " ".join(texto.split())
    return limpio if len(limpio) >= UMBRAL_TEXTO_NATIVO else None


def _partes_de_archivo(data: bytes, tipo: str) -> Tuple[List[types.Part], str]:
    if tipo == "pdf":
        texto = _texto_nativo(data)
        if texto:
            return [types.Part.from_text(text=texto)], "texto"
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            n_paginas = min(doc.page_count, MAX_PDF_PAGES)
            partes = []
            for i in range(n_paginas):
                pix = doc.load_page(i).get_pixmap(dpi=PDF_RENDER_DPI)
                partes.append(types.Part.from_bytes(data=pix.tobytes("png"), mime_type="image/png"))
            if not partes:
                raise ValueError("El PDF no tiene páginas.")
            return partes, "vision"
        finally:
            doc.close()
    return [types.Part.from_bytes(data=data, mime_type=f"image/{tipo}")], "vision"


def _es_error_transitorio(mensaje: str) -> bool:
    mensaje = mensaje.lower()
    return any(clave in mensaje for clave in ERRORES_TRANSITORIOS)


def _registrar_consumo(modelo: str, response) -> float:
    try:
        uso = getattr(response, "usage_metadata", None)
        if uso is None:
            return 0.0
        tokens_in = int(getattr(uso, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(uso, "candidates_token_count", 0) or 0)
        costo = round((tokens_in / 1_000_000) * PRECIO_IA_ENTRADA + (tokens_out / 1_000_000) * PRECIO_IA_SALIDA, 6)
        if tokens_in or tokens_out:
            db.registrar_gasto_ia(modelo, tokens_in, tokens_out, PRECIO_IA_ENTRADA, PRECIO_IA_SALIDA)
        return costo
    except Exception:
        return 0.0


def _extraer_json(texto: str) -> str:
    """Quita cercos de código markdown y deja solo el objeto JSON de la respuesta."""
    t = (texto or "").strip()
    if t.startswith("```"):
        lineas = [l for l in t.splitlines() if not l.strip().startswith("```")]
        t = "\n".join(lineas).strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        return t[i : j + 1]
    return t


def _llamar_gemini(partes: List[types.Part], modo: str) -> Tuple[str, float]:
    client = _obtener_cliente()
    esquema = campos.construir_esquema_ia()
    prompt = campos.construir_prompt(modo=modo)
    modelos = [MODEL_NAME] + FALLBACK_MODELS
    ultimo_error: Exception = RuntimeError("Sin modelos configurados")

    for modelo in modelos:
        for intento in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=[*partes, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=esquema,
                        temperature=0.0,
                    ),
                )
                costo = _registrar_consumo(modelo, response)
                texto = _extraer_json((response.text or "").strip())
                if not texto:
                    raise ValueError("Respuesta vacía del modelo")
                return texto, costo
            except Exception as e:
                ultimo_error = e
                if _es_error_transitorio(str(e)) and intento < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_SEG * intento)
                else:
                    break

    raise RuntimeError(f"Falló la extracción tras agotar reintentos y modelos: {ultimo_error}")


def _registrar_consumo(modelo: str, response) -> None:
    try:
        uso = getattr(response, "usage_metadata", None)
        if uso is None:
            return
        tokens_in = int(getattr(uso, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(uso, "candidates_token_count", 0) or 0)
        if tokens_in or tokens_out:
            db.registrar_gasto_ia(modelo, tokens_in, tokens_out, PRECIO_IA_ENTRADA, PRECIO_IA_SALIDA)
    except Exception:
        pass


def _resultado_error(filename: str, error: Exception) -> dict:
    resultado: dict = {"Nombre_Archivo": filename, "Observaciones": f"ERROR: {error}"}
    try:
        for clave in campos.construir_esquema_ia().model_fields:
            if clave not in ("Observaciones", "Nombre_Archivo"):
                resultado[clave] = None
    except Exception:
        pass
    return resultado


def procesar_archivo(file_bytes: bytes, filename: str, usar_cache: bool = True) -> dict:
    try:
        if len(file_bytes) == 0:
            raise ValueError("El archivo está vacío.")
        if len(file_bytes) > MAX_FILE_MB * 1024 * 1024:
            raise ValueError(f"El archivo supera el límite de {MAX_FILE_MB} MB.")

        tipo = _detectar_tipo(file_bytes, filename)

        hash_archivo = hashlib.sha256(file_bytes).hexdigest()
        if usar_cache:
            cacheado = db.obtener_cache(hash_archivo)
            if cacheado is not None:
                datos = dict(cacheado)
                datos["Nombre_Archivo"] = filename
                datos["_cache"] = True
                return datos

        if tipo in ("jpeg", "png"):
            try:
                Image.open(io.BytesIO(file_bytes)).verify()
            except Exception:
                raise ValueError(f"La imagen '{filename}' está corrupta o no se puede leer.")

        partes, modo = _partes_de_archivo(file_bytes, tipo)
        texto = _llamar_gemini(partes, modo)
        datos = campos.construir_esquema_ia().model_validate_json(texto).model_dump()
        datos.pop("nombre_archivo", None)
        datos["Nombre_Archivo"] = filename
        db.guardar_cache(hash_archivo, {k: v for k, v in datos.items() if k not in CLAVES_SISTEMA})
        return datos

    except Exception as e:
        return _resultado_error(filename, e)
