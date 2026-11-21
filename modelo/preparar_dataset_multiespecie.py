r"""
CONVERSOR MULTI-ESPECIE: de 5 datasets en 4 formatos distintos a UN SOLO dataset
YOLOv8-seg listo para entrenar con modelo/scripts/entrenar_yolo_seg.py.

POR QUÉ EXISTE ESTE ARCHIVO
----------------------------
`preparar_dataset.py` (el original) solo sabe convertir Laboro Tomato (un único
origen COCO). Para reconocimiento de tipo con varias especies necesitamos un
solo dataset YOLO con una clase por especie, construido a partir de:

    Especie     Dataset                         Formato de origen
    ----------  ------------------------------  --------------------------------
    tomate      Laboro Tomato                   COCO (ya lo sabíamos manejar)
    uva         WGISD                           COCO (coco_annotations/*.json)
    pimenton    Sweet Pepper (Kaggle lemontyc)   COCO (*_coco.json, VIA export)
    manzana     MinneApple                       imagen + máscara indexada (par
                                                  de archivos con el MISMO nombre
                                                  en carpetas distintas)
    frutilla    StrawDI_Db1                      imagen + máscara indexada (igual
                                                  patrón que MinneApple)

Este script resuelve los dos formatos (COCO y par imagen/máscara) con dos
funciones genéricas, y deja todo fundido en:

    modelo/data/combined_yolo/
        data.yaml
        images/{train,val,test}/<especie>_<nombre_original>.<ext>
        labels/{train,val,test}/<especie>_<nombre_original>.txt

Las clases quedan fijas en este orden (coincide con data.yaml):
    0 tomate | 1 manzana | 2 frutilla | 3 uva | 4 pimenton

SUPUESTOS QUE HICE (revisa si no calzan con tu copia real de los datos)
--------------------------------------------------------------------------
- Laboro Tomato: imágenes sueltas directo dentro de
  modelo/data/laboro_tomato_raw/laboro_tomato/train/ y .../test/, anotaciones
  en .../annotations/train.json y test.json. Si tu versión trae las imágenes
  en una subcarpeta distinta, ajusta LABORO_TRAIN_IMG / LABORO_TEST_IMG abajo.
- WGISD: imágenes en modelo/data/wgisd_raw/data/ (todas juntas), anotaciones en
  modelo/data/wgisd_raw/coco_annotations/train_polygons_instances.json y
  test_polygons_instances.json.
- Sweet Pepper: todo (imágenes + el .json) está junto en
  modelo/data/sweet_pepper_raw/dataset_620_red_yellow_cart_only/
  dataset_620_red_yellow_cart_only/dataset_620_red_yellow_cart_only_coco.json.
  Solo se usan las instancias cuya categoría de COCO contenga "fruit" (no se
  usan los pedúnculos/tallos) -- ver FILTRO_CATEGORIA_PIMENTON abajo. No viene
  con train/val/test separado, así que este script arma esos splits solo
  (80/10/10), de forma reproducible (semilla fija).
- MinneApple: imágenes en
  modelo/data/minneapple_raw/detection/train/images/, máscaras en
  modelo/data/minneapple_raw/detection/train/masks/ (mismo nombre de archivo
  en ambas). El split "train" oficial se usa como train (con un 10% separado
  para val); el split con máscaras reales de test
  (modelo/data/minneapple_raw/detection/test_data/segmentation/{images,masks})
  se usa como test.
- StrawDI: ya viene con train/val/test hechos
  (modelo/data/strawdi_raw/StrawDI_Db1/{train,val,test}/{img,label}/), se usan
  tal cual, sin recortar nada.

Cada máscara indexada (MinneApple/StrawDI) se asume: fondo = 0, cada instancia
= un valor entero distinto de píxel. Si alguna máscara viniera en otro formato
(por ejemplo RGB con un color por instancia), este script lo va a notar solo
(va a extraer 1 sola instancia gigante o ninguna) -- revisa el conteo de
instancias que imprime al final por fuente; si da sospechosamente bajo avísame
y lo ajustamos.

CÓMO CORRERLO
--------------
    cd agrovision   (la raíz del repo)
    python modelo\preparar_dataset_multiespecie.py

Tarda varios minutos (recorre miles de imágenes). Al final imprime un resumen
por especie con cuántas imágenes/instancias quedaron en cada split, para que
puedas revisar que nada quedó en cero antes de gastar horas entrenando.
"""

