# AgroVision

Proyecto de TEL328 para inspeccionar tomates mediante imágenes y videos RGB.
La interfaz web local permite ver detecciones, máscaras e IDs, consultar calibre,
peso estimado, madurez visual y manchas, y exportar los resultados de la sesión.

## Preparar el entorno virtual

Usa Python 3.14 y ejecuta los comandos desde la raíz del repositorio, donde están
las carpetas `web/`, `funciones/` y `config/`.

Crea el entorno una vez por equipo. Actívalo cada vez que abras una terminal para
trabajar en el proyecto.

### Windows con PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, abre Símbolo del sistema (CMD) en la misma
carpeta y activa el entorno ya creado:

```bat
.venv\Scripts\activate.bat
```

### Linux con Bash

```bash
python3.14 -m venv .venv
source .venv/bin/activate
```

### Instalar dependencias

Con el entorno activado, ejecuta el mismo comando en Windows o Linux:

```bash
python -m pip install -r requirements-tracking.txt
```

El archivo fija las versiones de OpenCV, NumPy y SciPy usadas por el procesamiento.
El servidor web utiliza la biblioteca estándar de Python.

Para salir del entorno virtual, ejecuta `deactivate`.

## Iniciar la interfaz web

Con el entorno activado:

```bash
python -m web.server
```

Abre [AgroVision local](http://127.0.0.1:8000) en el navegador del mismo equipo.
El servidor escucha en `127.0.0.1`. Mantén la terminal abierta durante la sesión.

Si el puerto 8000 está ocupado:

```bash
python -m web.server --puerto 8080
```

En ese caso abre [AgroVision en el puerto 8080](http://127.0.0.1:8080).
Para apagar el servidor, presiona `Ctrl+C` en la terminal.

## Probar con los archivos incluidos

1. Carga `dataset/fotos/summerlast.png` o uno de los cinco archivos
   `dataset/videos/tomates_sabana_gris_1.mp4` a
   `dataset/videos/tomates_sabana_gris_5.mp4`. Puedes arrastrarlos a la página o
   usar el selector de archivos.
2. Presiona **Iniciar** para procesar la fuente. Si cargas varios archivos,
   revisa su orden en la cola.
3. Alterna entre **Detecciones**, **Máscara HSV** y **Máscara limpia** para
   inspeccionar las etapas. Puedes ajustar los límites HSV y la zona de medición.
4. Consulta las observaciones actuales, los registros y las incidencias.
5. Abre **Dashboard** para consultar las estadísticas de la sesión o cargar un
   CSV anterior.
6. Usa **Guardar** para descargar los resultados disponibles de la sesión.

También puedes seleccionar una cámara que OpenCV reconozca en el equipo.

| Tecla | Acción |
|---|---|
| Q | Seleccionar archivos |
| W | Iniciar |
| S | Pausar o continuar |
| E | Guardar |
| R | Repetir |
| D | Abrir o cerrar el dashboard |
| Esc | Cerrar el dashboard o detener el procesamiento |

Los atajos se desactivan mientras escribes en un campo de entrada.

## Configuración y resultados

- `config/calib.json` contiene la escala, la zona y las condiciones de calibración.
- `config/perfiles/tomate.json` define los atributos y sus reglas.
- `config/peso_modelo_tomate.json` contiene el modelo de estimación de peso.
- `funciones/segmentación/`, `funciones/tracking/` y
  `funciones/caracteristicas/` contienen los módulos de procesamiento.
- `funciones/registro.py` gestiona el registro y la exportación.
- `interfaz/pipeline.py` conecta el procesamiento con la interfaz web.

El calibre y el peso requieren referencias físicas compatibles con el montaje.
Cambiar la distancia cámara-superficie exige revisar la calibración. Esa distancia
por sí sola no recalcula la escala en píxeles por milímetro. Revisa los estados
provisionales, fuera de rango y no evaluables antes de interpretar las medidas.

## Evidencias del Hito 2

- [Segmentación y resultados](docs/segmentacion.md)
- [Seguimiento y pruebas](docs/tracking/seguimiento.md)
- [Pruebas con los cinco videos](docs/pruebas_video_hito2.md)
- [Desarrollo de la interfaz web](docs/documentacion_trabajo.md)

Las evidencias describen la versión y las condiciones de cada ensayo.
