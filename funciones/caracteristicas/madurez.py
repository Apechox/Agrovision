"""M5 · Madurez visual por color (RF3, A3.1).

Descriptores dentro de la máscara de UN tomate:
    C = proporción de píxeles de color de transición (amarillo/naranja)
    R = proporción de píxeles rojos
    G = proporción de píxeles verdes
calculadas sobre los píxeles válidos (sin sombras ni reflejos).

Etiquetas: Verde / En transición / Maduro / No evaluable / No aplica.
Los umbrales vienen del perfil (config/perfiles/<tipo>.json); no se trasladan a otros tipos.
"""
import cv2
import numpy as np

from funciones.caracteristicas.perfiles import Perfil, NO_APLICA, NO_EVALUABLE
from funciones.caracteristicas.util_mascara import mascara_binaria, mascara_reflejos


class ColorMaturityClassifier:
    def __init__(self, perfil=None):
        self.perfil = perfil or Perfil.cargar("tomate")
        self.cfg = self.perfil.seccion("madurez")

    @staticmethod
    def _resultado(label, causa=None, c=None, r=None, g=None, n_validos=0):
        return {"label": label, "c_ratio": c, "r_ratio": r, "g_ratio": g,
                "pixeles_validos": n_validos, "causa": causa}

    def process(self, frame, mask):
        if not self.perfil.aplica("madurez"):
            return self._resultado(NO_APLICA, "El perfil no define madurez")

        mask = mascara_binaria(mask)
        area = int(cv2.countNonZero(mask))
        if area == 0:
            return self._resultado(NO_EVALUABLE, "Máscara vacía")

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        ex = self.cfg["excluir"]

        reflejos = mascara_reflejos(hsv, ex["reflejo_s_max"], ex["reflejo_v_min"],
                                    ex.get("dilatar_reflejo_px", 0))
        sombra = (v <= ex["sombra_v_max"])
        dentro = mask > 0
        validos = dentro & (reflejos == 0) & ~sombra
        n_validos = int(validos.sum())

        if n_validos < self.cfg["min_pixeles_validos"]:
            return self._resultado(NO_EVALUABLE, "Pocos píxeles válidos", n_validos=n_validos)
        if n_validos / area < self.cfg["min_fraccion_valida"]:
            return self._resultado(NO_EVALUABLE, "Sombras/reflejos cubren gran parte del fruto",
                                   n_validos=n_validos)

        rj, tr, vd = (self.cfg["hsv"][k] for k in ("rojo", "transicion", "verde"))
        es_rojo = (((h >= rj["h_bajo"][0]) & (h <= rj["h_bajo"][1])) |
                   ((h >= rj["h_alto"][0]) & (h <= rj["h_alto"][1]))) & \
                  (s >= rj["s_min"]) & (v >= rj["v_min"])
        es_trans = (h >= tr["h"][0]) & (h <= tr["h"][1]) & (s >= tr["s_min"]) & (v >= tr["v_min"])
        es_verde = (h >= vd["h"][0]) & (h <= vd["h"][1]) & (s >= vd["s_min"]) & (v >= vd["v_min"])

        r = float((es_rojo & validos).sum()) / n_validos
        c = float((es_trans & validos).sum()) / n_validos
        g = float((es_verde & validos).sum()) / n_validos

        if (r + c + g) < self.cfg.get("min_fraccion_clasificada", 0.5):
            return self._resultado(NO_EVALUABLE, "Color no concluyente para el perfil",
                                   round(c, 4), round(r, 4), round(g, 4), n_validos)

        reglas = self.cfg["reglas"]
        if r >= reglas["maduro_r_min"]:
            label = "Maduro"
        elif c >= reglas["transicion_c_min"] or r >= reglas["transicion_r_min"]:
            label = "En transición"
        else:
            label = "Verde"
        return self._resultado(label, None, round(c, 4), round(r, 4), round(g, 4), n_validos)
