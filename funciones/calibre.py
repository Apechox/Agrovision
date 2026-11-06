"""M4 · Calibre aparente y clasificación por perfil (RF4, A2.5 + A3.3).

Convierte la dimensión visible del tomate a mm con la escala del Calibrator y la
clasifica según los intervalos del perfil. No es el diámetro máximo 3D.

Efecto de la altura (sección 5.4): la escala px/mm del Calibrator corresponde al plano
de la cinta. La parte más ancha de un fruto casi esférico está a h ≈ d/2 sobre la cinta,
por lo que se ve ampliada por H / (H - h). Con H = altura de la cámara sobre la cinta
(perfil: calibre.altura_camara_mm) se resuelve en forma cerrada:

        d = d0 / (1 + d0 / (2 H)),      d0 = ancho_px / escala_cinta

Si H es null, NO se corrige y el resultado se marca como "sin corrección de altura".

Estados: Válido | Provisional | No evaluable | Fuera de rango
  - Provisional: hay medida, pero la calibración aún no se validó con pie de metro
    (Calibrator.validated falsy). La medida se entrega, marcada como tal.
"""
import cv2

from funciones.perfiles import Perfil, NO_APLICA, NO_EVALUABLE, FUERA_DE_RANGO

PROVISIONAL = "Provisional (calibración pendiente de validar con pie de metro)"
VALIDO = "Válido"


class CalibreEvaluator:
    def __init__(self, perfil=None):
        self.perfil = perfil or Perfil.cargar("tomate")
        self.cfg = self.perfil.seccion("calibre")

    @staticmethod
    def _res(estado, causa=None, ancho=None, categoria=None, en_zona=True,
             validada=False, altura=False):
        return {"ancho_mm": ancho, "estado": estado, "categoria": categoria,
                "causa": causa, "en_zona_medicion": en_zona,
                "calibracion_validada": validada, "altura_corregida": altura}

    def _dimension_px(self, obj):
        modo = self.cfg.get("dimension", "ancho_bbox")
        if modo == "lado_menor_rect":
            (_, _), (w, h), _ = cv2.minAreaRect(obj["contour"])
            return float(min(w, h))
        _, _, bw, _ = obj["bbox"]
        return float(bw)

    def clasificar(self, ancho_mm):
        """Categoría según el perfil. Intervalos [min, max); el último incluye su máximo."""
        cats = self.cfg["categorias"]
        for i, c in enumerate(cats):
            ultimo = i == len(cats) - 1
            if c["min_mm"] <= ancho_mm < c["max_mm"] or (ultimo and ancho_mm == c["max_mm"]):
                return c["nombre"]
        return None

    def evaluate(self, obj, calibrator):
        if not self.perfil.aplica("calibre"):
            return self._res(NO_APLICA, "El perfil no define calibre", en_zona=True)

        if not calibrator.is_inside_valid_zone(obj["centroid"]):
            return self._res(FUERA_DE_RANGO, "Fuera de la zona de medición", en_zona=False)

        if obj.get("is_valid_mask") is False:
            return self._res(NO_EVALUABLE, "Máscara recortada o ambigua")

        escala = getattr(calibrator, "scale_px_per_mm", None)
        if not escala or escala <= 0:
            return self._res(NO_EVALUABLE, "Sin escala px/mm")

        d = float(calibrator.pixels_to_mm(self._dimension_px(obj)))
        H = self.cfg.get("altura_camara_mm")
        corregida = False
        if H:
            d = d / (1.0 + d / (2.0 * H))
            corregida = True
        d = round(d, 2)

        validada = bool(getattr(calibrator, "validated", False))
        lo, hi = self.cfg["rango_validado_mm"]
        if not lo <= d <= hi:
            return self._res(FUERA_DE_RANGO, f"{d} mm fuera de [{lo}, {hi}] mm", ancho=d,
                             validada=validada, altura=corregida)

        return self._res(VALIDO if validada else PROVISIONAL,
                         None if corregida else "Sin corrección de altura",
                         ancho=d, categoria=self.clasificar(d),
                         validada=validada, altura=corregida)
