# AgroVision

Prototipo de inspección visual para TEL328, con tomate como primer producto. `main_test.py` muestra máscaras HSV y limpia, contornos, centroides e IDs. Los módulos de atributos y registro que requiere `main_test2.py` todavía no están completos en esta copia del repositorio.

La [guía de tracking](docs/tracking/seguimiento.md) reúne el método, los parámetros ensayados y los resultados.

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

Para el tracker con Kalman y asociación conjunta, instalar las dependencias verificadas:

```bash
python -m pip install -r requirements-tracking.txt
```

## Prueba

```bash
python main_test.py --foto dataset/fotos/summerlast.png --salida-foto salida-foto
```

Para analizar un video, reemplaza la ruta de ejemplo por la del archivo:

```bash
python main_test.py "dataset/videos/piloto.mp4"
```

El flujo de exportación está escrito en `main_test2.py`, pero requiere primero incorporar
`funciones/madurez.py`, `funciones/manchas.py` y `funciones/registro.py`. Los siguientes
comandos corresponden a esa integración pendiente; no son comandos comprobados:

```bash
python main_test2.py --foto dataset/fotos/summerlast.png --salida-csv salida/registro.csv
python main_test2.py "dataset/videos/piloto.mp4" --salida-csv salida/registro.csv --sesion PILOTO_01
```

Consulta opciones, incluidos los límites HSV, con `python main_test.py --help`.

## Interfaz gráfica (Tkinter)

Integración pendiente: además de los tres módulos mencionados, la GUI importa de
`main_test.py` funciones de atributos que actualmente están escritas en `main_test2.py`.

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

## Pruebas de tracking

```shell
python -m pip install -r requirements-tracking.txt
python -B -m unittest discover -s test -v
python -B -m examples.demo_tracking
```

La [guía de seguimiento](docs/tracking/seguimiento.md) explica cómo reproducir la demostración. Los [resultados sintéticos](salida-tracking/README.md) incluyen el video anotado y las observaciones por cuadro.
