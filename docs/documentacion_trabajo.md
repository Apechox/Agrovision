# Documentación del trabajo realizado — Interfaz de usuario (A3.6)

**Proyecto:** AgroVision (TEL328) · **Hito:** 2 / I2
**Actividad:** A3.6 Interfaz gráfica (video, ID, medidas, controles, errores) · **OE:** OE3
**Fecha:** 06/11/2026 · **Ramas:** `feat/interfaz-funcional` (Tkinter), `feat/interfaz-web` (web local)
**Complemento:** `docs/cambios_vs_diseno.md` (qué difiere del documento de diseño v1.1)

---

## 1. Resumen

Se construyó una interfaz que muestra el video con la zona de medición, contornos, ID y ancho en mm; permite controlar la sesión; registra **una fila por tomate**; exporta CSV y vista anotada; informa incidencias; y grafica estadísticas. Existe en dos versiones que comparten el mismo código de visión: **Tkinter** (escritorio) y **web local**.

La interfaz usa **solo los módulos que existen hoy en el repositorio** (`acq`, `seg`, `track`, `calib`). Madurez y manchas figuran como *Pendiente*, porque `madurez.py`, `manchas.py` y `registro.py` no están en el repo (ver sección 6).

## 2. Punto de partida (verificado)

- `interfaz/app.py` y `interfaz/dashboard.py` existían desde el 04/11/2026 como esqueleto: importaban módulos inexistentes y la aplicación **fallaba al abrir** (`ModuleNotFoundError: funciones.madurez`).
- En `funciones/` solo existen: `acq.py`, `calib.py`, `seg.py`, `track.py`, `track_kalman.py`.
- `main_test.py` solo conecta `acq` → `seg` → `track` y muestra las vistas (no calcula calibre, madurez ni CSV).

## 3. Arquitectura

```
 Cámara / archivo ──► funciones/acq.py ──► interfaz/pipeline.py ──► interfaz/sesion.py ──► CSV
                       (VideoSource)         seg.py → track.py → calib.py   (1 fila por ID)
                                                    │
                       ┌────────────────────────────┴───────────────┐
                       ▼                                            ▼
              interfaz/app.py (Tkinter)                  web/motor.py + web/server.py
                                                          └─► web/static/ (HTML + CSS + JS)
```

| Archivo | Responsabilidad |
|---|---|
| `interfaz/pipeline.py` | Adaptador: segmenta, sigue, mide (px → mm) y anota. Expone también las máscaras intermedias |
| `interfaz/sesion.py` | Registro por ID, incidencias y exportación CSV (provisional, hasta integrar M6) |
| `interfaz/app.py` | Ventana Tkinter. El hilo de video no toca widgets: deja mensajes en una cola |
| `interfaz/dashboard.py` | Tres gráficas sobre registros definitivos |
| `web/motor.py` | Estado de sesión y hilo de captura para la versión web |
| `web/server.py` | Servidor HTTP local (solo librería estándar): JSON, video MJPEG, subida de archivos, CSV |
| `web/static/` | Página: vistas por etapa, explicación del pipeline, tablas, dashboard |

**Decisiones de diseño** (con su motivo):
1. *La visión no se duplica:* ambas interfaces llaman a `pipeline.py`. Si cambia la segmentación, cambia en las dos.
2. *Sin dependencias nuevas en la web:* se usó `http.server` de la librería estándar. Evita instalar FastAPI/Flask y mantiene el entorno reproducible (RNF1).
3. *Hilo separado para video:* para no congelar la interfaz (RNF5). Cada sesión usa su propio evento de parada, así una sesión descartada no contamina la siguiente.
4. *Dato ausente = vacío, nunca cero* (RF7). El guardado se confirma solo tras escribir con éxito.
5. *Seguridad de la web local:* escucha solo en `127.0.0.1` y rechaza peticiones con cabecera `Origin` ajena.

## 4. Cómo ejecutar

Desde la carpeta que contiene `main_test.py` (dependencias: `opencv-python`, `numpy`, `pillow`, `matplotlib`; la web solo necesita `opencv-python` y `numpy`):

```bash
python -m interfaz.app        # escritorio (Tkinter)
python -m web.server          # web: abrir http://127.0.0.1:8000
```

Atajos (ambas): **Q** adjuntar · **W** iniciar · **S** detener · **E** guardar · **R** repetir · **D** dashboard.

## 5. Cobertura de requisitos (estado real)

| Requisito | Estado | Evidencia |
|---|---|---|
| RF1 Adquisición, iniciar/detener | Parcial | Archivo probado; **cámara sin probar con hardware real** |
| RF4 Calibre aparente | Parcial | 32,47 mm en la foto de ejemplo; calibración **sin validar** (se rotula) |
| RF6 Interfaz | Cubierto (prototipo) | Video, zona, ID, medidas, estados, pestañas actual/registro |
| RF7 Registro por unidad y CSV | Parcial | Una fila por ID; CSV con vacíos; faltan versiones de modelo/perfil |
| RF8 Incidencias | Cubierto (prototipo) | Pestaña de incidencias; aviso de "resultados anteriores a la interrupción" |
| RF9 Seguimiento | Parcial | IDs por centroides; criterio de observación no versionado |
| RF11 Videos de prueba | Parcial | Probado con video sintético; falta video real de cinta |
| RF3 Madurez / RF5 Manchas | **No** | Módulos A3.1/A3.2 ausentes del repo |
| RF2 Tipo / RF10 Configuración | **No** | Dependen de OE4 y de una pantalla de configuración |
| RNF4 Español, unidades, texto + color | Cubierto | Estados con texto y color |

