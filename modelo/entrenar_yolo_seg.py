"""
AJUSTE DE UN MODELO PREENTRENADO DE SEGMENTACIÓN POR INSTANCIA (Actividad A4.3)

¿CÓMO TRABAJAR AQUÍ?
1. Parte de un YOLOv8-seg preentrenado en COCO (`yolov8n-seg.pt` por defecto, el más
   liviano) y lo ajusta ("fine-tune") sobre `data.yaml` generado por
   `preparar_dataset.py`. Si tienes GPU úsala (`--device 0`); si no, Ultralytics cae a
   CPU automáticamente, solo que más lento.
2. `--epochs 48` y los demás valores por defecto imitan el baseline que Laboro.AI
   publicó con Mask R-CNN (lr=0.01, epochs=48) para tener un punto de comparación
   parecido, no porque sean necesariamente los óptimos para YOLO.
3. Al terminar, Ultralytics deja los pesos en `runs/segment/<nombre>/weights/best.pt`
   — ese es el archivo que necesita `evaluar_vs_clasico.py` y, más adelante, A4.5
   (integración tipo reconocido → selección de perfil).
4. No se ejecutó aquí: requiere el dataset real (ver modelo/README.md), que no se pudo
   descargar en este entorno.
"""

import argparse

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="Ruta al data.yaml de preparar_dataset.py")
    parser.add_argument("--modelo-base", default="yolov8n-seg.pt",
                         help="Checkpoint preentrenado de Ultralytics (n/s/m/l/x-seg).")
    parser.add_argument("--epochs", type=int, default=48)
    parser.add_argument("--imgsz", type=int, default=960,
                         help="Las fotos de Laboro Tomato son de alta resolución (3024x4032); "
                              "960 es un punto de partida razonable, no el óptimo verificado.")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default=None, help="'0' para GPU, 'cpu' para forzar CPU.")
    parser.add_argument("--nombre", default="agrovision_tomate_seg")
    args = parser.parse_args()

    modelo = YOLO(args.modelo_base)
    modelo.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.nombre,
        project="runs/segment",
    )

    print("\nEntrenamiento terminado. Pesos en: "
          f"runs/segment/{args.nombre}/weights/best.pt")


if __name__ == "__main__":
    main()
