# AgroVision

Prototipo de inspección visual de tomates para TEL328. La versión actual muestra la máscara HSV, la máscara después de la apertura y el cierre, y una vista con los contornos, centroides e IDs.

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
python -m pip install opencv-python==5.0.0.93 numpy==2.5.4
```

## Prueba

```bash
python main_test.py --foto dataset/fotos/summerlast.png --salida-foto salida-foto
```

Para analizar un video, reemplaza la ruta de ejemplo por la del archivo:

```bash
python main_test.py "dataset/videos/piloto.mp4"
```

Consulta opciones, incluidos los límites HSV, con `python main_test.py --help`.
