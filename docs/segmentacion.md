# Segmentación de tomates (A2.3) — código y evidencia de funcionamiento

Este documento junta todo lo relacionado específicamente con la **segmentación**: qué hace el código, por qué está hecho así, y la evidencia de que funciona (y de cuándo no). Para la trazabilidad con los ejemplos del curso ver `docs/adaptacion.md`; este archivo es solo sobre segmentación, con más detalle y las imágenes de las pruebas.

## Índice
1. [`funciones/seg.py` — segmentación por color (HSV)](#1-funcionessegpy--segmentación-por-color-hsv)
2. [`funciones/seg_fondo.py` — segmentación por fondo + color](#2-funcionesseg_fondopy--segmentación-por-fondo--color)
3. [Evidencia 1: foto propia del repo (un tomate)](#3-evidencia-1-foto-propia-del-repo-un-tomate)
4. [Evidencia 2: foto real con varios tomates (IDs por instancia)](#4-evidencia-2-foto-real-con-varios-tomates-ids-por-instancia)
5. [Evidencia 3: por qué el color solo no alcanza para fruta de cualquier color](#5-evidencia-3-por-qué-el-color-solo-no-alcanza-para-fruta-de-cualquier-color)
6. [Evidencia 4: fondo + color combinados (escena sintética controlada)](#6-evidencia-4-fondo--color-combinados-escena-sintética-controlada)
7. [Evidencia 5: video real — ambos métodos, 14/15 vs 15/15](#7-evidencia-5-video-real--ambos-métodos-14-15-vs-15-15)
8. [Evidencia 6: persistencia del ID entre cuadros (segmentación → tracking)](#8-evidencia-6-persistencia-del-id-entre-cuadros-segmentación--tracking)
9. [Qué falta / próximos pasos](#9-qué-falta--próximos-pasos)

---

## 1. `funciones/seg.py` — segmentación por color (HSV)

`ClassicSegmenter` recibe un cuadro BGR y devuelve `(mask, instances)`, donde `instances` es una lista (una por tomate detectado) de diccionarios con `bbox`, `centroid`, `area_px`, `contour` e `is_valid_mask`.

```python
hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)           # separa color (Hue) de brillo/saturación
raw_mask = cv2.inRange(hsv, hsv_lower, hsv_upper)        # 1 = color de tomate, 0 = fondo
clean_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)   # saca ruido suelto
clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_CLOSE, kernel) # rellena huecos (reflejos)
contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
```

Por cada contorno con área ≥ `min_area_px`: `cv2.boundingRect` da la caja, `cv2.moments` da el centroide, y se marca `is_valid_mask=False` si la caja toca el borde del cuadro (para no falsear el calibre con un tomate cortado).

**Parámetro que hay que ajustar según la fruta/fondo:** `hsv_lower`/`hsv_upper` — el rango de color a buscar. El valor por defecto del repo es deliberadamente amplio (casi todo el Hue) como punto de partida, no un valor final.

## 2. `funciones/seg_fondo.py` — segmentación por fondo + color

`BackgroundColorSegmenter` combina dos máscaras con `AND`:
- **Máscara de fondo:** `cv2.absdiff(frame, fondo_referencia)` — distinto al fondo vacío de referencia.
- **Máscara de color:** igual que `seg.py`, pero puede recibir **varios** rangos HSV a la vez (se combinan con `OR` entre ellos).

```python
mascara_final = mascara_fondo  AND  (rango_color_1  OR  rango_color_2  OR  ...)
```

Mismo contrato de salida que `ClassicSegmenter` — se puede usar como reemplazo directo en `main_test.py`.

**Requiere:** una foto de referencia del fondo vacío, tomada con la misma cámara/iluminación. No sirve para una sola foto suelta sin esa referencia.

---

## 3. Evidencia 1: foto propia del repo (un tomate)

Imagen: `dataset/fotos/summerlast.png` (la única foto que había en el repo al momento de esta prueba).

| Original | Máscara cruda | Máscara limpia | Resultado anotado |
|---|---|---|---|
| ![](evidencia_segmentacion/01_foto_propia_original.png) | ![](evidencia_segmentacion/02_foto_propia_mascara_cruda.png) | ![](evidencia_segmentacion/03_foto_propia_mascara_limpia.png) | ![](evidencia_segmentacion/04_foto_propia_anotada.png) |

Resultado: 1 tomate detectado, `bbox=(209,25,276,335)`, `centroide=(343,202)`, `area_px=58675`, `is_valid_mask=True`. Confirma que el pipeline básico (HSV → morfología → contornos → bbox/centroide) corre sin errores sobre una imagen real del propio repositorio.

## 4. Evidencia 2: foto real con varios tomates (IDs por instancia)

Imagen real (no sintética) de tomates en planta, del set de ejemplos público de Laboro Tomato (repositorio `laboroai/LaboroTomatoDatasets`, CC BY-NC-SA 4.0 — ver `modelo/README.md`).

| Original | Resultado con ID por tomate |
|---|---|
| ![](evidencia_segmentacion/05_foto_real_multitomate_original.png) | ![](evidencia_segmentacion/06_foto_real_multitomate_anotada.png) |

Parámetros: `hsv_lower=(0,70,40)`, `hsv_upper=(10,255,255)` (rojo maduro), `kernel_size=9`, `min_area_px=1500`. **7 tomates maduros detectados**, cada uno como instancia separada (ID 1 a 7 en orden de detección), con su propio `bbox`/`centroid`/`area_px`. Los tomates verdes de la misma foto no entran — ver sección 5, es intencional y tiene una razón de fondo.

**Importante — el "ID" que se ve en esta imagen no es un ID de seguimiento:** es solo el orden en que `seg.py` devolvió la lista de instancias para ESTE cuadro. El ID que persiste entre cuadros lo asigna `track.py`/`track_kalman.py`, no `seg.py` — ver sección 8 para la demostración de esa diferencia.

## 5. Evidencia 3: por qué el color solo no alcanza para fruta de cualquier color

Intento de ampliar `seg.py` con un segundo rango HSV para detectar también los tomates verdes de la foto anterior:

![](evidencia_segmentacion/07_intento_verde_fallido.png)

Resultado: casi toda la foto se marca como "tomate" — porque un tomate verde y una hoja tienen el mismo color. Esto **no es un umbral mal puesto**, es un límite real de segmentar solo por color cuando el fondo comparte el color del objeto. De ahí nace `seg_fondo.py` (sección 2).

## 6. Evidencia 4: fondo + color combinados (escena sintética controlada)

Para probar si fondo+color resuelve lo anterior, se armó una escena controlada: un tomate rojo, un tomate verde, una **mancha roja fija** pegada al fondo (no es fruta) y una **sombra** (no tiene color de fruta):

![](evidencia_segmentacion/08_sintetico_escena_prueba.png)

| Método | Resultado | Falla |
|---|---|---|
| Solo color | ![](evidencia_segmentacion/09_sintetico_solo_color.png) | marca la mancha fija como si fuera fruta |
| Solo fondo | ![](evidencia_segmentacion/10_sintetico_solo_fondo.png) | marca la sombra como si fuera fruta |
| **Combinado (fondo AND color)** | ![](evidencia_segmentacion/11_sintetico_combinado.png) | **ninguna — detecta justo los 2 tomates** |

## 7. Evidencia 5: video real — ambos métodos, 14/15 vs 15/15

Video real del equipo: `dataset/videos/tomates_sabana_gris_2.mp4`, cuadro #200 (15 tomates cherry reales sobre tela clara, celular a pulso).

| Método original (`ClassicSegmenter`, color rojo estricto) | Método combinado (`BackgroundColorSegmenter`, color amplio) |
|---|---|
| ![](evidencia_segmentacion/12_video_real_solo_color_14de15.png) | ![](evidencia_segmentacion/13_video_real_combinado_15de15.png) |
| **14 de 15** — el tomate anaranjado queda fuera del rango "rojo puro" | **15 de 15** — al combinar con fondo, el filtro de color puede ser amplio (detecta cualquier tono) sin agregar falsos positivos, porque el fondo ya descarta todo lo que no cambió |

Detalle completo de esta prueba (parámetros, diferencia de fondo, recomendación de grabar la tela vacía con cámara fija) en `docs/adaptacion.md`, sección 4.

## 8. Evidencia 6: persistencia del ID entre cuadros (segmentación → tracking)

Misma video (`tomates_sabana_gris_2.mp4`), usando `ClassicSegmenter` + `track.py` (`CentroidTracker`). Se siguió el mismo video entre los cuadros 0 y 120 y se registró qué ID de tracking tenía cada tomate en cada cuadro.

El tomate marcado en **rojo** es el mismo en los 3 cuadros — nótese que se desplaza en la imagen (por el paneo de la cámara, los tomates en sí no se mueven) pero conserva **ID 1** todo el tiempo:

| Cuadro #20 | Cuadro #60 | Cuadro #100 |
|---|---|---|
| ![](evidencia_segmentacion/14_seguimiento_id_cuadro020.png) | ![](evidencia_segmentacion/15_seguimiento_id_cuadro060.png) | ![](evidencia_segmentacion/16_seguimiento_id_cuadro100.png) |

Centroide del tomate ID 1 en cada cuadro — el desplazamiento es gradual y consistente, no un salto (lo que confirmaría que es el mismo objeto, no una reasignación casual del número):

| Cuadro | Centroide (x, y) |
|---|---|
| 20 | (372, 700) |
| 60 | (364, 696) |
| 100 | (320, 692) |

Los IDs 2, 3 y 5 también se mantuvieron estables los 120 cuadros. Algunos IDs aparecen y desaparecen (4, 6, 7, 8...) — son tomates que entran/salen del cuadro por el paneo, o ruido puntual de un reflejo; es un comportamiento esperado del tracker, no un error.

**Por qué importa esto para el resto del pipeline:** `seg.py`/`seg_fondo.py` entregan la lista de instancias *sin* ID persistente — es `track.py`/`track_kalman.py` quien lo agrega, comparando centroides entre cuadros consecutivos. Una vez que el tomate tiene un ID estable, `main_test.py` arma su máscara individual y le calcula calibre/madurez/manchas por separado (nunca se mezcla con el tomate vecino), y `registro.py` guarda una sola fila por ID en el CSV — el mismo formato que después lee `interfaz/dashboard.py`.

## 9. Qué falta / próximos pasos

- **Sustracción de fondo con cámara fija:** las pruebas de video real se hicieron con un cuadro cualquiera del mismo video como referencia de fondo (no había una toma vacía). Funciona, pero con margen ajustado. Recomendación: grabar unos segundos de la tela/cinta vacía con la cámara fija antes de poner la fruta.
- **Reconocimiento de especie (OE4):** hoy el color/rango hay que ajustarlo a mano por especie. La idea de diseño es que el modelo entrenado (`modelo/`) reconozca la especie y el sistema elija automáticamente el perfil de parámetros (color, calibración, madurez) correspondiente.
