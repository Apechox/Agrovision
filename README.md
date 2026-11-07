# AgroVision

Prototipo de inspección visual de tomates para TEL328. El flujo básico muestra la máscara HSV, la máscara después de la apertura y el cierre, y una vista con contornos, centroides e IDs. Permite procesar videos sin ventanas y guardar evidencia. El flujo ampliado de atributos y CSV tiene dependencias pendientes de integrar.

## Setup venv

Usa Python 3.14 y ejecuta los comandos desde la carpeta que contiene `main_test.py`. Crea el entorno una vez en cada equipo y actívalo cada vez que abras una terminal para trabajar en el proyecto. Mantén `.venv` local al equipo.

### PowerShell / CMD

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bat
.venv\Scripts\activate.bat
```

### Bash

```bash
python3.14 -m venv .venv
source .venv/bin/activate
```

### Dependencias

```bash
python -m pip install opencv-python==5.0.0.93 numpy==2.5.4 pillow matplotlib
```

`pillow` y `matplotlib` son para la interfaz gráfica (`interfaz/`); el pipeline de línea de
comandos (`main_test.py`) no las necesita.

## Prueba

```bash
python main_test.py --foto dataset/fotos/summerlast.png --salida-foto salida-foto
```

Para analizar un video, reemplaza la ruta de ejemplo por la del archivo:

```bash
python main_test.py "dataset/videos/piloto.mp4"
```

Para procesar un video completo y guardar las tres vistas juntas y un resumen técnico:

```bash
python main_test.py "../VIDEOS/tomates_sabana_gris_1.mp4" --tracker centroide --sin-ventanas --salida-video salidas/hito2/centroide/tomates_sabana_gris_1.mp4 --resumen salidas/hito2/centroide/resumen.json
```

Usa `--tracker kalman` para ejecutar el mismo flujo con el filtro de Kalman.
El MP4 conserva el FPS de entrada y muestra, de izquierda a derecha, las detecciones,
la máscara HSV y la máscara limpia. El JSON registra el hash del video, los parámetros
HSV, el seguidor, los cuadros procesados y los IDs asignados. Estos contadores requieren
anotaciones manuales para convertirse en métricas de exactitud.

Los videos originales deben estar disponibles en `../VIDEOS/`. Las salidas se guardan
localmente en `salidas/`, excluida de Git junto con `.venv/`.
Para cerrar el entorno ejecuta `deactivate`.

Consulta todas las opciones con `python main_test.py --help`.
El procedimiento, los resultados de los cinco clips y las incidencias están en
[Pruebas de video del Hito 2](docs/pruebas_video_hito2.md).

## Flujo ampliado pendiente de integración

`main_test2.py` agrega calibre, madurez, manchas y registro por ID. Requiere
`funciones/madurez.py`, `funciones/manchas.py` y `funciones/registro.py`,
ausentes del remoto revisado el 6 de noviembre de 2026. Su ayuda se puede consultar
con `python main_test2.py --help`. Las pruebas de CSV y atributos quedan pendientes
hasta integrar los módulos de sus responsables.

## Interfaz gráfica (Tkinter)

```bash
python -m interfaz.app
```

Eventos de la sección 6 del documento de diseño: adjuntar imagen/video (Q), iniciar
procesamiento (W), detener (S), guardar CSV + vista anotada (E), repetir (R), dashboard (D)
y salir (Esc). También acepta cámara en vivo (selector "Cámara n°").

Usa solo los módulos que existen hoy (`funciones/seg.py`, `track.py`, `calib.py`, `acq.py`)
a través de `interfaz/pipeline.py`. **Madurez y manchas (A3.1/A3.2) y el registro M6
(`funciones/registro.py`) aún no están en el repo**: sus columnas salen como "Pendiente" /
vacías, y `interfaz/sesion.py` es un registro provisional hasta integrar M6.

Pestañas: observaciones actuales, registro de sesión (una fila por ID) e incidencias.

## Interfaz web local

```bash
python -m web.server
```

Abre `http://127.0.0.1:8000`. Misma lógica que la interfaz Tkinter, con vistas por etapa
(detecciones, máscara HSV, máscara limpia) y una explicación del pipeline. No requiere
instalar nada más (solo librería estándar, OpenCV y NumPy); escucha únicamente en `127.0.0.1`.

Documentación: `docs/documentacion_trabajo.md` y `docs/cambios_vs_diseno.md`.
La interfaz depende de los mismos tres módulos pendientes. Su funcionamiento completo
queda pendiente de prueba. El código implementa el modelo de navegación de la sección 6 del documento de diseño: adjuntar
imagen/video (Q), iniciar procesamiento (W), guardar (E), repetir (R), salir (Esc) y abrir
el dashboard (D) con los gráficos de Madurez Visual, Calidad Visual y Calibre Aparente.
Reutiliza las funciones de evaluación y anotación de `main_test2.py`.

## Estado de calibración

`config/calib.json` trae un valor de `px_per_mm` de referencia. Antes de confiar en los
milímetros reportados hay que medirlo con el patrón físico y el pie de metro (tarea
T2.5.1); mientras tanto, el calibre se reporta como "Estimado (calibración pendiente de
validar)".
