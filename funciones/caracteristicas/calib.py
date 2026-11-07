"""
MÓDULO DE CALIBRACIÓN (Actividad A2.5)

¿CÓMO TRABAJAR AQUÍ?
1. Mide un objeto patrón (o un tomate con pie de metro) en el video a la altura fija definida.
2. Calcula cuántos píxeles mide de ancho en la imagen y divídelo por su medida real en milímetros.
3. Actualiza ese valor en el archivo `config/calib.json` bajo la llave `"px_per_mm"`.
"""

import json
import os

class Calibrator:
    def __init__(self, config_path="config/calib.json"):
        self.scale_px_per_mm = 8.5  # Valor por defecto
        self.valid_roi = [50, 50, 540, 380]  # [x, y, ancho, alto]

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.scale_px_per_mm = config.get("px_per_mm", self.scale_px_per_mm)
                self.valid_roi = config.get("valid_zone_bbox", self.valid_roi)

    def pixels_to_mm(self, width_px):
        """Convierte un ancho en píxeles a milímetros usando la escala calibrada."""
        if self.scale_px_per_mm <= 0:
            raise ValueError("Escala de calibración inválida (debe ser > 0).")
        return round(width_px / self.scale_px_per_mm, 2)

    def is_inside_valid_zone(self, centroid):
        """Verifica si el centroide (cx, cy) del tomate está dentro de la zona sin distorsión."""
        cx, cy = centroid
        rx, ry, rw, rh = self.valid_roi
        return (rx <= cx <= rx + rw) and (ry <= cy <= ry + rh)
