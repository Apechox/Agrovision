"""
SEGMENTADOR POR MODELO ENTRENADO (OE4) — adaptador para enchufar YOLOv8-seg al
mismo pipeline que ya usan ClassicSegmenter / main_test.py / interfaz/pipeline.py.

POR QUÉ EXISTE ESTE ARCHIVO
----------------------------
`funciones/segmentación/seg.py` documenta el contrato que debe cumplir cualquier
segmentador para que el resto del sistema (tracking, calibre, peso, madurez,
manchas, registro) funcione sin tocar una línea más:

    process(frame) -> (clean_mask, instances)
    process_with_masks(frame) -> (raw_mask, clean_mask, instances)

    instances: lista de dicts con exactamente estas llaves:
        bbox          (x, y, w, h)
        centroid      (cx, cy)
        area_px       float
        contour       np.ndarray (contorno de OpenCV, para dibujar/medir)
        is_valid_mask bool (False si el tomate toca el borde de la imagen)

Esta clase (`YoloSegmenter`) implementa ESE MISMO contrato pero usando un modelo
YOLOv8-seg entrenado (ver modelo/README.md para cómo entrenarlo) en vez de
HSV + contornos. Como cumple el mismo contrato, se puede pasar donde hoy se pasa
un ClassicSegmenter sin tocar main_test.py más allá de la instanciación (ver
`parche_main_test.md` en esta misma carpeta).

QUÉ AGREGA ADEMÁS DEL CONTRATO BASE
------------------------------------
YOLO, a diferencia de ClassicSegmenter, SÍ clasifica tipo (las 6 clases de Laboro
Tomato: tamaño × madurez). Por eso cada instancia trae además:
    "tipo_detectado"   str, p.ej. "b_fully_ripened" (o "tomate" si se entrenó con
                        --clase-unica en preparar_dataset.py)
    "confianza"        float 0-1, confianza de YOLO en esa detección
Estas dos llaves NO rompen nada: ClassicSegmenter simplemente no las trae, y el
resto del pipeline (tracking, evaluate_instances) ignora llaves que no conoce
porque accede por nombre (obj["contour"], obj["bbox"], etc.), nunca itera todas
las llaves. Quedan disponibles para:
  - Un futuro cruce con `funciones/caracteristicas/madurez.py` (RNF6: contrastar
    la madurez por color vs. la madurez que ya trae la etiqueta de Laboro Tomato
    — ver modelo/README.md, sección 3, decisión sobre --clase-unica).
  - Selección de perfil (RF2/RF10) el día que haya más de un perfil en
    config/perfiles/ y haga falta decidir cuál aplicar según el tipo detectado.
    Hoy solo existe config/perfiles/tomate.json, así que esto queda listo pero
    sin uso todavía.

QUÉ NO HACE (todavía)
-----------------------
- No reemplaza el tracking, la calibración, el calibre, el peso, la madurez por
  color ni las manchas — esos evaluadores siguen siendo exactamente los mismos
  de funciones/caracteristicas/, llamados igual por evaluate_instances() en
  main_test.py. YOLO solo decide QUÉ es tomate y DÓNDE, igual que hacía
  ClassicSegmenter con HSV + contornos.
- No calcula métricas de precisión/recall/IoU contra ground truth — eso sigue
  siendo evaluar_vs_clasico.py (y su calcular_metricas() sigue como
  NotImplementedError hasta que haya pesos reales, ver ese archivo).
- Requiere pesos entrenados reales (un archivo .pt). Sin --modelo apuntando a un
  .pt real, lanza FileNotFoundError con un mensaje explícito, igual que hace
  evaluar_vs_clasico.py hoy.

CÓMO SE USA (una vez haya un .pt entrenado)
---------------------------------------------
    from modelo.yolo_seg import YoloSegmenter
    segmentador = YoloSegmenter(modelo_path="runs/segment/agrovision_tomate_seg/weights/best.pt")
    # a partir de aquí, se usa exactamente igual que ClassicSegmenter:
    clean_mask, instances = segmentador.process(frame)
"""

from pathlib import Path

import cv2
import numpy as np


