# Resultado del video sintético

La demo genera 55 imágenes con dos círculos sobre fondo gris. El segmentador clásico extrae sus posiciones y entrega las mismas detecciones a ambos trackers. El círculo superior avanza 5 píxeles por cuadro y desaparece en los cuadros 19 y 20. El MP4 muestra el resultado anotado con Kalman. [Ver video](tracking_sintetico.mp4)

| Método | ID superior en cuadro 18 | ID superior al volver en cuadro 21 | IDs distintos en toda la secuencia |
|---|---:|---:|---:|
| Centroides | 2 | 3 | 3 |
| Kalman | 2 | 2 | 2 |

En ambos métodos se usaron 8 px de distancia máxima y dos ausencias toleradas. El centro observado pasa de x = 140 a x = 155 entre los cuadros 18 y 21. El tracker sencillo crea un ID al superar los 8 px desde su última observación. Kalman predice el avance y recupera el ID 2. El objeto inferior conserva el ID 1 durante toda la secuencia. [Registro por cuadro](tracking_sintetico.json)

La ejecución completa incluye 28 pruebas con 27 aprobaciones y un fallo esperado del método sencillo al cambiar el orden de detecciones cercanas. [Salida de las pruebas](evidencia_hito2_tests.txt) · [Ensayos aislados de centroides](evidencia_sintetica.json) · [Guía de parámetros y reproducción](../docs/tracking/seguimiento.md)
