"""
COMPARACIÓN MODELO ENTRENADO vs. PIPELINE CLÁSICO (Actividad A4.4)

¿CÓMO TRABAJAR AQUÍ?
1. Corre el modelo YOLOv8-seg entrenado (`entrenar_yolo_seg.py`) y el pipeline clásico
   (`funciones/seg.py` + `funciones/calib.py`, vía `main_test.py`) sobre las MISMAS
   imágenes de test, y deja ambos resultados listados lado a lado.
2. A propósito, este script NO calcula todavía precisión/exhaustividad (precision/
   recall) ni IoU — eso requiere un modelo ya entrenado sobre datos reales, que no
   existe en este entorno (ver modelo/README.md, sección 4). En vez de inventar un
   número, `calcular_metricas()` lanza `NotImplementedError` con una explicación de qué
   falta y cómo completarlo, para que quede documentado y no se confunda con un
   resultado real.
3. Lo que SÍ hace hoy: carga ambos conjuntos de predicciones (si existen), cuenta
   detecciones por clase/imagen, y deja la estructura para que, una vez haya pesos
   reales entrenados, solo haya que implementar `calcular_metricas()` (comparación caja
   por caja contra las anotaciones COCO de test.json con pycocotools, por ejemplo
   COCOeval) sin tocar el resto del flujo.
"""

import argparse
import json
import sys
from pathlib import Path


def cargar_predicciones_yolo(modelo_path, imagenes_dir):
    """Corre el modelo YOLO-seg entrenado sobre cada imagen de test y devuelve
    una lista de detecciones por imagen. Requiere pesos reales en modelo_path."""
    from ultralytics import YOLO

    if not Path(modelo_path).exists():
        raise FileNotFoundError(
            f"No se encontró el modelo en {modelo_path}. Corre primero "
            f"entrenar_yolo_seg.py (requiere el dataset real, ver modelo/README.md)."
        )

    modelo = YOLO(modelo_path)
    resultados = {}
    for img_path in sorted(Path(imagenes_dir).glob("*.jpg")):
        pred = modelo.predict(str(img_path), verbose=False)[0]
        clases = [modelo.names[int(c)] for c in pred.boxes.cls] if pred.boxes is not None else []
        resultados[img_path.name] = clases
    return resultados


def cargar_predicciones_clasico(imagenes_dir, calib_json):
    """Corre el pipeline clásico (segmentación HSV + contornos) sobre las mismas
    imágenes y devuelve cuántos tomates detectó por imagen (sin clase, el pipeline
    clásico solo segmenta/cuenta, no clasifica tipo)."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    import cv2
    from funciones.seg import ClassicSegmenter

    segmentador = ClassicSegmenter()
    resultados = {}
    for img_path in sorted(Path(imagenes_dir).glob("*.jpg")):
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        mascara, contornos = segmentador.process(frame)
        resultados[img_path.name] = len(contornos)
    return resultados


def calcular_metricas(predicciones_yolo, anotaciones_coco_path):
    """
    PENDIENTE — NO IMPLEMENTADO.

    Para calcular precisión, exhaustividad (recall) e IoU de verdad se necesita:
    1. Un modelo YOLO-seg ya entrenado con el dataset real (no el sandbox sintético
       usado para probar preparar_dataset.py).
    2. Cargar modelo/data/laboro_tomato_raw/annotations/test.json con pycocotools
       (COCO + COCOeval) como ground truth.
    3. Convertir las predicciones de Ultralytics a formato COCO results
       (image_id, category_id, bbox, score, segmentation) y correr COCOeval
       con iouType='segm' para obtener AP/AR por clase y en conjunto.

    Se deja como NotImplementedError (en vez de un número inventado) porque reportar
    una métrica sin modelo entrenado real sería un resultado falso en el informe final.
    Cuando haya pesos entrenados sobre el dataset real, implementar aquí los 3 pasos
    de arriba.
    """
    raise NotImplementedError(
        "calcular_metricas() requiere un modelo entrenado sobre el dataset real de "
        "Laboro Tomato (ver modelo/README.md sección 4). Con el dataset sintético de "
        "prueba de preparar_dataset.py no hay ground truth representativo para "
        "calcular precisión/exhaustividad/IoU de forma honesta."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path,
                         help="Carpeta YOLO-seg generada por preparar_dataset.py (debe tener images/test/).")
    parser.add_argument("--modelo", default="runs/segment/agrovision_tomate_seg/weights/best.pt")
    parser.add_argument("--calib", default="config/calib.json")
    args = parser.parse_args()

    imagenes_test = args.data / "images" / "test"
    if not imagenes_test.exists():
        print(f"[error] no existe {imagenes_test}. Corre preparar_dataset.py primero.")
        sys.exit(1)

    print("=== Pipeline clásico (HSV + contornos) ===")
    try:
        conteo_clasico = cargar_predicciones_clasico(imagenes_test, args.calib)
        for nombre, n in conteo_clasico.items():
            print(f"  {nombre}: {n} detecciones")
    except Exception as e:
        print(f"[error] no se pudo correr el pipeline clásico: {e}")

    print("\n=== Modelo YOLOv8-seg entrenado ===")
    try:
        predicciones_yolo = cargar_predicciones_yolo(args.modelo, imagenes_test)
        for nombre, clases in predicciones_yolo.items():
            print(f"  {nombre}: {clases}")
    except FileNotFoundError as e:
        print(f"[pendiente] {e}")
        predicciones_yolo = None

    print("\n=== Métricas (precisión / exhaustividad / IoU) ===")
    if predicciones_yolo is None:
        print("[pendiente] no hay modelo entrenado todavía, no se puede calcular.")
    else:
        try:
            calcular_metricas(predicciones_yolo, args.data / "annotations_test.json")
        except NotImplementedError as e:
            print(f"[pendiente] {e}")


if __name__ == "__main__":
    main()