class YoloSegmenter:
    def __init__(self, modelo_path, confianza_min=0.25, imgsz=960, device=None):
        """
        modelo_path: ruta a los pesos entrenados (.pt), p.ej.
            "runs/segment/agrovision_tomate_seg/weights/best.pt" que deja
            entrenar_yolo_seg.py al terminar (ver modelo/README.md).
        confianza_min: descarta detecciones de YOLO con confianza menor a esto
            (equivalente a min_area_px en ClassicSegmenter: filtra ruido).
        imgsz: debe ser razonablemente parecido al --imgsz usado al entrenar
            (entrenar_yolo_seg.py usa 960 por defecto).
        device: None deja que Ultralytics decida (GPU si hay, si no CPU);
            "cpu" fuerza CPU, "0" fuerza la GPU 0.
        """
        if not Path(modelo_path).exists():
            raise FileNotFoundError(
                f"No se encontró el modelo en {modelo_path}. Corre primero "
                f"modelo/scripts/preparar_dataset.py y modelo/scripts/entrenar_yolo_seg.py "
                f"(requieren el dataset real, ver modelo/README.md)."
            )
        from ultralytics import YOLO  # import local: así el resto del proyecto
                                       # (main_test.py con --segmentador clasico,
                                       # la interfaz, etc.) no necesita ultralytics
                                       # instalado si no lo va a usar.

        self.modelo = YOLO(str(modelo_path))
        self.confianza_min = confianza_min
        self.imgsz = imgsz
        self.device = device

    def process(self, frame):
        _, clean_mask, instances = self.process_with_masks(frame)
        return clean_mask, instances

    def process_with_masks(self, frame):
        """Mismo contrato que ClassicSegmenter.process_with_masks: devuelve
        (raw_mask, clean_mask, instances). Para YOLO, raw_mask y clean_mask son
        la misma máscara combinada (la unión de todas las instancias detectadas)
        -- YOLO no tiene una etapa de 'máscara cruda de color' separada como
        ClassicSegmenter, así que no hay nada distinto que mostrar entre ambas
        vistas en la interfaz; se mantienen las dos llaves solo para que
        preview()/main_test.py no tengan que distinguir qué segmentador está
        activo.
        """
        h_img, w_img = frame.shape[:2]
        resultados = self.modelo.predict(
            frame, imgsz=self.imgsz, device=self.device, verbose=False
        )[0]

        instances = []
        combinada = np.zeros((h_img, w_img), dtype=np.uint8)

        if resultados.masks is not None:
            # resultados.masks.data: tensor (n_instancias, h_modelo, w_modelo) en 0..1
            mascaras = resultados.masks.data.cpu().numpy()
            cajas = resultados.boxes
            for i in range(len(mascaras)):
                confianza = float(cajas.conf[i])
                if confianza < self.confianza_min:
                    continue

                # La máscara de Ultralytics viene en la resolución de inferencia
                # (self.imgsz), no en la resolución original del frame -- hay que
                # reescalarla antes de usarla con el resto del pipeline (igual que
                # ClassicSegmenter trabaja siempre en la resolución real del frame).
                mascara = cv2.resize(
                    (mascaras[i] * 255).astype(np.uint8),
                    (w_img, h_img),
                    interpolation=cv2.INTER_NEAREST,
                )

                contornos, _ = cv2.findContours(
                    mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                if not contornos:
                    continue
                cnt = max(contornos, key=cv2.contourArea)  # el contorno más grande
                                                            # de esa instancia, igual
                                                            # criterio que
                                                            # polígono_mas_detallado()
                                                            # en preparar_dataset.py

                combinada = cv2.bitwise_or(combinada, mascara)

                x, y, w, h = cv2.boundingRect(cnt)
                M = cv2.moments(cnt)
                cx = int(M["m10"] / M["m00"]) if M["m00"] != 0 else x + w // 2
                cy = int(M["m01"] / M["m00"]) if M["m00"] != 0 else y + h // 2
                touching_border = (x <= 2) or (y <= 2) or (x + w >= w_img - 2) or (y + h >= h_img - 2)

                clase_id = int(cajas.cls[i])
                tipo_detectado = self.modelo.names[clase_id]

                instances.append({
                    "bbox": (x, y, w, h),
                    "centroid": (cx, cy),
                    "area_px": float(cv2.contourArea(cnt)),
                    "contour": cnt,
                    "is_valid_mask": not touching_border,
                    # Extra respecto a ClassicSegmenter -- ver docstring del módulo:
                    "tipo_detectado": tipo_detectado,
                    "confianza": confianza,
                })

        return combinada, combinada, instances
