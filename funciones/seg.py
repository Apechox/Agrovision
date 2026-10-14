"""
MÓDULO DE SEGMENTACIÓN (Actividad A2.3)

¿CÓMO TRABAJAR AQUÍ?
1. En `process()`, reemplaza los umbrales HSV de prueba por los valores reales
   que separen el tomate del fondo de la cinta transportadora.
2. Revisa la validación `is_valid_mask`. Si dos tomates vienen pegados (área muy grande
   o baja circularidad), márcalos o sepáralos con Watershed/erosión para tu informe de fallos.

El método `process(frame)` SIEMPRE debe devolver `(clean_mask, instances)`, donde `instances`
es una lista de diccionarios con exactamente estas llaves:
    {
        "bbox": (x, y, w, h),       # int: Caja delimitadora en píxeles
        "centroid": (cx, cy),       # int: Centro del tomate (x, y)
        "area_px": float,           # Área en píxeles
        "contour": np.ndarray,      # Contorno de OpenCV
        "is_valid_mask": bool       # False si toca el borde de la imagen o está incompleto
    }
"""

import cv2
import numpy as np

class ClassicSegmenter:
    def __init__(self, kernel_size=5, min_area_px=500):
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        self.min_area_px = min_area_px

    def process(self, frame):
        # 1. Convertir de BGR a HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # =====================================================================
        # Ajustar umbrales del fondo/tomate
        # =====================================================================
        lower_bound = np.array([0, 70, 50])
        upper_bound = np.array([180, 255, 255])
        raw_mask = cv2.inRange(hsv, lower_bound, upper_bound)

        # Limpieza morfológica (elimina ruido blanco y rellena huecos negros)
        clean_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, self.kernel)
        clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_CLOSE, self.kernel)

        # 2. Encontrar contornos de cada tomate
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        instances = []
        h_img, w_img = frame.shape[:2]

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area_px:
                continue  # Ignorar basura pequeña

            x, y, w, h = cv2.boundingRect(cnt)
            M = cv2.moments(cnt)
            cx = int(M["m10"] / M["m00"]) if M["m00"] != 0 else x + w // 2
            cy = int(M["m01"] / M["m00"]) if M["m00"] != 0 else y + h // 2

            # =====================================================================
            # Validar recortes y contactos
            # =====================================================================
            # Si el tomate toca los bordes de la cámara, está cortado -> máscara inválida
            touching_border = (x <= 2) or (y <= 2) or (x + w >= w_img - 2) or (y + h >= h_img - 2)

            instances.append({
                "bbox": (x, y, w, h),
                "centroid": (cx, cy),
                "area_px": float(area),
                "contour": cnt,
                "is_valid_mask": not touching_border
            })

        return clean_mask, instances
