from typing import Optional

from pydantic import Field, create_model

import db

TIPOS_PYDANTIC = {
    "numero": Optional[float],
    "booleano": Optional[bool],
    "fecha": Optional[str],
    "texto": Optional[str],
}

INSTRUCCIONES_BASE = """Eres un asistente tributario y contable de alta precisión.
Analiza la factura adjunta — puede llegar como imagen, PDF escaneado, o como TEXTO extraído
de un PDF digital; en todos los casos extrae los campos requeridos en el esquema JSON.

Reglas:
1. Extrae únicamente información explícita en el documento. No inventes ni deduzcas datos.
2. Si un dato no es legible o no existe, usa null (o 0.0 en campos numéricos obligatorios).
3. Los montos deben ser números con hasta 2 decimales, sin símbolos de moneda ni separadores de miles.
4. Las fechas deben tener el formato YYYY-MM-DD.
5. En Observaciones reporta irregularidades: datos ilegibles, tachaduras, falta de NIT, etc.
6. Si el documento NO es una factura (por ejemplo un recibo o una foto aleatoria), devuelve todos
   los campos nulos/0.0 y explícalo en Observaciones.
7. Distingue SIEMPRE emisor y comprador: Razon_Social es quien EMITE/VENDE la factura;
   Razon_Social_Cliente es el COMPRADOR/cliente a quien se factura. Nunca uses el emisor como cliente.
8. NIT_Emisor pertenece al emisor; NIT_Cliente pertenece al comprador. No los mezcles.
9. El comprador puede aparecer después de "Nombre/Razón Social", "Señor(es)", "Cliente" o "Empresa",
   o en la línea anterior a esa etiqueta. Extrae el nombre tal como figura, sin agregar "EMPRESA ".
"""


def construir_esquema_ia():
    campos = [
        c
        for c in db.listar_campos()
        if c["activo"] and c["en_ia"] and c["clave"] not in ("Observaciones",)
    ]
    definiciones = {}
    for c in campos:
        tipo = TIPOS_PYDANTIC.get(c["tipo"], Optional[str])
        definiciones[c["clave"]] = (
            tipo,
            Field(None, description=c["descripcion"] or c["etiqueta"]),
        )
    definiciones["Observaciones"] = (
        Optional[str],
        Field(None, description="Notas relevantes o irregularidades detectadas"),
    )
    return create_model("FacturaExtraida", **definiciones)


def construir_prompt(modo: str = "vision") -> str:
    campos_activos = [
        c
        for c in db.listar_campos()
        if c["activo"] and c["en_ia"] and c["clave"] != "Observaciones"
    ]
    lista = "\n".join(
        f"- {c['clave']} ({c['etiqueta']}): {c['descripcion'] or 'extraer del documento'}"
        for c in campos_activos
    )
    nota_modo = (
        "El documento se entrega como TEXTO extraído de un PDF digital: analiza ese texto.\n"
        if modo == "texto"
        else "El documento se entrega como imagen/PDF escaneado: analiza visualmente.\n"
    )
    return (
        INSTRUCCIONES_BASE
        + nota_modo
        + "\nCampos a extraer:\n"
        + lista
        + "\n- Observaciones: notas relevantes o irregularidades detectadas\n"
    )


__all__ = ["construir_esquema_ia", "construir_prompt"]
