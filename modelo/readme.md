# Modelo de reconocimiento de tipo (OE4)

Carpeta separada del resto del proyecto (A2.x/A3.x son el pipeline clásico; esto es
lo necesario para **OE4 — Entrenar o ajustar el modelo de reconocimiento de tipo e
integrarlo con los perfiles por especie** del documento de diseño).

## Qué hay acá

- `preparar_dataset_multiespecie.py` — convierte 5 datasets públicos heterogéneos
  (COCO, máscaras indexadas, VIA CSV) a un único dataset YOLO-seg combinado.
  Reemplaza al antiguo `preparar_dataset.py` (solo Laboro Tomato / solo tomate).
- `entrenar_yolo_seg.py` — ajusta un `yolov8n-seg.pt` preentrenado sobre el
  dataset combinado.
- `yolo_seg.py` — adaptador `YoloSegmenter`: implementa el mismo contrato que
  `funciones/segmentación/seg.py` (`ClassicSegmenter`), así que se puede usar
  en lugar del segmentador HSV sin tocar tracking/calibre/peso/madurez/manchas.
  Ver docstring del archivo para el detalle del contrato.
- `evaluar_vs_clasico.py` — compara detecciones del modelo contra el pipeline
  clásico sobre las mismas imágenes; `calcular_metricas()` (precisión/
  exhaustividad/IoU) sigue como `NotImplementedError` documentado, pendiente.
- `pesos/` — pesos ya entrenados (`especies_v1_best.pt`) y
  [`pesos/README.md`](pesos/README.md) con el detalle completo: qué 5
  datasets se usaron (con links y licencias), cómo regenerar el dataset
  combinado, el comando de entrenamiento exacto y la tabla de resultados
  por especie.
- `data/` — no se versiona (dataset crudo + combinado, varios GB); se
  regenera localmente, ver `pesos/README.md`.

> **Nota:** `modelo/scripts/` contiene copias antiguas de estos mismos
> archivos (de antes de la versión multiespecie). Son las que no se deben
> usar — las vigentes son las de `modelo/` directamente. Conviene que el
> equipo las elimine para no confundirse, pero no las borré yo para no
> tomar esa decisión por el grupo.

## Uso rápido

```powershell
python modelo\entrenar_yolo_seg.py --data modelo\data\combined_yolo\data.yaml --device 0 --epochs 15 --imgsz 640 --batch 16 --nombre especies_v1
python main_test.py <video_o_foto> --segmentador yolo --modelo-yolo modelo\pesos\especies_v1_best.pt
```

Detalle completo (datasets, licencias, métricas, limitaciones) en
[`pesos/README.md`](pesos/README.md).

## Qué falta (OE4 / RF10)

El modelo ya identifica especie (`tipo_detectado`) y confianza por
detección, disponibles en cada instancia que entrega `YoloSegmenter`. Lo
que **todavía no existe** es la selección automática de `Perfil`/
`Evaluadores` según la especie detectada (hoy solo hay
`config/perfiles/tomate.json`) — es el siguiente paso para que RF10 use el
tipo detectado en vez de asumir siempre tomate.