import csv
import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

# ----------------------------------------------------------------------------
# Config general
# ----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent  # modelo/.. = raíz del repo
DATA_RAW = REPO_ROOT / "modelo" / "data"
OUT_DIR = DATA_RAW / "combined_yolo"

CLASES = ["tomate", "manzana", "frutilla", "uva", "pimenton"]
CLASE_ID = {nombre: i for i, nombre in enumerate(CLASES)}

SEED = 42
VAL_FRACTION_SIN_SPLIT_OFICIAL = 0.10  # para fuentes sin val propio
TEST_FRACTION_SWEET_PEPPER = 0.10       # Sweet Pepper no trae splits, se arman

random.seed(SEED)

# Rutas de origen (ajusta si tu copia real quedó en otra estructura, ver
# docstring arriba) ----------------------------------------------------------

LABORO_DIR = DATA_RAW / "laboro_tomato_raw" / "laboro_tomato"
LABORO_TRAIN_JSON = LABORO_DIR / "annotations" / "train.json"
LABORO_TEST_JSON = LABORO_DIR / "annotations" / "test.json"
LABORO_TRAIN_IMG = LABORO_DIR / "train"
LABORO_TEST_IMG = LABORO_DIR / "test"

WGISD_DIR = DATA_RAW / "wgisd_raw"
WGISD_TRAIN_JSON = WGISD_DIR / "coco_annotations" / "train_polygons_instances.json"
WGISD_TEST_JSON = WGISD_DIR / "coco_annotations" / "test_polygons_instances.json"
WGISD_IMG = WGISD_DIR / "data"

PEPPER_DIR = (
    DATA_RAW / "sweet_pepper_raw" / "dataset_620_red_yellow_cart_only"
    / "dataset_620_red_yellow_cart_only"
)
# Ya NO usamos el .json de este dataset -- viene con las categorías "Type"/
# "Color" sin nombre (export roto de VIA), así que leemos directo el .csv
# original, que sí trae "Type":"fruit" explícito por fila.
PEPPER_CSV = PEPPER_DIR / "dataset_620_red_yellow_cart_only_csv.csv"
PEPPER_IMG = PEPPER_DIR

MINNEAPPLE_DIR = DATA_RAW / "minneapple_raw" / "detection"
MINNEAPPLE_TRAIN_IMG = MINNEAPPLE_DIR / "train" / "images"
MINNEAPPLE_TRAIN_MASK = MINNEAPPLE_DIR / "train" / "masks"
# OJO: test_data es HERMANA de detection/, no está adentro -- por eso
# .parent (sube de detection/ a minneapple_raw/ antes de bajar a test_data/).
MINNEAPPLE_TEST_IMG = MINNEAPPLE_DIR.parent / "test_data" / "segmentation" / "images"
MINNEAPPLE_TEST_MASK = MINNEAPPLE_DIR.parent / "test_data" / "segmentation" / "masks"

STRAWDI_DIR = DATA_RAW / "strawdi_raw" / "StrawDI_Db1"


# ----------------------------------------------------------------------------
# Utilidades comunes
# ----------------------------------------------------------------------------

def preparar_carpetas_salida():
    for split in ("train", "val", "test"):
        (OUT_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)


def escribir_label_yolo(ruta_txt, lineas):
    """lineas: lista de strings "clase x1 y1 x2 y2 ...", ya normalizados 0-1."""
    ruta_txt.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_txt, "w") as f:
        f.write("\n".join(lineas))


def poligono_a_linea_yolo(clase_id, puntos_xy, ancho, alto):
    """puntos_xy: lista plana [x1, y1, x2, y2, ...] en píxeles.
    Devuelve la línea de texto YOLO-seg normalizada, o None si el polígono
    es degenerado (menos de 3 puntos)."""
    if len(puntos_xy) < 6:  # menos de 3 puntos (x,y)
        return None
    normalizados = []
    for i in range(0, len(puntos_xy), 2):
        x = min(max(puntos_xy[i] / ancho, 0.0), 1.0)
        y = min(max(puntos_xy[i + 1] / alto, 0.0), 1.0)
        normalizados.append(f"{x:.6f}")
        normalizados.append(f"{y:.6f}")
    return f"{clase_id} " + " ".join(normalizados)


