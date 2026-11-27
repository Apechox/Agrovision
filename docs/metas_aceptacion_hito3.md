# Metas de aceptación — AgroVision, Hito 3 (T5.1.1)

Fijadas antes de abrir los datos reservados de A5.3, para no ajustar criterios
después de ver los resultados (regla de A5.3: "sin reajustar con la prueba
reservada"). Son una propuesta inicial, pendiente de confirmación por el resto
del equipo para los módulos que no son de OE4.

| Módulo | Meta | Cómo se mide | Base/referencia |
|---|---|---|---|
| Calibre (OE2, A2.5) | Error ≤ ±3 mm o ±10% frente al pie de metro, lo que sea mayor | Comparar `ancho_mm` contra medición física en el mismo cuadro | Provisional — depende de que T2.5.2 (pendiente) se complete antes del test |
| Seguimiento/IDs (OE2, A2.4) | 0 IDs duplicados o perdidos en el video reservado; ambigüedades reportadas, no contadas como error | Revisión manual de IDs cuadro a cuadro | 27/28 pruebas sintéticas ya aprobadas; primera medición sobre video real |
| Peso (OE3, A3.4) | RMSE ≤ 5 g dentro del dominio validado (47,7–77,3 mm); fuera de rango, "No evaluable", nunca extrapolar | Comparar `peso_g` contra balanza en ejemplares reservados | RMSE 4,39 g ya obtenido por leave-one-out en desarrollo |
| Madurez / Manchas (OE3, A3.1/A3.2) | Coincidencia ≥ 80% con etiqueta humana en una muestra del video reservado | Conteo manual de aciertos/desaciertos (ej. 30 frutos) | Sin ground truth humano todavía — pendiente etiquetar una muestra |
| Modelo de especie (OE4, A4.3/A4.4) | mAP50 ≥ 0.65 por especie; en detección geométrica, igualar o superar al clásico en tomate y superarlo claramente en las otras 4 especies | `evaluar_vs_clasico.py` sobre el test reservado | Ya logrado en validación propia (0.655–0.943 mAP50 por especie) |
| Latencia (RNF2) | ≤ 100 ms/imagen en GPU (RTX 2060 o equivalente); reportar también en CPU sin ser meta dura | Tiempo de `predict()`/`process()` en `evaluar_vs_clasico.py` | ~3 ms/imagen de inferencia pura ya observado en GPU |
| Estabilidad (A5.2) | Procesar el video completo sin caída ni excepción no controlada; recuperación correcta tras desconexión simulada | Ejecución de extremo a extremo + prueba de desconexión | Pendiente T5.2.2 |

## Reglas de reporte

1. Congelar versión de código y pesos del modelo antes de abrir los datos reservados.
2. Correr una sola vez sobre la prueba reservada; si algo falla, se documenta como brecha, no se reajusta y se vuelve a correr.
3. Todo resultado que no cumpla la meta se reporta igual, con la causa probable.
4. Las métricas de calibre/peso/madurez se calculan solo sobre registros válidos (`is_valid_mask=True`, calibración validada).
