"""
CONVERSOR COCO (Laboro Tomato) → YOLO-SEG (Actividad A4.1)

¿CÓMO TRABAJAR AQUÍ?
1. Convierte `annotations/train.json` y `annotations/test.json` (formato COCO instance
   segmentation, confirmado contra `config_example/configs/_base_/datasets/
   laboro_tomato_coco_instance.py` del repo oficial de Laboro.AI) al formato que espera
   Ultralytics YOLOv8-seg: una carpeta `images/<split>/` con las fotos y `labels/<split>/`
   con un .txt por imagen, una línea por instancia:
       <id_clase> x1 y1 x2 y2 ... xn yn   (coordenadas del polígono normalizadas 0-1)
2. Por defecto mantiene las 6 clases originales de Laboro Tomato (tamaño × madurez).
   Usa `--clase-unica` para colapsar todo a una sola clase "tomate" (más datos por
   clase, más simple, pero se pierde la etiqueta de madurez como posible ground truth
   futuro para contrastar con `funciones/madurez.py`).
3. Una anotación COCO puede traer varios polígonos por instancia (partes separadas,
   p. ej. un tomate parcialmente tapado). Este script usa el polígono con más puntos
   (el más detallado) y descarta el resto — déjalo documentado si cambias ese criterio,
   porque afecta directamente la máscara que ve el modelo.
4. No se verificó contra el ZIP real (no se pudo descargar en este entorno, ver
   modelo/README.md). Si `--origen` no tiene la estructura esperada, el script falla
   con un mensaje explícito en vez de generar un dataset silenciosamente incompleto.
"""

import argparse
import json
import shutil
from pathlib import Path

CLASES_ORIGINALES = [
    "b_fully_ripened", "b_half_ripened", "b_green",
    "l_fully_ripened", "l_half_ripened", "l_green",
]
CLASE_UNICA = ["tomate"]


def cargar_coco(ruta_json):
    if not ruta_json.exists():
        raise FileNotFoundError(
            f"No se encontró {ruta_json}. Revisa que --origen apunte a la carpeta "
            f"descomprimida del dataset (debe tener annotations/train.json y "
            f"annotations/test.json; ver modelo/README.md)."
        )
    with open(ruta_json, "r", encoding="utf-8") as f:
        return json.load(f)


def polígono_mas_detallado(segmentation):
    """Una anotación COCO puede traer varios polígonos (lista de listas); se usa
    el de más puntos como aproximación de 'la parte más grande/clara' de la instancia."""
    if not segmentation:
        return None
    return max(segmentation, key=len)


def normalizar_puntos(poligono, ancho, alto):
    puntos = []
    for i in range(0, len(poligono), 2):
        x = poligono[i] / ancho
        y = poligono[i + 1] / alto
        puntos.append(f"{x:.6f}")
        puntos.append(f"{y:.6f}")
    return puntos


def convertir_split(origen, destino, split, mapa_clase_id, clase_unica):
    ann_path = origen / "annotations" / f"{split}.json"
    img_dir_origen = origen / split

    coco = cargar_coco(ann_path)
    imagenes = {img["id"]: img for img in coco["images"]}

    (destino / "images" / split).mkdir(parents=True, exist_ok=True)
    (destino / "labels" / split).mkdir(parents=True, exist_ok=True)

    anotaciones_por_imagen = {}
    for ann in coco["annotations"]:
        anotaciones_por_imagen.setdefault(ann["image_id"], []).append(ann)

    categorias = {c["id"]: c["name"] for c in coco["categories"]}

    copiadas, sin_anotacion, instancias_descartadas = 0, 0, 0
    for img_id, img_info in imagenes.items():
        nombre = img_info["file_name"]
        origen_img = img_dir_origen / nombre
        if not origen_img.exists():
            # Algunos exports COCO usan rutas relativas distintas; se avisa en vez de fallar todo.
            print(f"[aviso] no se encontró la imagen {origen_img}, se omite.")
            continue

        shutil.copy2(origen_img, destino / "images" / split / nombre)
        copiadas += 1

        anns = anotaciones_por_imagen.get(img_id, [])
        if not anns:
            sin_anotacion += 1

        lineas = []
        for ann in anns:
            poligono = polígono_mas_detallado(ann.get("segmentation"))
            if not poligono or len(poligono) < 6:
                instancias_descartadas += 1
                continue  # menos de 3 puntos no forma un polígono válido

            if clase_unica:
                clase_id = 0
            else:
                nombre_clase = categorias[ann["category_id"]]
                clase_id = mapa_clase_id[nombre_clase]

            puntos = normalizar_puntos(poligono, img_info["width"], img_info["height"])
            lineas.append(f'{clase_id} ' + " ".join(puntos))

        txt_path = destino / "labels" / split / (Path(nombre).stem + ".txt")
        txt_path.write_text("\n".join(lineas), encoding="utf-8")

    print(f"[{split}] imágenes copiadas={copiadas}, sin anotación={sin_anotacion}, "
          f"instancias descartadas={instancias_descartadas}")


def escribir_data_yaml(destino, clases):
    contenido = (
        f"path: {destino.resolve()}\n"
        f"train: images/train\n"
        f"val: images/test\n"
        f"names:\n" + "\n".join(f"  {i}: {c}" for i, c in enumerate(clases)) + "\n"
    )
    (destino / "data.yaml").write_text(contenido, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origen", required=True, type=Path,
                         help="Carpeta del dataset Laboro Tomato ya descomprimido.")
    parser.add_argument("--destino", required=True, type=Path,
                         help="Carpeta de salida en formato YOLO-seg.")
    parser.add_argument("--clase-unica", action="store_true",
                         help="Colapsa las 6 clases originales en una sola clase 'tomate'.")
    args = parser.parse_args()

    clases = CLASE_UNICA if args.clase_unica else CLASES_ORIGINALES
    mapa_clase_id = {nombre: i for i, nombre in enumerate(clases)}

    for split in ("train", "test"):
        convertir_split(args.origen, args.destino, split, mapa_clase_id, args.clase_unica)

    escribir_data_yaml(args.destino, clases)
    print(f"Listo. data.yaml escrito en {args.destino / 'data.yaml'}")


if __name__ == "__main__":
    main()