def dividir_val_si_falta(nombres, val_fraction, seed=SEED):
    """Para fuentes que solo traen 'train' oficial: separa un % para val.
    Recibe una lista de identificadores (nombres de imagen) y devuelve
    (nombres_train, nombres_val)."""
    nombres = sorted(nombres)  # orden determinista antes de mezclar
    rng = random.Random(seed)
    rng.shuffle(nombres)
    corte = int(len(nombres) * (1 - val_fraction))
    return nombres[:corte], nombres[corte:]


# ----------------------------------------------------------------------------
# Conversor genérico para fuentes en formato COCO
# ----------------------------------------------------------------------------

def convertir_fuente_coco(
    nombre_especie,
    json_path,
    carpeta_imagenes,
    split_destino,
    prefijo_archivo,
    filtro_categoria=None,
):
    """Lee un COCO json y escribe las imágenes+labels YOLO-seg en
    OUT_DIR/{images,labels}/split_destino/, con nombre
    "<prefijo_archivo>_<nombre_original>".

    filtro_categoria: si se da, solo se incluyen anotaciones cuya
    categoría (nombre en minúsculas) contenga ese texto. Útil para el
    pimentón, donde el COCO trae tanto frutos como pedúnculos.

    Devuelve (n_imagenes_escritas, n_instancias_escritas).
    """
    if not json_path.exists():
        print(f"  [{nombre_especie}] AVISO: no encontré {json_path} -- se omite esta fuente.")
        return 0, 0

    with open(json_path, encoding="utf-8") as f:
        coco = json.load(f)

    categorias_validas = set()
    for cat in coco.get("categories", []):
        nombre_cat = str(cat.get("name", "")).lower()
        if filtro_categoria is None or filtro_categoria in nombre_cat:
            categorias_validas.add(cat["id"])

    if filtro_categoria is not None and not categorias_validas:
        print(
            f"  [{nombre_especie}] AVISO: ninguna categoría de {json_path.name} "
            f"contiene '{filtro_categoria}'. Reviso las categorías disponibles: "
            f"{[c.get('name') for c in coco.get('categories', [])]} -- "
            f"uso TODAS las categorías para no perder el dataset completo."
        )
        categorias_validas = {c["id"] for c in coco.get("categories", [])}

    anotaciones_por_imagen = {}
    for ann in coco.get("annotations", []):
        if ann["category_id"] not in categorias_validas:
            continue
        seg = ann.get("segmentation")
        if not seg or isinstance(seg, dict):  # dict = RLE, no lo manejamos acá
            continue
        anotaciones_por_imagen.setdefault(ann["image_id"], []).append(ann)

    n_imagenes = 0
    n_instancias = 0
    clase_id = CLASE_ID[nombre_especie]

    for img_info in coco.get("images", []):
        anots = anotaciones_por_imagen.get(img_info["id"])
        if not anots:
            continue  # imagen sin instancias de la categoría que nos interesa

        origen_img = carpeta_imagenes / img_info["file_name"]
        if not origen_img.exists():
            # algunos exports de COCO guardan el nombre con subcarpeta incluida
            origen_img = carpeta_imagenes / Path(img_info["file_name"]).name
        if not origen_img.exists():
            continue  # imagen referenciada en el json pero no está en disco

        ancho = img_info.get("width") or 0
        alto = img_info.get("height") or 0
        if not ancho or not alto:
            img_cv = cv2.imread(str(origen_img))
            if img_cv is None:
                continue
            alto, ancho = img_cv.shape[:2]

        lineas = []
        for ann in anots:
            for poligono in ann["segmentation"]:
                linea = poligono_a_linea_yolo(clase_id, poligono, ancho, alto)
                if linea:
                    lineas.append(linea)

        if not lineas:
            continue

        nombre_destino = f"{prefijo_archivo}_{origen_img.name}"
        destino_img = OUT_DIR / "images" / split_destino / nombre_destino
        destino_label = (
            OUT_DIR / "labels" / split_destino / (Path(nombre_destino).stem + ".txt")
        )

        shutil.copyfile(origen_img, destino_img)
        escribir_label_yolo(destino_label, lineas)

        n_imagenes += 1
        n_instancias += len(lineas)

    return n_imagenes, n_instancias


