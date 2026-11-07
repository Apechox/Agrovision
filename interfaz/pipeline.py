"""
ADAPTADOR ENTRE LA INTERFAZ Y LOS MÓDULOS DE VISIÓN

Usa segmentación (`seg`), seguimiento (`track`) y calibración (`calib`), y calcula calibre,
peso, madurez y manchas con los MISMOS evaluadores que `main_test.py`
(`evaluate_instances` + perfil `config/perfiles/<tipo>.json`), de modo que la interfaz y la
línea de comandos entregan siempre el mismo resultado.

Solo se mide dentro de la zona de medición (RF9). Fuera de ella, o con la máscara cortada
por el borde, madurez y manchas quedan en "—" (el registro las guarda vacías, nunca en cero).
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from funciones.caracteristicas.calib import Calibrator
from funciones.caracteristicas.perfiles import Perfil
from funciones.segmentación.seg import ClassicSegmenter
from main_test import Evaluadores, evaluate_instances  # misma lógica que la línea de comandos

try:  # la rama de seguimiento mueve track.py a funciones/tracking/
    from funciones.tracking.track import CentroidTracker
except ImportError:
    from funciones.tracking.track import CentroidTracker

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_CALIB = RAIZ / "config" / "calib.json"

PENDIENTE = "Pendiente"      # se conserva por compatibilidad; ya no se usa como valor
SIN_MEDIR = "—"              # fuera de zona o máscara cortada: no se mide
NO_EVALUABLE = "No evaluable"
ESTADOS_SIN_CATEGORIA = ("Fuera de rango", "No evaluable", "No aplica")

# Cortes PROVISIONALES antiguos. YA NO SE USAN: las categorías de calibre salen del perfil
# (config/perfiles/<tipo>.json, A3.3). Se dejan solo por si otro módulo importa la función.
LIMITE_PEQUENO_MM = 55
LIMITE_MEDIANO_MM = 70

VERDE = (0, 200, 0)
NARANJA = (0, 140, 255)
AZUL = (255, 160, 0)


def clasificar_calibre(ancho_mm):  # obsoleta: ver comentario arriba
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
    madurez: str = SIN_MEDIR
    manchas: str = SIN_MEDIR
    dist_centro: float = float("inf")
    causa: str = ""
    # --- datos reales del análisis (los lee el registro; vacío = no calculado) ---
    tipo: str = "tomate"
    peso_g: float | None = None
    peso_estado: str = ""
    c_ratio: float | None = None
    r_ratio: float | None = None
    defect_ratio: float | None = None
    calibre_causa: str = ""
    altura_corregida: bool = False
    perfil_version: str = ""
    peso_modelo_version: str = ""
    incidencia: str = ""

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
    def __init__(self, perfil="tomate"):
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
        # Los evaluadores leen el estado de validación del calibrador.
        self.calibrador.validated = self.calibracion_validada
        # OJO: la distancia de cámara NO se aplica como corrección de altura de forma automática
        # (si px_per_mm se calibró con un tomate, se corregiría dos veces). Para activarla, fijar
        # `altura_camara_mm` en el perfil y calibrar px_per_mm sobre el plano de la mesa.
        self.perfil = Perfil.cargar(perfil)
        self.ev = Evaluadores(self.perfil, self.calibrador, "interfaz")

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
        observaciones = self._observar_todas(frame, seguidas)
        for inst in instancias:
            if not inst["is_valid_mask"]:
                observaciones.append(Observacion(
                    id=None, bbox=inst["bbox"], centroid=inst["centroid"],
                    contour=inst["contour"], valida=False, en_zona=False,
                    ancho_px=inst["bbox"][2], causa="Cortado por el borde de la imagen"))
        return ResultadoCuadro(self._anotar(frame, observaciones), observaciones,
                               set(self.seguidor.objects), mascara_hsv, mascara_limpia)

    def _observar_todas(self, frame, seguidas):
        """Calcula los atributos solo de los tomates dentro de la zona de medición (RF9)."""
        en_zona = [self.calibrador.is_inside_valid_zone(o["centroid"]) for o in seguidas]
        medibles = [o for o, z in zip(seguidas, en_zona) if z]
        resultados = iter(evaluate_instances(frame, medibles, self.ev) if medibles else [])
        return [self._observar(o, next(resultados) if z else None) for o, z in zip(seguidas, en_zona)]

    def _observar(self, obj, r):
        ancho_px = obj["bbox"][2]
        obs = Observacion(id=obj["id"], bbox=obj["bbox"], centroid=obj["centroid"],
                          contour=obj["contour"], valida=True, en_zona=r is not None,
                          ancho_px=ancho_px)
        rx, ry, rw, rh = self.calibrador.valid_roi
        obs.dist_centro = math.hypot(obj["centroid"][0] - (rx + rw / 2),
                                     obj["centroid"][1] - (ry + rh / 2))
        if r is None:  # fuera de zona: no se mide
            return obs

        cal, pes, mad, man = r["calibre"], r["peso"], r["madurez"], r["manchas"]
        obs.tipo = self.perfil.tipo
        obs.ancho_mm = cal["ancho_mm"]
        obs.calibre = cal["categoria"] or (cal["estado"] if cal["estado"] in ESTADOS_SIN_CATEGORIA
                                           else NO_EVALUABLE)
        # Con medida válida o provisional se conserva el texto de siempre de la interfaz
        # ("Calibrado" / "Estimado (calibración pendiente de validar)").
        obs.estado_calibre = (cal["estado"] if cal["estado"] in ESTADOS_SIN_CATEGORIA
                              else self.estado_calibracion)
        obs.calibre_causa = cal["causa"] or ""
        obs.altura_corregida = cal["altura_corregida"]
        obs.peso_g, obs.peso_estado = pes["peso_g"], pes["estado"]
        obs.peso_modelo_version = pes["modelo_version"] or ""
        obs.madurez, obs.c_ratio, obs.r_ratio = mad["label"], mad["c_ratio"], mad["r_ratio"]
        obs.manchas, obs.defect_ratio = man["label"], man["defect_ratio"]
        obs.perfil_version = self.perfil.version
        causas = [f"{etq}: {txt}" for etq, txt in (
            ("Calibre", cal["causa"]), ("Peso", pes["causa"]),
            ("Madurez", mad.get("causa")), ("Manchas", man.get("causa"))) if txt]
        obs.incidencia = "; ".join(causas)
        return obs

    def _anotar(self, frame, observaciones):
        """Modo interfaz: solo el ID. El detalle va en las tablas y en el CSV. Un tomate
        cortado por el borde solo cambia el color del contorno, sin texto."""
        img = frame.copy()
        rx, ry, rw, rh = self.calibrador.valid_roi
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), AZUL, 1)
        cv2.putText(img, "Zona de medicion", (rx + 4, ry + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, AZUL, 1)
        for o in observaciones:
            x, y, _, _ = o.bbox
            color = VERDE if (o.valida and o.en_zona) else NARANJA
            cv2.drawContours(img, [o.contour], -1, color, 2)
            if o.id is not None:
                cv2.putText(img, f"ID {o.id}", (x, max(18, y - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        return img