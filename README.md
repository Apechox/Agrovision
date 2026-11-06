# AgroVision

Prototipo de inspección visual de tomates para TEL328. La versión actual muestra la máscara HSV, la máscara después de la apertura y el cierre, y una vista con los contornos, centroides e IDs, calibre estimado, madurez visual y manchas por tomate.

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

Para exportar el registro consolidado por tomate (RF7: calibre, madurez y manchas, una fila por ID):

```bash
python main_test.py --foto dataset/fotos/summerlast.png --salida-csv salida/registro.csv
python main_test.py "dataset/videos/piloto.mp4" --salida-csv salida/registro.csv --sesion PILOTO_01
```

Consulta opciones, incluidos los límites HSV, con `python main_test.py --help`.

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

## Estado de calibración

`config/calib.json` trae un valor de `px_per_mm` de referencia. Antes de confiar en los
milímetros reportados hay que medirlo con el patrón físico y el pie de metro (tarea
T2.5.1); mientras tanto, el calibre se reporta como "Estimado (calibración pendiente de
validar)".