# ----------------------------------------------------------------------------
# Conversor genérico para fuentes de tipo imagen + máscara indexada
# ----------------------------------------------------------------------------

def convertir_fuente_mascara(
    nombre_especie,
    carpeta_imagenes,
    carpeta_mascaras,
    split_destino,
    prefijo_archivo,
    nombres_a_usar=None,
):
    """carpeta_imagenes / carpeta_mascaras: mismas extensiones y mismo nombre
    de archivo en ambas (ej. "20150919_174151_image1.png" en las dos).
    Cada máscara: fondo=0, cada instancia = un entero de píxel distinto.

    nombres_a_usar: si se da, solo procesa esos nombres de archivo (para
    separar train/val de una misma carpeta sin copiar dos veces).

    Devuelve (n_imagenes_escritas, n_instancias_escritas).
    """
    if not carpeta_imagenes.exists() or not carpeta_mascaras.exists():
        print(
            f"  [{nombre_especie}] AVISO: no encontré {carpeta_imagenes} o "
            f"{carpeta_mascaras} -- se omite esta fuente/split."
        )
        return 0, 0

    archivos = nombres_a_usar
    if archivos is None:
        archivos = [p.name for p in carpeta_imagenes.iterdir() if p.is_file()]

    n_imagenes = 0
    n_instancias = 0
    clase_id = CLASE_ID[nombre_especie]

    for nombre_archivo in archivos:
        origen_img = carpeta_imagenes / nombre_archivo
        origen_mask = carpeta_mascaras / nombre_archivo
        if not origen_img.exists() or not origen_mask.exists():
            continue

        mascara = cv2.imread(str(origen_mask), cv2.IMREAD_UNCHANGED)
        if mascara is None:
            continue
        if mascara.ndim == 3:  # por si viene como RGB en vez de 1 canal
            mascara = cv2.cvtColor(mascara, cv2.COLOR_BGR2GRAY)

        valores_instancia = [v for v in np.unique(mascara) if v != 0]
        if not valores_instancia:
            continue

        alto, ancho = mascara.shape[:2]
        lineas = []
        for valor in valores_instancia:
            binaria = (mascara == valor).astype(np.uint8) * 255
            contornos, _ = cv2.findContours(
                binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contornos:
                continue
            cnt = max(contornos, key=cv2.contourArea)
            puntos = cnt.reshape(-1, 2).astype(float).flatten().tolist()
            linea = poligono_a_linea_yolo(clase_id, puntos, ancho, alto)
            if linea:
                lineas.append(linea)

        if not lineas:
            continue

        nombre_destino = f"{prefijo_archivo}_{nombre_archivo}"
        destino_img = OUT_DIR / "images" / split_destino / nombre_destino
        destino_label = (
            OUT_DIR / "labels" / split_destino / (Path(nombre_destino).stem + ".txt")
        )

        shutil.copyfile(origen_img, destino_img)
        escribir_label_yolo(destino_label, lineas)

        n_imagenes += 1
        n_instancias += len(lineas)

    return n_imagenes, n_instancias


# ----------------------------------------------------------------------------
# Orquestación por especie
# ----------------------------------------------------------------------------

def procesar_tomate(resumen):
    for split, json_path, carpeta_img in (
        ("train", LABORO_TRAIN_JSON, LABORO_TRAIN_IMG),
        ("test", LABORO_TEST_JSON, LABORO_TEST_IMG),
    ):
        n_img, n_inst = convertir_fuente_coco(
            "tomate", json_path, carpeta_img, split, "tomate"
        )
        resumen.append(("tomate", split, n_img, n_inst))

    # Laboro Tomato no trae val -- separamos un 10% del train ya copiado.
    _recortar_val_desde_train("tomate", resumen)


def procesar_uva(resumen):
    for split, json_path in (
        ("train", WGISD_TRAIN_JSON),
        ("test", WGISD_TEST_JSON),
    ):
        n_img, n_inst = convertir_fuente_coco(
            "uva", json_path, WGISD_IMG, split, "uva"
        )
        resumen.append(("uva", split, n_img, n_inst))

    _recortar_val_desde_train("uva", resumen)


def procesar_pimenton(resumen):
    """Lee directo el .csv exportado por VIA (no el _coco.json, que vino con
    las categorías sin nombre -- ver nota en PEPPER_CSV). Cada fila es UNA
    instancia (un polígono); nos quedamos solo con las que tengan
    region_attributes.Type == "fruit" (descartamos pedúnculos/tallos)."""
    if not PEPPER_CSV.exists():
        print(f"  [pimenton] AVISO: no encontré {PEPPER_CSV} -- se omite.")
        return

    poligonos_por_imagen = {}
    with open(PEPPER_CSV, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            try:
                attrs = json.loads(fila["region_attributes"])
            except (KeyError, json.JSONDecodeError):
                continue
            if str(attrs.get("Type", "")).lower() != "fruit":
                continue
            try:
                forma = json.loads(fila["region_shape_attributes"])
            except (KeyError, json.JSONDecodeError):
                continue
            xs = forma.get("all_points_x")
            ys = forma.get("all_points_y")
            if not xs or not ys or len(xs) != len(ys):
                continue
            puntos = []
            for x, y in zip(xs, ys):
                puntos.append(float(x))
                puntos.append(float(y))
            poligonos_por_imagen.setdefault(fila["filename"], []).append(puntos)

    if not poligonos_por_imagen:
        print(
            "  [pimenton] AVISO: 0 instancias con Type=fruit en el csv -- "
            "revisa si el valor real es 'Fruit' con mayúscula u otro texto."
        )
        return

    # Split reproducible por IMAGEN (no por instancia), ya que este dataset
    # no trae train/val/test hechos.
    nombres = sorted(poligonos_por_imagen.keys())
    rng = random.Random(SEED)
    rng.shuffle(nombres)
    n = len(nombres)
    n_test = int(n * TEST_FRACTION_SWEET_PEPPER)
    n_val = int(n * VAL_FRACTION_SIN_SPLIT_OFICIAL)
    split_de = {}
    for nombre in nombres[:n_test]:
        split_de[nombre] = "test"
    for nombre in nombres[n_test:n_test + n_val]:
        split_de[nombre] = "val"
    for nombre in nombres[n_test + n_val:]:
        split_de[nombre] = "train"

    clase_id = CLASE_ID["pimenton"]
    conteo = {"train": [0, 0], "val": [0, 0], "test": [0, 0]}

    for nombre_archivo, poligonos in poligonos_por_imagen.items():
        split = split_de[nombre_archivo]
        origen_img = PEPPER_IMG / nombre_archivo
        if not origen_img.exists():
            continue
        img_cv = cv2.imread(str(origen_img))
        if img_cv is None:
            continue
        alto, ancho = img_cv.shape[:2]

        lineas = []
        for puntos in poligonos:
            linea = poligono_a_linea_yolo(clase_id, puntos, ancho, alto)
            if linea:
                lineas.append(linea)
        if not lineas:
            continue

        nombre_destino = f"pimenton_{nombre_archivo}"
        destino_img = OUT_DIR / "images" / split / nombre_destino
        destino_label = (
            OUT_DIR / "labels" / split / (Path(nombre_destino).stem + ".txt")
        )
        shutil.copyfile(origen_img, destino_img)
        escribir_label_yolo(destino_label, lineas)

        conteo[split][0] += 1
        conteo[split][1] += len(lineas)

    for split, (n_img, n_inst) in conteo.items():
        resumen.append(("pimenton", split, n_img, n_inst))


def procesar_manzana(resumen):
    nombres_train_completo = [
        p.name for p in MINNEAPPLE_TRAIN_IMG.iterdir() if p.is_file()
    ] if MINNEAPPLE_TRAIN_IMG.exists() else []
    nombres_train, nombres_val = dividir_val_si_falta(
        nombres_train_completo, VAL_FRACTION_SIN_SPLIT_OFICIAL
    )

    for split, nombres in (("train", nombres_train), ("val", nombres_val)):
        n_img, n_inst = convertir_fuente_mascara(
            "manzana",
            MINNEAPPLE_TRAIN_IMG,
            MINNEAPPLE_TRAIN_MASK,
            split,
            "manzana",
            nombres_a_usar=nombres,
        )
        resumen.append(("manzana", split, n_img, n_inst))

    # El split de test oficial SÍ trae máscaras reales -- se usa tal cual.
    n_img, n_inst = convertir_fuente_mascara(
        "manzana", MINNEAPPLE_TEST_IMG, MINNEAPPLE_TEST_MASK, "test", "manzana"
    )
    resumen.append(("manzana", "test", n_img, n_inst))


def procesar_frutilla(resumen):
    for split in ("train", "val", "test"):
        carpeta_img = STRAWDI_DIR / split / "img"
        carpeta_mask = STRAWDI_DIR / split / "label"
        n_img, n_inst = convertir_fuente_mascara(
            "frutilla", carpeta_img, carpeta_mask, split, "frutilla"
        )
        resumen.append(("frutilla", split, n_img, n_inst))


def _recortar_val_desde_train(especie, resumen):
    """Para fuentes COCO que ya se copiaron completas a train/ pero no
    traen val propio: mueve un 10% de los archivos ya copiados en
    OUT_DIR/images/train (los que empiezan con "<especie>_") a val/."""
    carpeta_train_img = OUT_DIR / "images" / "train"
    carpeta_train_lbl = OUT_DIR / "labels" / "train"
    candidatos = [
        p.name for p in carpeta_train_img.iterdir()
        if p.name.startswith(f"{especie}_")
    ]
    _, nombres_val = dividir_val_si_falta(candidatos, VAL_FRACTION_SIN_SPLIT_OFICIAL)

    n_img_val = 0
    n_inst_val = 0
    for nombre in nombres_val:
        stem = Path(nombre).stem
        origen_img = carpeta_train_img / nombre
        origen_lbl = carpeta_train_lbl / (stem + ".txt")
        if not origen_img.exists() or not origen_lbl.exists():
            continue
        shutil.move(str(origen_img), str(OUT_DIR / "images" / "val" / nombre))
        shutil.move(str(origen_lbl), str(OUT_DIR / "labels" / "val" / (stem + ".txt")))
        n_img_val += 1
        with open(OUT_DIR / "labels" / "val" / (stem + ".txt")) as f:
            n_inst_val += sum(1 for linea in f if linea.strip())

    # Restamos lo movido del conteo de "train" que ya habíamos registrado,
    # y agregamos la entrada de "val".
    for i, (esp, split, n_img, n_inst) in enumerate(resumen):
        if esp == especie and split == "train":
            resumen[i] = (esp, split, n_img - n_img_val, n_inst - n_inst_val)
    resumen.append((especie, "val", n_img_val, n_inst_val))


# ----------------------------------------------------------------------------
# data.yaml + main
# ----------------------------------------------------------------------------

def escribir_data_yaml():
    contenido = (
        f"path: {OUT_DIR.as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"test: images/test\n"
        f"names:\n"
        + "".join(f"  {i}: {nombre}\n" for i, nombre in enumerate(CLASES))
    )
    (OUT_DIR / "data.yaml").write_text(contenido, encoding="utf-8")


def main():
    preparar_carpetas_salida()
    resumen = []

    print("Procesando tomate (Laboro Tomato, COCO)...")
    procesar_tomate(resumen)

    print("Procesando uva (WGISD, COCO)...")
    procesar_uva(resumen)

    print("Procesando pimenton (Sweet Pepper, COCO)...")
    procesar_pimenton(resumen)

    print("Procesando manzana (MinneApple, imagen+mascara)...")
    procesar_manzana(resumen)

    print("Procesando frutilla (StrawDI, imagen+mascara)...")
    procesar_frutilla(resumen)

    escribir_data_yaml()

    print("\n=== Resumen final ===")
    print(f"{'especie':<10} {'split':<6} {'imagenes':>9} {'instancias':>11}")
    total_img = 0
    total_inst = 0
    for especie, split, n_img, n_inst in resumen:
        print(f"{especie:<10} {split:<6} {n_img:>9} {n_inst:>11}")
        total_img += n_img
        total_inst += n_inst
    print(f"\nTOTAL: {total_img} imagenes, {total_inst} instancias.")
    print(f"\nListo en: {OUT_DIR}")
    print(f"data.yaml escrito en: {OUT_DIR / 'data.yaml'}")
    print(
        "\nRevisa que ninguna fila del resumen haya quedado en 0 -- si alguna "
        "especie/split dio 0 imagenes, probablemente una ruta no calzo con tu "
        "copia real de los datos (ver supuestos al inicio del archivo)."
    )


if __name__ == "__main__":
    main()