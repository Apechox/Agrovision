"""
MÓDULO DE SEGMENTACIÓN

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
    def __init__(self, kernel_size=5, min_area_px=500, hsv_lower=(0, 70, 50),
                 hsv_upper=(179, 255, 255), rangos_extra=None,
                 fondo_referencia=None, umbral_diferencia=30,
                 separar_contacto=False, ajuste_pico=0.5,
                 kernel_size_cierre=None):
        """
        hsv_lower/hsv_upper: rango de color principal a buscar.
        rangos_extra: lista opcional de (lower, upper) adicionales -- se combinan con OR
            entre sí y con el rango principal (p.ej. para buscar rojo Y verde a la vez).
        fondo_referencia: imagen BGR del fondo vacío (opcional). Si se da, además de
            cumplir el color, el píxel debe ser distinto a este fondo (AND). Sin esto,
            la segmentación es solo por color, igual que antes.
        umbral_diferencia: solo se usa si se da `fondo_referencia` -- diferencia mínima
            (0-255) para considerar un píxel "distinto al fondo".
        kernel_size_cierre: tamaño del kernel para el CIERRE (rellenar huecos/puentear
            un tallo o rama que corta a la fruta en 2), por separado del de APERTURA
            (`kernel_size`, que solo saca ruido). Si no se da, usa el mismo que
            `kernel_size`. Conviene agrandar SOLO este, no los dos juntos -- agrandar
            también la apertura erosiona el contorno real de la fruta (ver
            docs/segmentacion.md, sección 6, la comparación de ambos enfoques).
        """
        self.kernel_apertura = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        k_cierre = kernel_size_cierre if kernel_size_cierre is not None else kernel_size
        self.kernel_cierre = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_cierre, k_cierre))
        self.min_area_px = min_area_px
        self.rangos = [(np.array(hsv_lower), np.array(hsv_upper))]
        if rangos_extra:
            self.rangos += [(np.array(lo), np.array(hi)) for lo, hi in rangos_extra]
        self.fondo_referencia = fondo_referencia
        self.umbral_diferencia = umbral_diferencia
        self.separar_contacto = separar_contacto
        self.ajuste_pico = ajuste_pico  # 0-1: que fraccion de la distancia maxima al
                                         # borde se exige para considerar "centro seguro"
                                         # de un tomate. Mas alto = corta mas facil pero
                                         # arriesga partir un tomate sano en 2.

    def process(self, frame):
        _, clean_mask, instances = self.process_with_masks(frame)
        return clean_mask, instances

    def _mascara_color(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mascara = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lo, hi in self.rangos:
            mascara = cv2.bitwise_or(mascara, cv2.inRange(hsv, lo, hi))
        return mascara

    def _mascara_fondo(self, frame):
        diff = cv2.absdiff(frame, self.fondo_referencia)
        diff_gris = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, mascara = cv2.threshold(diff_gris, self.umbral_diferencia, 255, cv2.THRESH_BINARY)
        return mascara

    def _separar_contornos_tocando(self, clean_mask, frame):
        """Watershed sobre la mascara: usa la distancia de cada pixel al borde mas
        cercano para encontrar un 'centro seguro' por tomate, y corta en el valle entre
        dos centros que estan pegados. Devuelve una lista de contornos (uno por tomate
        ya separado), en vez de un contorno por blob conectado."""
        dist = cv2.distanceTransform(clean_mask, cv2.DIST_L2, 5)
        if dist.max() == 0:
            return []
        _, picos = cv2.threshold(dist, self.ajuste_pico * dist.max(), 255, 0)
        picos = picos.astype(np.uint8)

        n_picos, marcadores = cv2.connectedComponents(picos)
        if n_picos <= 1:
            return []  # no hay ni un "centro seguro" -- no se puede separar nada

        zona_dudosa = cv2.subtract(clean_mask, picos)
        marcadores = marcadores + 1
        marcadores[zona_dudosa == 255] = 0

        cv2.watershed(frame, marcadores)

        contornos = []
        for etiqueta in range(2, n_picos + 2):
            mascara_etiqueta = np.uint8(marcadores == etiqueta) * 255
            cnts, _ = cv2.findContours(mascara_etiqueta, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contornos.extend(cnts)
        return contornos

    def process_with_masks(self, frame):
        """Devuelve la máscara inicial, la máscara limpia y las detecciones."""
        raw_mask = self._mascara_color(frame)
        if self.fondo_referencia is not None:
            raw_mask = cv2.bitwise_and(raw_mask, self._mascara_fondo(frame))

        # Limpieza morfológica (elimina ruido blanco y rellena huecos negros)
        clean_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, self.kernel_apertura)
        clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_CLOSE, self.kernel_cierre)

        # 2. Encontrar contornos de cada tomate
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if self.separar_contacto:
            contornos_separados = self._separar_contornos_tocando(clean_mask, frame)
            if contornos_separados:
                contours = contornos_separados

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

        return raw_mask, clean_mask, instances
