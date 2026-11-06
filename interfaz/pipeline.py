"""
ADAPTADOR ENTRE LA INTERFAZ Y LOS MÓDULOS DE VISIÓN DISPONIBLES

Usa solo lo que existe hoy en el repo: `funciones/seg.py` (segmentación),
`funciones/track.py` (seguimiento) y `funciones/calib.py` (calibración).

Madurez visual y manchas (A3.1 / A3.2) NO están integradas todavía: sus campos
salen como PENDIENTE. Cuando existan `funciones/madurez.py` y `funciones/manchas.py`
solo hay que completar `_observar()`; la interfaz no necesita cambios.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from funciones.calib import Calibrator
from funciones.seg import ClassicSegmenter

try:  # la rama de seguimiento mueve track.py a funciones/tracking/
    from funciones.tracking.track import CentroidTracker
except ImportError:
    from funciones.track import CentroidTracker

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_CALIB = RAIZ / "config" / "calib.json"

PENDIENTE = "Pendiente"
NO_EVALUABLE = "No evaluable"

# Cortes PROVISIONALES de calibre (mm) solo para clasificar y graficar.
# Los oficiales por perfil se fijan en A3.3 y deben reemplazar estos valores.
LIMITE_PEQUENO_MM = 55
LIMITE_MEDIANO_MM = 70

VERDE = (0, 200, 0)
NARANJA = (0, 140, 255)
AZUL = (255, 160, 0)


def clasificar_calibre(ancho_mm):
    if ancho_mm is None:
        return NO_EVALUABLE
    if ancho_mm < LIMITE_PEQUENO_MM:
        return "Pequeño"
    if ancho_mm < LIMITE_MEDIANO_MM:
        return "Mediano"
    return "Grande"


@dataclass
class Observacion:
    id: int | None
    bbox: tuple
    centroid: tuple
    contour: object
    valida: bool
    en_zona: bool
    ancho_px: int
    ancho_mm: float | None = None
    calibre: str = NO_EVALUABLE
    estado_calibre: str = NO_EVALUABLE
    madurez: str = PENDIENTE
    manchas: str = PENDIENTE
    dist_centro: float = float("inf")
    causa: str = ""

    @property
    def validez(self):
        if not self.valida:
            return self.causa or "Máscara no válida"
        if not self.en_zona:
            return "Fuera de zona de medición"
        return "Válida"


@dataclass
class ResultadoCuadro:
    anotado: object
    observaciones: list = field(default_factory=list)
    ids_activos: set = field(default_factory=set)
    mascara_hsv: object = None      # umbral HSV crudo (etapa 1)
    mascara_limpia: object = None   # tras apertura y cierre (etapa 2)


def leer_imagen(ruta):
    """cv2.imread falla con rutas con tildes en Windows; imdecode no."""
    datos = np.fromfile(str(ruta), dtype=np.uint8)
    return cv2.imdecode(datos, cv2.IMREAD_COLOR) if datos.size else None


class PipelineInspeccion:
    def __init__(self):
        self.segmentador = ClassicSegmenter()
        self.seguidor = CentroidTracker()
        self.calibrador = Calibrator(str(CONFIG_CALIB))
        self.calibracion_validada = False
        self.distancia_camara_cm = None  # distancia cámara-superficie, de "camera_height_mm" en calib.json
        try:
            with open(CONFIG_CALIB, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.calibracion_validada = bool(config.get("validated", False))
            altura_mm = config.get("camera_height_mm")
            if isinstance(altura_mm, (int, float)):
                self.distancia_camara_cm = altura_mm / 10
        except (OSError, ValueError):
            pass  # sin config legible: se queda como "no validada"

    @property
    def version_calibracion(self):
        validada = "sí" if self.calibracion_validada else "no"
        roi = [int(v) for v in self.calibrador.valid_roi]
        dist = f"; dist_cm={self.distancia_camara_cm:g}" if self.distancia_camara_cm is not None else ""
        return f"px_per_mm={self.calibrador.scale_px_per_mm}; validada={validada}; roi={roi}{dist}"

    @property
    def estado_calibracion(self):
        return "Calibrado" if self.calibracion_validada else "Estimado (calibración pendiente de validar)"

    def procesar(self, frame):
        mascara_hsv, mascara_limpia, instancias = self.segmentador.process_with_masks(frame)
        seguidas = self.seguidor.update(instancias)
        observaciones = [self._observar(o) for o in seguidas]
        for inst in instancias:
            if not inst["is_valid_mask"]:
                observaciones.append(Observacion(
                    id=None, bbox=inst["bbox"], centroid=inst["centroid"],
                    contour=inst["contour"], valida=False, en_zona=False,
                    ancho_px=inst["bbox"][2], causa="Cortado por el borde de la imagen"))
        return ResultadoCuadro(self._anotar(frame, observaciones), observaciones,
                               set(self.seguidor.objects), mascara_hsv, mascara_limpia)

    def _observar(self, obj):
        ancho_px = obj["bbox"][2]
        en_zona = self.calibrador.is_inside_valid_zone(obj["centroid"])
        obs = Observacion(id=obj["id"], bbox=obj["bbox"], centroid=obj["centroid"],
                          contour=obj["contour"], valida=True, en_zona=en_zona,
                          ancho_px=ancho_px)
        rx, ry, rw, rh = self.calibrador.valid_roi
        obs.dist_centro = math.hypot(obj["centroid"][0] - (rx + rw / 2),
                                     obj["centroid"][1] - (ry + rh / 2))
        if en_zona:  # RF9: solo se mide dentro de la zona calibrada
            obs.ancho_mm = self.calibrador.pixels_to_mm(ancho_px)
            obs.calibre = clasificar_calibre(obs.ancho_mm)
            obs.estado_calibre = self.estado_calibracion
        return obs

    def _anotar(self, frame, observaciones):
        img = frame.copy()
        rx, ry, rw, rh = self.calibrador.valid_roi
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), AZUL, 1)
        cv2.putText(img, "Zona de medicion", (rx + 4, ry + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, AZUL, 1)
        for o in observaciones:
            x, y, _, _ = o.bbox
            color = VERDE if (o.valida and o.en_zona) else NARANJA
            cv2.drawContours(img, [o.contour], -1, color, 2)
            if o.id is None:
                texto = "Cortado por borde"
            elif o.ancho_mm is not None:
                texto = f"ID {o.id} | {o.ancho_mm:.1f} mm"
            else:
                texto = f"ID {o.id} | fuera de zona"
            cv2.putText(img, texto, (x, max(18, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        return img
