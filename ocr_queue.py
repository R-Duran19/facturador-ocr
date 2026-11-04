import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import archivos
import db
from config import MAX_WORKERS
from extractor import _detectar_tipo, procesar_archivo

__all__ = ["COLA", "LoteOCR", "TrabajoArchivo", "ColaOCR"]

ESTADOS_ARCHIVO = ("EN_COLA", "PROCESANDO", "OK", "DUPLICADO", "ERROR")
ESTADOS_ACTIVOS = ("EN_COLA", "PROCESANDO")


@dataclass
class TrabajoArchivo:
    nombre: str
    datos: bytes
    estado: str = "EN_COLA"
    resultado: Optional[dict] = None
    error: str = ""

    def resumen(self) -> dict:
        r = self.resultado or {}
        return {
            "nombre": self.nombre,
            "estado": self.estado,
            "error": self.error,
            "nro_factura": r.get("Nro_Factura", ""),
            "razon_social": r.get("Razon_Social", ""),
            "cliente": r.get("Razon_Social_Cliente", ""),
            "monto_total": r.get("Monto_Total", 0.0),
            "credito_fiscal": r.get("Credito_Fiscal", 0.0),
            "observaciones": r.get("Observaciones", ""),
            "cache": bool(r.get("_cache")),
        }


@dataclass
class LoteOCR:
    id: str
    mes: str
    proveedor: str
    pct_compra: float = 0.0
    archivos: List[TrabajoArchivo] = field(default_factory=list)
    ventas_creadas: Dict[str, dict] = field(default_factory=dict)

    def resumen(self) -> dict:
        hechos = sum(1 for a in self.archivos if a.estado not in ESTADOS_ACTIVOS)
        return {
            "id": self.id,
            "mes": self.mes,
            "proveedor": self.proveedor,
            "pct_compra": self.pct_compra,
            "total": len(self.archivos),
            "hechos": hechos,
            "progreso": hechos / len(self.archivos) if self.archivos else 1.0,
            "activo": any(a.estado in ESTADOS_ACTIVOS for a in self.archivos),
            "ok": sum(1 for a in self.archivos if a.estado == "OK"),
            "duplicados": sum(1 for a in self.archivos if a.estado == "DUPLICADO"),
            "errores": sum(1 for a in self.archivos if a.estado == "ERROR"),
            "ventas": [
                {"cliente": v["cliente"], "precio": v["precio"]}
                for v in self.ventas_creadas.values()
            ],
            "archivos": [a.resumen() for a in self.archivos],
        }


def _clave_dedup(registro: dict) -> Tuple[str, str, str]:
    return (
        str(registro.get("NIT_Emisor", "")).strip().upper(),
        str(registro.get("Nro_Factura", "")).strip().upper(),
        str(registro.get("Cod_Autorizacion", "")).strip().upper(),
    )


