# Boceto de bitácora — Interfaz (A3.6)

Borrador para pasar al Excel de la bitácora. **Las columnas son una propuesta**: hay que igualarlas a las del Excel real del equipo (no está en el repositorio ni en sus ramas remotas).

**Responsable de este bloque:** Cristóbal Fuentes
**Base de links:** `https://github.com/Apechox/Agrovision`

> Los links a commits, ramas y archivos **solo funcionan cuando la rama se sube** (`git push -u origin feat/interfaz-web`). Hasta entonces apuntan a algo que GitHub no conoce. Las ramas locales hoy son `feat/interfaz-funcional` y `feat/interfaz-web`.

## Tareas realizadas

| Fecha | Actividad | Tarea realizada | Responsable | Evidencia (link) | Resultado | Estado |
|---|---|---|---|---|---|---|
| 04/11/2026 | A3.6 | Esqueleto inicial de `interfaz/app.py` y `dashboard.py` (importaban módulos que no existen en el repo) | Apechox *(cuenta de GitHub; confirmar la persona)* | [0ed4954](https://github.com/Apechox/Agrovision/commit/0ed4954) · [77e4025](https://github.com/Apechox/Agrovision/commit/77e4025) | Base de arquitectura; **no ejecutaba** (`ModuleNotFoundError`) | Hecho (reemplazado) |
| 05/11/2026 | A3.6 | Diagnóstico del estado real del repo frente al documento v1.1 | Cristóbal Fuentes | [docs/cambios_vs_diseno.md](https://github.com/Apechox/Agrovision/blob/feat/interfaz-web/docs/cambios_vs_diseno.md) | 9 cambios a aprobar, 7 afirmaciones sin respaldo en el repo, 12 pendientes | Hecho |
| 05/11/2026 | A3.6 | Interfaz de escritorio (Tkinter) funcional sobre `seg`, `track` y `calib`: video con zona de medición, ID, mm, registro por ID, CSV, dashboard, incidencias | Cristóbal Fuentes | [a74bd36](https://github.com/Apechox/Agrovision/commit/a74bd36) | Abre y procesa foto y video; foto de ejemplo → 32,47 mm | Hecho |
| 06/11/2026 | A3.6 | Interfaz web local (servidor propio + navegador): vistas por etapa, explicación del pipeline, tablas, dashboard, subida de archivos | Cristóbal Fuentes | [0aa1bc1](https://github.com/Apechox/Agrovision/commit/0aa1bc1) · [capturas](https://github.com/Apechox/Agrovision/tree/feat/interfaz-web/docs/evidencia) | Probada por API y en navegador | Hecho |
| 06/11/2026 | A3.6 | Sliders HSV con vista previa y trazabilidad en CSV; prueba con video real (421 cuadros) | Cristóbal Fuentes | [695f04d](https://github.com/Apechox/Agrovision/commit/695f04d) · [web_sliders_hsv.jpg](https://github.com/Apechox/Agrovision/blob/feat/interfaz-web/docs/evidencia/web_sliders_hsv.jpg) | Procesó el video completo; medidas en mm **no interpretables** hasta calibrar (T2.5.1) | Hecho |
| 06/11/2026 | A3.6 | Documentación del trabajo de interfaz y registro de cambios vs. diseño | Cristóbal Fuentes | [docs/documentacion_trabajo.md](https://github.com/Apechox/Agrovision/blob/feat/interfaz-web/docs/documentacion_trabajo.md) | Texto propuesto para secciones 3.3, 7.1, 7.2 y 7.3 | Hecho |

## Tareas pendientes (para la siguiente entrada)

| Actividad | Tarea | Depende de | Estado |
|---|---|---|---|
| A3.6 | Probar con cámara real | Cámara y montaje (A1.2) | Pendiente |
| A3.6 | Probar con video calibrado de la cinta | Calibración real (A2.5, T2.5.1) | Pendiente |
| A3.6 | Conectar madurez y manchas a las tablas y al dashboard | Módulos A3.1 y A3.2 en el repo | Pendiente |
| A3.6 | Pantalla de configuración (guardar/cargar umbrales y calibración) — RF10 | — | Pendiente |
| A5.4 | Manual de usuario de la interfaz — RNF4 | — | Pendiente |

## Cómo completarlo

1. **Una fila por tarea y por persona.** Si una tarea la hicieron dos personas, se separa en dos filas o se nombran ambas en *Responsable*.
2. **Evidencia = algo que se pueda abrir:** commit, archivo o carpeta del repo, captura, o video. Un link a un commit sirve como "evidencia de desarrollo"; una captura o CSV, como "evidencia de resultados".
3. **Resultado = lo que se obtuvo y se verificó**, incluyendo lo que no funcionó (ejemplo: "medidas no interpretables").
4. Si el Excel pide horas, avance (%) u otra columna, agregarla; aquí no se inventaron horas.
