# Modelo YOLOv8-seg multiespecie (OE4)

Segmentador por modelo entrenado que identifica especie (tomate, manzana,
frutilla, uva, pimentón) y la posición de cada fruto/ítem en la imagen,
usable como alternativa a `ClassicSegmenter` (HSV + contornos) vía
`main_test.py --segmentador yolo --modelo-yolo <ruta/a/best.pt>`.

Los pesos ya entrenados están en `modelo/pesos/especies_v1_best.pt`.
Los datasets originales **no se incluyen en este repo** (varios GB en total,
con licencias propias de cada fuente) — se regeneran localmente con el
script de este mismo directorio. Ver abajo cómo descargarlos y dónde
dejarlos.

## Datasets usados

| Especie | Dataset | Fuente | Formato original |
|---|---|---|---|
| Tomate | Laboro Tomato | http://assets.laboro.ai.s3.amazonaws.com/laborotomato/laboro_tomato.zip | COCO (instance seg, 6 clases tamaño×madurez) |
| Uva | WGISD (Wine Grape Instance Segmentation Dataset) | https://github.com/thsant/wgisd | COCO (`coco_annotations/*_polygons_instances.json`) |
| Pimentón | Sweet Pepper (lemontyc) | https://www.kaggle.com/datasets/lemontyc/sweet-pepper | VIA CSV (polígonos + atributo `Type`: fruit/peduncle) |
| Manzana | MinneApple | https://conservancy.umn.edu/handle/11299/206575 | Máscaras indexadas (detection + test_data/segmentation) |
| Frutilla | StrawDI (StrawDI_Db1) | https://strawdi.github.io/ | Máscaras indexadas, con splits train/val/test propios |

**Importante sobre licencias:** cada dataset tiene sus propios términos de
uso (en general, uso académico/investigación; varios son no comerciales).
Antes de usar este modelo fuera del contexto de este curso (TEL328),
revisa la licencia de cada fuente en el link de arriba.

## Cómo regenerar el dataset combinado

1. Descarga cada fuente y déjala en `modelo/data/<nombre>_raw/` con esta
   estructura exacta (la que espera `preparar_dataset_multiespecie.py`):

   ```
   modelo/data/
     laboro_tomato_raw/laboro_tomato/{annotations,train,test}/
     wgisd_raw/{coco_annotations,data}/
     sweet_pepper_raw/dataset_620_red_yellow_cart_only/dataset_620_red_yellow_cart_only/
     minneapple_raw/{detection,test_data}/
     strawdi_raw/StrawDI_Db1/{train,val,test}/
   ```

2. Corre el conversor (normaliza las 5 fuentes a un único dataset YOLO-seg):

   ```powershell
   python modelo\preparar_dataset_multiespecie.py
   ```

   Esto genera `modelo/data/combined_yolo/` (images/labels/train,val,test +
   `data.yaml`). Resumen de la corrida usada para entrenar `especies_v1`:

   ```
   especie    split   imagenes  instancias
   tomate     train        578        6881
   tomate     test         161        1996
   tomate     val           65         900
   uva        train         99        2222
   uva        test          27         647
   uva        val           11         263
   pimenton   train        497        4230
   pimenton   val           61         528
   pimenton   test          61         566
   manzana    train        603       25642
   manzana    val           67        2537
   manzana    test         331       12285
   frutilla   train       2800       16234
   frutilla   val          100         572
   frutilla   test         200        1132

   TOTAL: 5661 imagenes, 76635 instancias.
   ```

## Entrenamiento

```powershell
python modelo\entrenar_yolo_seg.py --data modelo\data\combined_yolo\data.yaml --device 0 --epochs 15 --imgsz 640 --batch 16 --nombre especies_v1
```

Pocas épocas a propósito: el objetivo es solo identificar la especie, no
afinar subtipos (tamaño/madurez por especie).

### Resultados (especies_v1, 15 épocas, YOLOv8n-seg)

| Especie | mAP50 caja | mAP50 máscara |
|---|---|---|
| tomate | 0.889 | 0.879 |
| frutilla | 0.943 | 0.944 |
| manzana | 0.791 | 0.653 |
| pimentón | 0.751 | 0.728 |
| uva | 0.655 | 0.641 |

Uva y manzana rinden algo más bajo: uva por tener el val set más chico (11
imágenes), manzana por racimos con frutos muy solapados en MinneApple. Para
el objetivo de solo identificar especie, el modelo ya es usable; si se
necesita mejor calidad de máscara en esas dos clases, conviene más épocas
focalizadas o revisar esos splits.

## Uso en el proyecto

```powershell
python main_test.py <video_o_foto> --segmentador yolo --modelo-yolo modelo\pesos\especies_v1_best.pt
```

Ver `modelo/yolo_seg.py` para el contrato que implementa (`YoloSegmenter`,
mismo `process()`/`process_with_masks()` que `ClassicSegmenter`) y las
llaves extra que agrega a cada instancia (`tipo_detectado`, `confianza`).