class ColaOCR:
    """Cola de procesamiento OCR en segundo plano.

    Interfaz: agregar_lote(), resumen_lotes(), guardar_duplicado(),
    descartar_archivo(), reintentar_archivo(), limpiar_completados().
    La ejecución (ThreadPool global, estados, idempotencia por hash y
    deduplicación) queda oculta como implementación.
    """

    def __init__(self, workers: int = MAX_WORKERS):
        self._lotes: Dict[str, LoteOCR] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="ocr")

    def agregar_lote(
        self, mes: str, proveedor: str, archivos: List[Tuple[str, bytes]], pct_compra: float = 0.0
    ) -> str:
        if not archivos:
            raise ValueError("Lote sin archivos")
        lote = LoteOCR(
            id=str(uuid.uuid4())[:8],
            mes=mes,
            proveedor=proveedor,
            pct_compra=pct_compra,
            archivos=[TrabajoArchivo(nombre=n, datos=d) for n, d in archivos],
        )
        with self._lock:
            self._lotes[lote.id] = lote
        for trabajo in lote.archivos:
            self._pool.submit(self._procesar, lote.id, trabajo)
        return lote.id

    def _procesar(self, lote_id: str, trabajo: TrabajoArchivo) -> None:
        with self._lock:
            lote = self._lotes.get(lote_id)
        if lote is None:
            return
        trabajo.estado = "PROCESANDO"
        try:
            datos = procesar_archivo(trabajo.datos, trabajo.nombre)
            trabajo.resultado = datos
            if str(datos.get("Observaciones", "")).startswith("ERROR:"):
                trabajo.error = str(datos.get("Observaciones", ""))[7:]
                trabajo.estado = "ERROR"
                return
            registro = self._registro_de_datos(datos, lote)
            clave = _clave_dedup(registro)
            if any(clave) and db.existe_duplicado(*clave):
                trabajo.estado = "DUPLICADO"
                return
            tipo = _detectar_tipo(trabajo.datos, trabajo.nombre)
            registro["Ruta_Archivo"] = archivos.guardar_archivo_original(
                lote.mes,
                lote.proveedor,
                trabajo.nombre,
                trabajo.datos,
                tipo,
                registro.get("Nro_Factura", ""),
            )
            db.registrar_facturas_batch(lote.mes, [registro])
            trabajo.estado = "OK"
            self._auto_venta(lote, [registro])
        except Exception as e:
            trabajo.error = str(e)
            trabajo.estado = "ERROR"

    def _auto_venta(self, lote: LoteOCR, registros: List[dict]) -> None:
        """Crea o incrementa la venta al COMPRADOR de cada factura.

        Si la IA no extrajo Razon_Social_Cliente, no se crea venta: la factura
        queda sin venta para asignación manual."""
        por_cliente = {}
        for r in registros:
            cliente = (r.get("Razon_Social_Cliente") or "").strip()
            fid = r.get("ID")
            if not cliente or not fid:
                continue
            nit = str(r.get("NIT_Cliente") or "")
            por_cliente.setdefault((cliente, nit), []).append(fid)
        for (cliente, nit), ids in por_cliente.items():
            try:
                resultado = None
                for intento in range(3):
                    try:
                        resultado = db.auto_venta_de_facturas(
                            lote.mes, cliente, nit, ids, notas=f"Lote {lote.id} · {lote.proveedor}"
                        )
                        break
                    except Exception:
                        if intento < 2:
                            time.sleep(0.4 * (intento + 1))
                if not resultado:
                    continue
                with self._lock:
                    previa = lote.ventas_creadas.get(resultado["cliente"])
                    if previa:
                        previa["precio"] = round(previa["precio"] + resultado["precio"], 2)
                    else:
                        lote.ventas_creadas[resultado["cliente"]] = {
                            "cliente": resultado["cliente"],
                            "precio": resultado["precio"],
                        }
            except Exception:
                continue

    def _registro_de_datos(self, datos: dict, lote: LoteOCR) -> dict:
        registro = {
            "Nombre_Archivo": datos.get("Nombre_Archivo", ""),
            "Proveedor_Asignado": lote.proveedor,
            "Porcentaje_Compra": lote.pct_compra,
            "Estado_Pago": "PENDIENTE",
            "Venta_ID": "",
        }
        registro.update(datos)
        registro.pop("_cache", None)
        registro.pop("nombre_archivo", None)
        return registro

    def resumen_lotes(self) -> List[dict]:
        with self._lock:
            lotes = list(self._lotes.values())
        return [l.resumen() for l in sorted(lotes, key=lambda x: x.id, reverse=True)]

    def hay_activos(self) -> bool:
        with self._lock:
            return any(
                a.estado in ESTADOS_ACTIVOS
                for lote in self._lotes.values()
                for a in lote.archivos
            )

    def guardar_duplicado(self, lote_id: str, indice: int) -> bool:
        with self._lock:
            lote = self._lotes.get(lote_id)
            trabajo = lote.archivos[indice] if lote and 0 <= indice < len(lote.archivos) else None
        if not lote or not trabajo or trabajo.estado != "DUPLICADO" or not trabajo.resultado:
            return False
        registro = self._registro_de_datos(trabajo.resultado, lote)
        tipo = "pdf"
        try:
            tipo = _detectar_tipo(trabajo.datos, trabajo.nombre)
        except Exception:
            pass

        clave = _clave_dedup(registro)
        existente = None
        if any(clave):
            for f in db.leer_facturas_mes(lote.mes):
                if _clave_dedup(f) == clave:
                    existente = f
                    break

        if existente:
            ruta = archivos.guardar_archivo_original(
                lote.mes,
                lote.proveedor,
                trabajo.nombre,
                trabajo.datos,
                tipo,
                registro.get("Nro_Factura", ""),
            )
            existente["Ruta_Archivo"] = ruta
            if not existente.get("Fecha_Emision") and registro.get("Fecha_Emision"):
                existente["Fecha_Emision"] = registro["Fecha_Emision"]
            if not existente.get("Cod_Autorizacion") and registro.get("Cod_Autorizacion"):
                existente["Cod_Autorizacion"] = registro["Cod_Autorizacion"]
            db.actualizar_factura(lote.mes, existente)
            trabajo.estado = "OK"
            trabajo.resultado["_adjuntado"] = True
            return True

        registro["Ruta_Archivo"] = archivos.guardar_archivo_original(
            lote.mes,
            lote.proveedor,
            trabajo.nombre,
            trabajo.datos,
            tipo,
            registro.get("Nro_Factura", ""),
        )
        db.registrar_facturas_batch(lote.mes, [registro])
        trabajo.estado = "OK"
        self._auto_venta(lote, [registro])
        return True

    def descartar_archivo(self, lote_id: str, indice: int) -> bool:
        with self._lock:
            lote = self._lotes.get(lote_id)
            trabajo = lote.archivos[indice] if lote and 0 <= indice < len(lote.archivos) else None
        if not trabajo or trabajo.estado in ESTADOS_ACTIVOS:
            return False
        trabajo.estado = "DESCARTADO"
        return True

    def reintentar_archivo(self, lote_id: str, indice: int) -> bool:
        with self._lock:
            lote = self._lotes.get(lote_id)
            trabajo = lote.archivos[indice] if lote and 0 <= indice < len(lote.archivos) else None
        if not lote or not trabajo or trabajo.estado in ESTADOS_ACTIVOS:
            return False
        trabajo.estado = "EN_COLA"
        trabajo.error = ""
        self._pool.submit(self._procesar, lote.id, trabajo)
        return True

    def limpiar_completados(self) -> int:
        with self._lock:
            ids = [
                lid
                for lid, lote in self._lotes.items()
                if all(a.estado not in ESTADOS_ACTIVOS for a in lote.archivos)
            ]
            for lid in ids:
                del self._lotes[lid]
        return len(ids)


COLA = ColaOCR()
