# Cambios respecto al Documento de Análisis y Diseño v1.1

**Documento base:** `AgroVision_Analisis_y_Diseno_B01_v1.1.docx` (03/11/2026)
**Alcance de este registro:** lo que cambia, se agrega o no coincide entre el documento y el repositorio, desde la parte de interfaz (A3.6).
**Estado:** propuesto, para revisión del equipo. Un cambio al documento de diseño lo decide el equipo, no una sola persona.
**Verificado contra:** repositorio en la rama `main` (commit `637c150`, 05/11/2026) y ramas `feat/interfaz-funcional`, `feat/interfaz-web`.

Leyenda de tipo: **Cambio** (decisión nueva a aprobar) · **Adición** (algo que el documento no describe) · **Corrección** (el documento afirma algo que el repo no respalda) · **Pendiente** (el documento lo exige y aún no existe).

---

## A. Cambios y adiciones en la interfaz (decisiones a aprobar)

| # | Sección v1.1 | Dice la v1.1 | Qué se hizo / propone | Tipo | Por qué |
|---|---|---|---|---|---|
| C1 | 1.2 y 6 ("prototipo de escritorio") | Interfaz de escritorio | Se mantiene la GUI de escritorio (Tkinter) y se agrega una interfaz web local (`python -m web.server`, navegador en `127.0.0.1`) que reutiliza el mismo pipeline | Cambio | Mostrar las etapas del procesamiento de forma didáctica y con mejor presentación. La web corre solo en el equipo local y no añade dependencias (solo librería estándar de Python) |
| C2 | 6.1 vs 6.2.1 | El texto de 6.1 usa **G** (guardar) y **C** (nueva captura); la tabla 6.2.1 usa **E** y **W** | Se implementó la tabla 6.2.1 (Q, W, E, R, D, Esc). Hay que corregir el texto de 6.1 | Corrección | El propio documento se contradice |
| C3 | 6.2.1 (tabla de eventos) | No existe un evento para detener | Se agrega **Detener (S)** y selección de **cámara n°** | Adición | RF1 exige iniciar y detener la sesión desde la interfaz |
| C4 | 6.2 / RF6 / RF8 | Un solo panel de resultados | Tres pestañas: **Observaciones actuales**, **Registro de sesión** (una fila por ID) e **Incidencias**. Ante una interrupción de la fuente, se rotula "Últimos resultados — anteriores a la interrupción" | Adición | Cumplir RF6 (actual vs. finalizado) y RF8 (avisos distintos de resultados) |
| C5 | 6.2.2 Dashboard | Gráficas de Madurez, Calidad y Calibre | Solo cuenta registros **definitivos** (los provisionales no entran). Madurez y Calidad muestran "Sin datos" mientras A3.1/A3.2 no estén integradas. Selector de fruto con solo "Tomate" | Cambio | M6 indica que los provisionales no ingresan a agregados definitivos; el catálogo habilitado hoy es solo tomate |
| C6 | 6.2.1 "Capturar (W)" | Cargar vista, procesar, borrar resultado anterior | Implementado como **Iniciar**; cada W crea una sesión nueva y pide confirmación si hay registros sin guardar | Adición | Evitar perder datos por accidente |
| C7 | RF4 / RF10 | Calibración con estado de validez | `config/calib.json` gana la clave `"validated": false`. Mientras sea falsa, la UI y el CSV rotulan "Estimado (calibración pendiente de validar)" | Cambio | Honestidad de la medida hasta completar T2.5.1 |
| C8 | RF9 / 5.3 | Criterio fijo y versionado para elegir la observación del paso | Se elige la más cercana al centro de la zona de medición (el ejemplo de 5.3). **Aún no está versionado** | Adición | Permite consolidar una fila por ID |
| C9 | RF7 / M6 | Registro con versiones de modelo, perfil y calibración | El registro de la interfaz (`interfaz/sesion.py`) guarda solo la versión de calibración. Estados de fila: Provisional, Confirmado, Cierre de sesión, Interrumpido | Cambio | Es un registro provisional hasta integrar `funciones/registro.py` (M6) |

| C10 | 6.2 / 5.2 (no descrito) | La interfaz solo muestra resultados | En la web se agregan **sliders HSV** para ajustar la segmentación y ver la máscara; los umbrales quedan en el CSV y los cambios a mitad de video se registran como incidencia | Adición | Facilita ajustar la segmentación (A2.3) y explicar el pipeline |

