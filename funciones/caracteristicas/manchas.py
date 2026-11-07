"""M5 · Atributos superficiales: manchas oscuras (RF5, A3.2).

Una mancha es una región conectada, dentro de la máscara de UN tomate, que se aparta del
color sano del fruto (mediana de la propia máscara) por alguna de dos vías:
  - más OSCURA:       V < v_relativo_max · mediana(V)      (lesiones, hongos oscuros)
  - más DESATURADA:   S < s_relativo_max · mediana(S)      (moho gris/blanquecino, tejido pálido)
No se cuentan como defecto:
  - reflejos especulares: casi blancos (V alto y S muy baja); se excluyen del área evaluable,
  - el anillo del borde (oscurecimiento natural por curvatura/sombra),
  - ruido menor al área mínima (apertura morfológica + filtro por área).

defect_ratio = área de manchas / área evaluable.
Etiquetas: Sin manchas / Con manchas / No evaluable / No aplica.
"""
import cv2
import numpy as np

from funciones.caracteristicas.perfiles import Perfil, NO_APLICA, NO_EVALUABLE
from funciones.caracteristicas.util_mascara import mascara_binaria, mascara_reflejos, erosionar, apertura, cierre


class DarkSpotDetector:
    def __init__(self, perfil=None):
        self.perfil = perfil or Perfil.cargar("tomate")
        self.cfg = self.perfil.seccion("manchas")

    @staticmethod
    def _resultado(label, causa=None, ratio=None, regiones=None, n_eval=0):
        return {"label": label, "defect_ratio": ratio, "regiones": regiones or [],
                "n_regiones": len(regiones or []), "pixeles_evaluables": n_eval,
                "causa": causa}

    def process(self, frame, mask):
        if not self.perfil.aplica("manchas"):
            return self._resultado(NO_APLICA, "El perfil no define manchas")

        cfg = self.cfg
        mask = mascara_binaria(mask)
        area = int(cv2.countNonZero(mask))
        if area == 0:
            return self._resultado(NO_EVALUABLE, "Máscara vacía")

        interior = erosionar(mask, cfg["erosion_borde_px"])
        k = int(cfg.get("suavizado_px", 0))
        base = cv2.GaussianBlur(frame, (k, k), 0) if k > 1 else frame  # reduce moteado/ruido
        hsv = cv2.cvtColor(base, cv2.COLOR_BGR2HSV)
        ex = cfg["excluir"]
        reflejos = mascara_reflejos(hsv, ex["reflejo_s_max"], ex["reflejo_v_min"],
                                    ex.get("dilatar_reflejo_px", 0))
        evaluable = (interior > 0) & (reflejos == 0)
        n_eval = int(evaluable.sum())

        if n_eval < cfg["min_pixeles_evaluables"]:
            return self._resultado(NO_EVALUABLE, "Pocos píxeles evaluables", n_eval=n_eval)
        if n_eval / area < cfg["min_fraccion_evaluable"]:
            return self._resultado(NO_EVALUABLE, "Reflejos/borde cubren gran parte del fruto",
                                   n_eval=n_eval)

        v = hsv[..., 2].astype(np.float32)
        sat = hsv[..., 1].astype(np.float32)
        v_ref = float(np.median(v[evaluable]))
        s_ref = float(np.median(sat[evaluable]))
        candidato = v < cfg["v_relativo_max"] * v_ref
        if cfg.get("s_relativo_max"):
            candidato |= sat < cfg["s_relativo_max"] * s_ref
        oscuro = (evaluable & candidato).astype(np.uint8) * 255
        oscuro = cierre(oscuro, cfg.get("cierre_px", 0))  # une fragmentos de una misma mancha
        oscuro = apertura(oscuro, cfg["apertura_px"])

        contornos, _ = cv2.findContours(oscuro, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regiones, px_mancha = [], 0
        for c in contornos:
            a = cv2.contourArea(c)
            if a >= cfg["area_min_mancha_px"]:
                regiones.append(c)
                px_mancha += int(a)

        ratio = min(px_mancha / n_eval, 1.0)
        label = "Con manchas" if ratio >= cfg["umbral_con_manchas"] else "Sin manchas"
        return self._resultado(label, None, round(ratio, 4), regiones, n_eval)