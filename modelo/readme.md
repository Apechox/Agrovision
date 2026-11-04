# Modelo de reconocimiento de tipo (OE4)

Carpeta separada del resto del proyecto (A2.x/A3.x son el pipeline clásico; esto es
exclusivamente lo necesario para **OE4 — Entrenar o ajustar el modelo de reconocimiento
de tipo e integrarlo con los perfiles por especie** del documento de diseño).

**Qué hay en cada subcarpeta:**
- `modelo/scripts/` — el código (los 3 .py), separado de los datos/resultados.
- `modelo/data/` — donde va el dataset descargado y convertido (no existe todavía,
  se crea al correr los scripts).
- `modelo/requirements.txt` — lista de librerías de Python que necesita *solo* esta
  carpeta (ver más abajo qué es exactamente).

## 1. Dataset: Laboro Tomato

- **Qué es:** 804 imágenes de tomates con segmentación de instancia a nivel de píxel,
  804 imágenes (643 train / 161 test), 6 clases que combinan tamaño (`b_` = cherry/big,
  `l_` = little) y estado de madurez (`fully_ripened`, `half_ripened`, `green`).
  Repositorio oficial: <https://github.com/laboroai/LaboroTomatoDatasets>.
- **Licencia:** CC BY-NC-SA 4.0 (uso no comercial, con atribución, compartir igual).
  Para un proyecto académico de TEL328 está bien; cítalo en el informe final
  (sección 1.4 Referencias) si el modelo se entrena con él.
- **Descarga:** no pude bajarlo yo mismo — el entorno donde corro no tiene salida de red
  hacia S3/hosts externos (solo PyPI/npm/GitHub). Lo tienes que bajar tú:

  ```bash
  curl -o laboro_tomato.zip http://assets.laboro.ai.s3.amazonaws.com/laborotomato/laboro_tomato.zip
  unzip laboro_tomato.zip -d modelo/data/laboro_tomato_raw
  ```

  (o simplemente abre el link en el navegador y descomprime). Verificado contra la
  configuración oficial del repo: la estructura esperada es

  ```
  laboro_tomato_raw/
  ├── annotations/
  │   ├── train.json   # COCO instance segmentation
  │   └── test.json
  ├── train/            # imágenes .jpg
  └── test/
  ```

  Si al descomprimir la estructura real difiere de esto (nombres de carpeta distintos,
  por ejemplo), ajusta las rutas en `scripts/preparar_dataset.py` — no pude verificarlo
  contra el ZIP real, solo contra la configuración de MMDetection que publica el repo
  oficial.

## 2. Flujo de trabajo

El primer comando instala las dependencias del archivo `requirements.txt` (ver sección 2.1
si no sabes qué es); los siguientes tres corren los scripts que están en `modelo/scripts/`.

```bash
python -m pip install -r modelo/requirements.txt

# 1) Convierte las anotaciones COCO a formato YOLO-seg (Ultralytics)
python modelo/scripts/preparar_dataset.py \
    --origen modelo/data/laboro_tomato_raw \
    --destino modelo/data/laboro_tomato_yolo

# 2) Entrena (ajuste de un modelo preentrenado, tarea A4.3)
python modelo/scripts/entrenar_yolo_seg.py --data modelo/data/laboro_tomato_yolo/data.yaml --epochs 48

# 3) Compara contra el pipeline clásico (tarea A4.4), sobre las mismas imágenes de test
python modelo/scripts/evaluar_vs_clasico.py --data modelo/data/laboro_tomato_yolo
```

### 2.1 ¿Qué es `requirements.txt`?

Es un archivo de texto plano (no se ejecuta, no es código) que lista los paquetes de
Python que hacen falta para correr los 3 scripts de esta carpeta — cada línea es
`nombre_paquete>=version_minima`. `pip install -r modelo/requirements.txt` lee ese
archivo e instala todo de una vez, en vez de escribir `pip install ultralytics`,
`pip install pycocotools`, etc. uno por uno. Se separó del `requirements.txt` general
del proyecto (si lo tienes) porque `ultralytics`/`pycocotools` solo los necesita el
modelo OE4 — el pipeline clásico (`main_test.py`) no los usa para nada.

## 3. Decisiones y por qué

- **YOLOv8-seg en vez de Mask R-CNN/MMDetection:** el documento de diseño (sección 1.3)
  ya menciona YOLO como alternativa factible, y Ultralytics se instala con un solo
  `pip install ultralytics`, sin el stack de MMDetection/MMCV que exige el repo oficial
  de Laboro.AI. El baseline publicado por Laboro.AI (Mask R-CNN R-50-FPN, bbox AP 64.3,
  mask AP 65.7) sirve igual como referencia de qué tan bien debería rendir un modelo
  ajustado a este dataset, sea cual sea la arquitectura.
- **`--clase-unica` en `scripts/preparar_dataset.py`:** por defecto se mantienen las 6 clases
  originales (tamaño × madurez), porque sirven para una idea que vale la pena explorar
  más adelante: las etiquetas de madurez de Laboro Tomato son ground truth independiente
  para contrastar contra la clasificación por color de `funciones/madurez.py` (RNF6:
  evaluación con datos reservados). Si por ahora solo necesitas "es tomate sí/no" para
  RF2 (reconocimiento y segmentación), usa `--clase-unica` para colapsar todo a una sola
  clase `tomate` y entrenar más rápido con menos datos por clase.
- **Qué NO resuelve este dataset:** son fotos de tomates en la planta/cosechados, no en
  una cinta transportadora — sirve para el reconocimiento de tipo (OE4), no reemplaza el
  video real del montaje que necesitan A1.2/A1.3 para tracking y calibración.

## 4. Pendiente / no verificado

- La estructura real del ZIP descomprimido (solo verificada contra la config de
  MMDetection, no contra el archivo).
- El entrenamiento no se ejecutó aquí (requiere el dataset real, que no pude descargar).
- `evaluar_vs_clasico.py` deja los cálculos de precisión/exhaustividad/IoU como función
  a completar una vez haya un modelo entrenado — por ahora corre y marca claramente
  qué falta (NotImplementedError documentado, no un resultado inventado).
