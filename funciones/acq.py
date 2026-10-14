"""
MÓDULO DE ADQUISICIÓN DE VIDEO Y CÁMARA (Actividad A2.2)

¿CÓMO TRABAJAR AQUÍ?
1. Aquí está implementada la lectura desde cámara en vivo (pasando un int,
   ej. source=0) o archivo de video (pasando un str),
   junto con el contador de cuadros (`frame_idx`), identificador de sesión (`session_id`) y
   marca temporal (`timestamp`). Puedes agregar configuración de FPS o resolución en `_connect()`.
2. Aquí se controla la máquina de estados (`SourceState`). Cuando un video
   termina (`EOF`) o la cámara se desconecta (`SIGNAL_LOST`), el método activa automáticamente
   la bandera `"suspend_observations": True` y devuelve `frame = None` para que el resto del
   pipeline detenga las mediciones sin colapsar.

El método `read_frame()` SIEMPRE debe devolver una tupla de 3 elementos:
    (state, meta, frame)
Donde:
    - state: Instancia de `SourceState` (OK, EOF, SIGNAL_LOST, UNINITIALIZED)
    - meta: Diccionario con exactamente estas llaves:
        {
            "session_id": str,              # Nombre o código de la sesión actual
            "frame_idx": int,               # Número de cuadro leído (1, 2, 3...)
            "timestamp": float,             # Tiempo de captura en segundos (epoch)
            "source_state": str,            # Estado en texto ("ACTIVO", "FIN_DE_ARCHIVO", etc.)
            "suspend_observations": bool    # True si el frame es inválido y no se debe medir
        }
    - frame: Imagen en formato `np.ndarray` (BGR de OpenCV) o `None` si hubo fallo/fin de video.
"""

import cv2
import time
import os
from enum import Enum

class SourceState(Enum):
    OK = "ACTIVO"
    EOF = "FIN_DE_ARCHIVO"
    SIGNAL_LOST = "PERDIDA_DE_SENAL"
    UNINITIALIZED = "NO_INICIALIZADO"

class VideoSource:
    def __init__(self, source=0, session_id="SESION_01"):
        """
        Parámetros:
        - source: int para índice de cámara USB/integrada (ej. 0, 1) o str para ruta de video (.mp4).
        - session_id: Identificador único de la corrida para trazabilidad en el CSV final.
        """
        self.source = source
        self.session_id = session_id
        self.cap = None
        self.frame_idx = 0
        self.state = SourceState.UNINITIALIZED
        self._connect()

    def _connect(self):
        # =====================================================================
        # Inicialización de fuente
        # =====================================================================
        # Si es una ruta de archivo, verificar primero que el archivo exista
        if isinstance(self.source, str) and not os.path.exists(self.source):
            self.state = SourceState.SIGNAL_LOST
            return

        self.cap = cv2.VideoCapture(self.source)
        if self.cap is not None and self.cap.isOpened():
            self.state = SourceState.OK
        else:
            self.state = SourceState.SIGNAL_LOST

    def read_frame(self):
        """
        Lee el siguiente cuadro de la cámara o archivo de video y evalúa su validez.
        """
        timestamp = time.time()

        # =====================================================================
        # Suspensión por fallo previo
        # =====================================================================
        if self.state != SourceState.OK or self.cap is None:
            return self.state, self._build_meta(valid=False, ts=timestamp), None

        ret, frame = self.cap.read()

        # Si `ret` es False o el frame viene vacío, se interrumpió el flujo
        if not ret or frame is None:
            if isinstance(self.source, str):
                # En un archivo de video, llegar al final de los cuadros es FIN_DE_ARCHIVO
                self.state = SourceState.EOF
            else:
                # En una cámara en vivo, perder la lectura es PERDIDA_DE_SENAL
                self.state = SourceState.SIGNAL_LOST

            return self.state, self._build_meta(valid=False, ts=timestamp), None

        # Si la lectura fue exitosa, incrementamos el índice y habilitamos observaciones
        self.frame_idx += 1
        return self.state, self._build_meta(valid=True, ts=timestamp), frame

    def _build_meta(self, valid, ts):
        """Construye el diccionario estandarizado de metadatos del cuadro."""
        return {
            "session_id": self.session_id,
            "frame_idx": self.frame_idx,
            "timestamp": ts,
            "source_state": self.state.value,
            "suspend_observations": not valid
        }

    def release(self):
        """Libera el recurso de hardware o archivo de video."""
        if self.cap is not None:
            self.cap.release()