| C11 | 6.2 / RF9 / RF7 | La zona de medición sale fija de `config/calib.json` (`valid_zone_bbox`); el CSV tiene un solo formato | En la web la **zona de medición parte como el cuadro completo** y se arrastra y redimensiona sobre el video; **ya no se usa `valid_zone_bbox`** y el cambio no modifica `calib.json`. Queda en el CSV (`roi=[x, y, ancho, alto]`) y, si ocurre a mitad de video, como incidencia. Al guardar se descargan **dos CSV**: **Excel** (`;`, coma decimal, columnas legibles) y **datos** (`,`, nombres técnicos) | Cambio | Ajustar la zona a cada montaje y abrir el registro en Excel en español. Riesgo: la zona sin distorsión de la lente ya no se aplica por defecto; hay que validarlo contra pie de metro (T2.5.1) |
| C12 | 6.1 / RF1 | Una sola imagen, video o cámara por sesión | La web admite una **cola de varios archivos**: se procesan uno tras otro, cada uno con su propia sesión (los IDs no se mezclan entre archivos) y se guarda **un CSV con las filas de toda la cola** (columna *fuente*). La cámara no admite cola | Adición | Procesar varias pasadas o videos en una misma corrida |
| C13 | 6.2 / RNF4 | Una sola pantalla de procesamiento | La web tiene un **Modo didáctico** (interruptor, apagado por defecto y recordado en el navegador): muestra las etapas intermedias (máscara HSV y limpia), un esquema del flujo con los módulos M1–M6 y el detalle del pipeline. Apagado, queda la vista de operación solo con detecciones | Adición | Separar la vista del operador de la que sirve para explicar y ajustar el procesamiento |

## B. Afirmaciones del documento que el repositorio no respalda

| # | Sección v1.1 | Afirmación | Lo verificado | Tipo |
|---|---|---|---|---|
| D1 | 7.1 | Existen `funciones/madurez.py`, `funciones/manchas.py` y `funciones/registro.py`, y `main_test.py` integra todo con `--salida-csv` | `funciones/` contiene solo `acq`, `calib`, `seg`, `track`, `track_kalman`. Ninguno de los tres archivos aparece en el historial de git. `main_test.py` solo importa `acq`, `seg` y `track` y no tiene `--salida-csv` | Corrección |
| D2 | 3.3 | Avance A3.1 = 70 %, A3.2 = 70 %, A3.5 = 90 % | Sin esos módulos en el repo no hay evidencia verificable. O se suben los archivos o se corrigen los porcentajes | Corrección |
| D3 | 7.2 | Pipeline integrado: ancho 32,47 mm, madurez «Maduro», fila en CSV | Los **32,47 mm se reproducen** (interfaz, foto `summerlast.png`). «Maduro» y la exportación vía `main_test.py` **no son reproducibles** con el código actual | Corrección |
| D4 | 7.3 y 3.3 (A3.6 = 0 %) | La interfaz "aún no está implementada" | Existe un prototipo funcional (Tkinter y web). Hay que actualizar la sección y el porcentaje | Corrección |
| D5 | 3.3 / 3.4 | Responsable de A3.6: Fernando Cataldo (miembro1) | El trabajo de interfaz lo hace Cristobal Fuentes. **Confirmar el responsable en el documento** | Corrección |
| D6 | `docs/adaptacion.md` | Filas para `madurez`, `manchas`, `registro`, integración de `main_test.py` y una GUI "ya probada en sintaxis" | Mismos módulos ausentes (D1). Además cita `config/calibration.json` (el real es `config/calib.json`) y `modelo/scripts/` (el real es `modelo/*.py`) | Corrección |
| D7 | 2.4.3 / A4.1 | Dataset de entrenamiento versionado | `dataset_marged_yolo/data.yaml` apunta a una ruta de otro equipo (`G:/Programing/...`), por lo que no funciona en otra máquina | Corrección |

## C. Requisitos del documento aún sin cubrir en la interfaz

| # | Requisito | Estado |
|---|---|---|
| P1 | RF3 madurez y RF5 manchas | Columnas "Pendiente" (A3.1/A3.2 no integradas) |
| P2 | RF2 tipo de producto y estado "no confirmado" | El tipo sale como "Tomate (asumido, sin modelo de tipo)"; depende de OE4 |
| P3 | OE3 "peso estimado" en pantalla | No está; A3.4 requiere datos de balanza |
| P4 | RF10 guardar y cargar configuración desde la interfaz | No implementado |
| P5 | RF7 / RNF3 versiones de modelo y perfil en el CSV | No implementado (no hay modelo ni perfiles integrados) |
| P6 | RNF2 latencia (percentil 95) | Solo se muestran FPS de proceso; no se mide latencia |
| P7 | A3.3 cortes de calibre oficiales | Se usan 55 y 70 mm **provisionales** solo para clasificar y graficar |
| P8 | RF1 cámara en vivo | Implementado, **sin probar con una cámara real** |
| P9 | Tracker | La interfaz usa `CentroidTracker`; `track_kalman.py` existe pero no está conectado |
| P10 | RNF4 manual de usuario | No existe |
| P11 | Integración con la rama `vicferx/tracking-base-y-contrato` | Esa rama mueve `track.py` y `track_kalman.py` a `funciones/tracking/`. `interfaz/pipeline.py` ya acepta ambas ubicaciones. Al integrar, hay que revisar también su cambio en `interfaz/app.py` (que aún importa módulos inexistentes) |
| P12 | Videos reales de la cinta (`dataset/video/*`, 464×832 px) | `config/calib.json` y la zona de medición no corresponden a estas grabaciones; las medidas en mm no son interpretables hasta calibrar (T2.5.1) |
