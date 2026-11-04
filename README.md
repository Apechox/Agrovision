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

Implementa el modelo de navegación de la sección 6 del documento de diseño: adjuntar
imagen/video (Q), iniciar procesamiento (W), guardar (E), repetir (R), salir (Esc) y abrir
el dashboard (D) con los gráficos de Madurez Visual, Calidad Visual y Calibre Aparente.
Reutiliza el mismo pipeline que `main_test.py`, no duplica lógica de visión.

## Estado de calibración

`config/calib.json` trae un valor de `px_per_mm` de referencia. Antes de confiar en los
milímetros reportados hay que medirlo con el patrón físico y el pie de metro (tarea
T2.5.1); mientras tanto, el calibre se reporta como "Estimado (calibración pendiente de
validar)".
