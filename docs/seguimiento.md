# Seguimiento de frutos en AgroVision

**Actividad A2.4 · requisito RF9 · avance al 6 de noviembre de 2026.** El seguimiento asigna una identidad a cada fruto visible e intenta conservarla mientras cruza la cinta. Así, una observación de madurez, calibre o manchas puede vincularse con la unidad que la originó. Victoria Fernández tiene asignado el seguimiento por acuerdo del equipo. La rama parte del tracker de centroides y del filtro de Kalman ya incorporados por el grupo.

## Entrada, salida y métodos

Por cada fotograma válido, segmentación entrega una lista de detecciones con centro, caja, contorno, área y validez de máscara. Las coordenadas usan píxeles del mismo fotograma. Una máscara inválida se excluye del seguimiento actual. La llamada `update(instances)` devuelve las detecciones observadas con un `id`. Para el registro, el programa debe asociar cada ID con su sesión y cuadro de origen.

| Método | Cómo asocia una detección | Comportamiento en una ausencia |
|---|---|---|
| Centroides | Compara su centro con la última posición observada de cada ID disponible. Procesa la lista en orden. | Retiene el ID durante un número limitado de cuadros. Compara la reaparición con el último centro conocido. |
| Kalman | Predice posición y velocidad por ID. Evalúa conjuntamente los pares admisibles, primero por cantidad de asociaciones y luego por distancia total. | La predicción avanza mientras falta una observación. Si existen alternativas de coste similar, omite las detecciones dudosas y comunica la ambigüedad. |

Kalman entrega los avisos de la operación más reciente en `last_events`. Distingue ambigüedad, ausencia temporal, recuperación, pérdida definitiva por plazo y cierre. El consumidor debe leer los avisos antes de la siguiente operación. Un cuadro válido sin detecciones cuenta como ausencia. La suspensión de la fuente detiene las observaciones y el programa puede cerrar las trayectorias mediante `reset`.

El modelo de posición y velocidad y las operaciones de predicción y corrección siguen el ejemplo local del ramo `OPENCV-KALMAN-FILTER2_WIN/OPENCV-KALMAN-FILTER2/main.cpp`. El proyecto mantiene un filtro por fruto y aplica una asignación conjunta con SciPy. [Código de seguimiento](../../funciones/tracking/)

## Parámetros y fundamento experimental

| Parámetro | Valor y razón de uso | Evidencia y límite |
|---|---|---|
| Distancia máxima | La demo usa **8 px**. El objeto avanza 5 px por cuadro y recorre 15 px entre la última observación y la reaparición. El umbral admite el avance habitual y permite distinguir el efecto de predecir el movimiento. | Ambos métodos reciben las mismas detecciones y el mismo umbral. El programa general parte de **80 px**. Su ajuste para la cámara real queda pendiente. |
| Ausencias toleradas | La demo usa **2 cuadros**, exactamente la duración del ocultamiento. El código elimina el track cuando supera esa tolerancia. El valor general inicial es **10 cuadros**. | Se probaron la recuperación dentro del plazo y la creación de un nuevo ID tras caducar. La duración en segundos dependerá de la frecuencia efectiva de captura. |
| Margen de ambigüedad | **2 px** de diferencia en el coste total entre asignaciones con igual número de pares. Las asociaciones afectadas quedan en duda. | Las pruebas con alternativas empatadas verifican que se omiten esos pares y se conserva un tercer fruto independiente. El margen es provisional y falta contrastarlo con videos anotados. |
| Modelo de movimiento | Un paso temporal por actualización válida, velocidad inicial cero, covarianza inicial identidad, ruido de proceso **0,01** y ruido de medición **0,1**. | Son valores del filtro incorporado por el equipo. Con ellos se verificó recuperación tras una ausencia breve. Queda pendiente comparar otras combinaciones y medir el efecto de variaciones de velocidad y frecuencia. |

## Resultados y alcance

En una secuencia controlada de 55 cuadros con dos objetos, el método de centroides asignó tres IDs y Kalman conservó los dos originales. En otro ensayo, cambiar solo el orden de dos detecciones cercanas hacía que el método sencillo reasignara una identidad. Kalman conservó los dos IDs en ambos órdenes. Las 28 pruebas automatizadas produjeron 27 aprobaciones y un fallo esperado que documenta esa limitación del método sencillo. [Resultados por cuadro y video](../../salida-tracking/README.md) · [Pruebas](../../test/tracking/)

Para completar RF9 quedan la evaluación con identidades anotadas en videos reales, la selección de una observación válida en la zona de medición mediante un criterio fijo, y la consolidación del paso por sesión e ID. Las cinco grabaciones propias se prepararon sin audio para esas pruebas. Los resultados anteriores corresponden a los escenarios sintéticos.

### Limitación identificada en RF9: un ID nuevo ante tres detecciones ambiguas

En un ensayo aislado del 6 de noviembre, el tracker de Kalman tenía un único ID activo con posición predicha en `x = 100`. En el cuadro siguiente recibió tres detecciones a la misma altura, en `x = 99, 100 y 101`. Las tres estaban dentro del umbral de distancia de 8 px y sus costes quedaban dentro del margen de ambigüedad de 2 px. La asociación comparó la mejor asignación con una sola alternativa. Marcó como dudosas las detecciones en 99 y 100, pero dejó libre la de 101. El tracker le asignó el ID 2 mientras retenía temporalmente el ID 1.

Si la segmentación produce varias detecciones de un mismo tomate, este comportamiento podría hacer que se contabilice dos veces. El efecto sobre el conteo de frutos en video real queda pendiente de evaluación.

**Corrección propuesta, pendiente de implementación y validación.** Antes de registrar una detección como fruto nuevo, comprobar si podría pertenecer a un ID activo en alguna asignación global con igual número de pares y coste dentro del margen. En ese caso se aplazaría el alta y se conservaría el ID original durante la tolerancia a ausencias. La futura prueba de regresión debería verificar que los seis órdenes posibles de las tres detecciones producen un aviso de ambigüedad y cero IDs nuevos. Una detección adicional, espacialmente independiente, debería poder iniciar su propia trayectoria.

## Reproducción desde la raíz del repositorio

```sh
python -m pip install -r requirements-tracking.txt
python -B -m unittest discover -s test -v
python -B -m examples.tracking.demo_tracking
python -B -m examples.tracking.demo_tracking_kalman --output salida-reproduccion
```

La última orden genera un MP4 anotado con Kalman y un JSON con las observaciones de ambos métodos. La carpeta de destino indicada permite comparar una nueva ejecución con la evidencia publicada.