## 6. Pruebas realizadas

Todas automáticas o de humo, ejecutadas el 05–06/11/2026. **Ninguna con cámara real ni con video real de la cinta.**

| Prueba | Resultado |
|---|---|
| Interfaz Tkinter: abre, procesa la foto `dataset/fotos/summerlast.png`, un video sintético, exporta CSV y cierra | Correcto. Foto: 1 tomate, 276 px → **32,47 mm**, calibre "Pequeño" (corte provisional) |
| Video sintético (círculo cruzando la zona, 40 cuadros) | 40 cuadros, 1 registro, observación elegida en el cuadro 23 (el más cercano al centro) |
| Dashboard Tkinter y web | Abre sin errores |
| API web: estado, subida de video, formato no soportado (`.exe`), CSV, PNG, ruta fuera de `static/`, origen ajeno | 200 / 400 / 404 / 403 según corresponde |
| Vistas de video web (detecciones, máscara HSV, máscara limpia) | Las tres entregan imágenes distintas |
| Inspección visual en navegador | Sin errores de consola |

**No verificado:** cámara real, video real, rendimiento con carga (RNF2), sesiones largas (RNF5), uso por un operador (RNF4).

## 7. Limitaciones conocidas

1. Madurez y manchas pendientes; tipo de fruto asumido (sección 5 y `cambios_vs_diseno.md`, P1–P2).
2. Calibración `px_per_mm = 8.5` es un valor de referencia, no medido (tarea T2.5.1).
3. Cortes de calibre 55/70 mm provisionales (A3.3).
4. La medida usa el ancho de la caja delimitadora; con tomates rotados o tocándose puede sobreestimar.
5. En la web, el navegador tarda ~1 s en reflejar un cambio de vista.

## 8. Texto propuesto para el documento de diseño

*Es una propuesta; el porcentaje debe confirmarlo el equipo.*

**Tabla 3.3, fila A3.6:** avance sugerido **≈ 60 %** (criterio: 6 de 10 entregables cubiertos — ventana y controles, procesamiento de imagen, de video, registro por ID, CSV, dashboard — y pendientes: cámara real, integración de madurez/manchas, prueba con video real, manual de usuario).

**Sección 7.1 (agregar viñeta):**
> `interfaz/` (A3.6) — interfaz de escritorio (Tkinter) y web local que reutilizan un mismo adaptador (`interfaz/pipeline.py`) sobre `seg.py`, `track.py` y `calib.py`. Muestra video con zona de medición, ID y ancho en mm; registra una fila por ID; exporta CSV y vista anotada; lista incidencias y distingue resultados actuales de finalizados (RF6, RF7, RF8). Madurez y manchas figuran como «Pendiente» hasta integrar A3.1 y A3.2.

**Sección 7.2 (agregar):**
> Sobre la fotografía de referencia, la interfaz detectó un tomate de 276 px de ancho, equivalente a 32,47 mm con la escala de referencia (calibración pendiente de validar). Con un video sintético de 40 cuadros se obtuvo un registro por ID con la observación elegida más cercana al centro de la zona.

**Sección 7.3 (reemplazar la viñeta de A3.6):**
> A3.6 — Interfaz: prototipo funcional. Pendiente: prueba con cámara y video reales de la cinta, integración de madurez y manchas, pantalla de configuración (RF10), medición de latencia (RNF2) y manual de usuario (RNF4).

## 9. Procedencia y adaptación del código (para `docs/adaptacion.md`)

| Módulo | Base | Adaptación |
|---|---|---|
| `interfaz/pipeline.py`, `sesion.py`, `app.py`, `dashboard.py` | Esqueleto del repo (commits `0ed4954`, `77e4025`) y módulos propios `seg`, `track`, `calib`, `acq` | Reescritura completa: se eliminaron las dependencias a módulos inexistentes, se agregó registro por ID, incidencias, confirmación de guardado y hilo con cola |
| `web/motor.py`, `web/server.py`, `web/static/*` | Librería estándar de Python (`http.server`) y OpenCV (`cv2.imencode` para MJPEG). **No proviene de ejemplos del curso** | Desarrollo propio; reutiliza `pipeline.py` |

> **Declarar según la política del curso:** el código de esta interfaz fue desarrollado con asistencia de una herramienta de IA (Claude Code). Confirmar cómo debe declararse en la entrega.

## 10. Trazabilidad

| Cambio | Commit |
|---|---|
| Interfaz Tkinter funcional | `a74bd36` (rama `feat/interfaz-funcional`) |
| Interfaz web local y documentación | `0aa1bc1` (rama `feat/interfaz-web`) |
