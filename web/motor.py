"""
MOTOR DE LA INTERFAZ WEB

Mismo flujo que la GUI de Tkinter (`interfaz/app.py`) pero sin widgets: guarda el estado
de la sesión y el último resultado, y el servidor HTTP (`web/server.py`) los expone.
Reutiliza `interfaz/pipeline.py` y `interfaz/sesion.py`; no duplica lógica de visión.

Concurrencia: un hilo de captura escribe el estado; los hilos HTTP lo leen. Todo acceso
al estado compartido pasa por `self.lock`.
"""

import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np

from funciones.acq import SourceState, VideoSource
from interfaz.pipeline import PipelineInspeccion, leer_imagen
from interfaz.sesion import SesionRegistro

RAIZ = Path(__file__).resolve().parent.parent
MUESTRA = RAIZ / "dataset" / "fotos" / "summerlast.png"

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp"}
EXT_VIDEO = {".mp4", ".avi", ".mov", ".mkv"}
PERIODO_CUADRO = 1 / 25  # ritmo de reproducción, no velocidad de la cinta

ESPERANDO, LISTO, PROCESANDO, RESULTADO = "ESPERANDO", "LISTO", "PROCESANDO", "RESULTADO"

# Umbrales HSV por defecto de ClassicSegmenter y tope de cada canal (H 0-179, S y V 0-255).
HSV_DEFECTO = ((0, 70, 50), (179, 255, 255))
HSV_TOPE = (179, 255, 255)


class Motor:
    def __init__(self):
        self.lock = threading.RLock()
        self.carpeta_tmp = Path(tempfile.mkdtemp(prefix="agrovision_"))
        self.estado = ESPERANDO
        self.mensaje = "Esperando imagen/video"
        self.fuente = None          # ("archivo", Path, nombre) | ("camara", int, nombre)
        self.sesion = None
        self.ultimo = None          # ResultadoCuadro más reciente
        self.frame_id = 0
        self.cuadros = 0
        self.t_inicio = 0.0
        self.interrumpida = False
        self.detener_ev = threading.Event()
        self.hilo = None
        self.hsv = HSV_DEFECTO      # se reemplaza completo (tupla), nunca se muta
        self.frame_img = None       # imagen cargada, para la vista previa al mover los sliders
        self.calibracion = PipelineInspeccion().estado_calibracion

    # ------------------------------------------------------------- fuente
    def _ocupado(self):
        return self.hilo is not None and self.hilo.is_alive()

    def fijar_archivo(self, ruta, nombre):
        suf = Path(nombre).suffix.lower()
        if suf not in EXT_IMAGEN | EXT_VIDEO:
            return False, f"Formato no soportado: {suf or 'sin extensión'}"
        return self._fijar(("archivo", Path(ruta), Path(nombre).name))

    def fijar_camara(self, n):
        return self._fijar(("camara", int(n), f"Cámara {int(n)}"))

    def fijar_muestra(self):
        if not MUESTRA.exists():
            return False, "No se encontró la foto de ejemplo del dataset"
        return self._fijar(("archivo", MUESTRA, MUESTRA.name))

    def _fijar(self, fuente):
        with self.lock:
            if self._ocupado():
                return False, "Detén la sesión antes de cambiar la fuente"
            self.fuente = fuente
            self.estado = LISTO
            self.mensaje = f"Fuente lista: {fuente[2]}. Presiona Iniciar."
            return True, self.mensaje

    # --------------------------------------------------------- umbrales HSV
    def _aplicar_hsv(self, pipeline):
        minimo, maximo = self.hsv
        pipeline.segmentador.hsv_lower = np.array(minimo)
        pipeline.segmentador.hsv_upper = np.array(maximo)

    def fijar_hsv(self, minimo, maximo):
        """Cambia los umbrales de segmentación. Con una imagen cargada y sin sesión en
        curso, solo actualiza la vista previa: el registro no cambia hasta Iniciar."""
        try:
            minimo, maximo = tuple(int(v) for v in minimo), tuple(int(v) for v in maximo)
        except (TypeError, ValueError):
            return False, "Valores HSV inválidos"
        if len(minimo) != 3 or len(maximo) != 3 or any(
                not 0 <= lo <= hi <= tope for lo, hi, tope in zip(minimo, maximo, HSV_TOPE)):
            return False, "Cada límite debe cumplir 0 ≤ mínimo ≤ máximo ≤ tope del canal (H 179, S 255, V 255)"
        with self.lock:
            self.hsv = (minimo, maximo)
            if self._ocupado():
                if self.sesion:  # trazabilidad: el CSV registra los umbrales iniciales
                    self.sesion.incidencia(
                        "Configuración", f"Umbrales HSV cambiados durante la sesión a {list(minimo)}-{list(maximo)}")
                return True, "Umbrales HSV actualizados (se aplican al video en curso)"
            if self.frame_img is None:
                return True, "Umbrales HSV actualizados"
            try:
                pipeline = PipelineInspeccion()
                self._aplicar_hsv(pipeline)
                self.ultimo = pipeline.procesar(self.frame_img)
                self.frame_id += 1
            except Exception as exc:  # noqa: BLE001
                return False, f"No evaluable con esos umbrales: {exc}"
            return True, "Vista previa actualizada. Presiona Iniciar para registrar con estos umbrales."

    # ------------------------------------------------------------ control
    def iniciar(self):
        with self.lock:
            if self.fuente is None:
                return False, "Primero elige una fuente (archivo, cámara o foto de ejemplo)"
            if self._ocupado():
                return False, "Ya hay una sesión en curso"
            pipeline = PipelineInspeccion()
            self._aplicar_hsv(pipeline)
            id_sesion = time.strftime("S%Y%m%d_%H%M%S")
            minimo, maximo = self.hsv
            version = f"{pipeline.version_calibracion}; hsv={list(minimo)}-{list(maximo)}"
            self.sesion = SesionRegistro(id_sesion, self.fuente[2], version)
            self.frame_img = None
            self.sesion.incidencia("Calibración", pipeline.estado_calibracion, unica=True)
            self.ultimo, self.frame_id, self.cuadros = None, 0, 0
            self.interrumpida = False
            self.t_inicio = time.perf_counter()
            self.estado, self.mensaje = PROCESANDO, "Procesando…"
            tipo, valor, _ = self.fuente

            if tipo == "archivo" and valor.suffix.lower() in EXT_IMAGEN:
                self._procesar_imagen(valor, pipeline)
                return True, self.mensaje

            self.detener_ev = threading.Event()
            origen = str(valor) if tipo == "archivo" else int(valor)
            self.hilo = threading.Thread(
                target=self._trabajador,
                args=(origen, pipeline, self.sesion, self.detener_ev), daemon=True)
            self.hilo.start()
            return True, "Procesando…"

    def detener(self):
        with self.lock:
            if self._ocupado():
                self.detener_ev.set()
                self.mensaje = "Deteniendo…"
                return True, self.mensaje
            return False, "No hay una sesión en curso"

    def repetir(self):
        with self.lock:
            self.detener_ev.set()
            self.sesion, self.fuente, self.ultimo, self.frame_img = None, None, None, None
            self.frame_id, self.cuadros, self.interrumpida = 0, 0, False
            self.estado, self.mensaje = ESPERANDO, "Esperando imagen/video"
            return True, self.mensaje

    def cerrar(self):
        self.detener_ev.set()

    # ------------------------------------------------------ procesamiento
    def _procesar_imagen(self, ruta, pipeline):
        frame = leer_imagen(ruta)
        if frame is None:  # error de lectura: vuelve a "Esperando" (sección 6.1)
            self.sesion.incidencia("Fuente", f"No se pudo leer la imagen {ruta.name}")
            self.estado, self.fuente = ESPERANDO, None
            self.mensaje = "Error de lectura: vuelve a Esperando imagen/video"
            return
        self.frame_img = frame
        try:
            resultado = pipeline.procesar(frame)
        except Exception as exc:  # noqa: BLE001  error de procesamiento: "No evaluable"
            self.sesion.incidencia("Procesamiento", f"No evaluable: {exc}")
            self.estado, self.mensaje = RESULTADO, f"No evaluable ({exc})"
            return
        self._aplicar(resultado, {"frame_idx": 1, "timestamp": time.time()}, self.sesion)
        self.sesion.confirmar_ausentes(set())
        self.sesion.cerrar("Cierre de sesión")
        self.estado = RESULTADO
        self.mensaje = f"Imagen procesada: {len(resultado.observaciones)} objeto(s) detectado(s)"

    def _trabajador(self, origen, pipeline, sesion, detener):
        fuente = VideoSource(source=origen, session_id=sesion.id_sesion)
        try:
            while not detener.is_set():
                t0 = time.perf_counter()
                estado, meta, cuadro = fuente.read_frame()
                if meta["suspend_observations"]:
                    self._fuente_terminada(estado, meta, sesion, detener)
                    break
                self._aplicar_hsv(pipeline)  # recoge los sliders también durante el video
                try:
                    resultado = pipeline.procesar(cuadro)
                except Exception as exc:  # noqa: BLE001
                    with self.lock:
                        if not detener.is_set():
                            sesion.incidencia("Procesamiento",
                                              f"Cuadro {meta['frame_idx']} no evaluable: {exc}")
                    continue
                self._aplicar(resultado, meta, sesion, detener)
                detener.wait(max(0.0, PERIODO_CUADRO - (time.perf_counter() - t0)))
        finally:
            fuente.release()
            with self.lock:
                if not detener.is_set():
                    sesion.cerrar("Cierre de sesión")
                    if self.estado == PROCESANDO:
                        self.estado = RESULTADO
                elif self.sesion is sesion:  # detenida por el usuario
                    sesion.cerrar("Cierre de sesión")
                    self.estado, self.mensaje = RESULTADO, "Sesión detenida"

    def _aplicar(self, resultado, meta, sesion, detener=None):
        with self.lock:
            if detener is not None and detener.is_set():
                return  # sesión descartada con Repetir: no contaminar la siguiente
            for obs in resultado.observaciones:
                if obs.id is None and not obs.valida:
                    sesion.incidencia("Segmentación", f"{obs.causa} (no se mide)", unica=True)
                sesion.observar(obs, meta["frame_idx"], meta["timestamp"])
            sesion.confirmar_ausentes(resultado.ids_activos)
            self.ultimo = resultado
            self.frame_id += 1
            self.cuadros += 1

    def _fuente_terminada(self, estado, meta, sesion, detener):
        with self.lock:
            if detener.is_set():
                return
            if estado == SourceState.EOF and meta["frame_idx"] > 0:
                self.mensaje = "Fin del archivo de video"
                return
            causa = ("No se pudo abrir la fuente" if meta["frame_idx"] == 0
                     else "Se perdió la señal de la fuente")
            sesion.incidencia("Fuente", f"{causa} ({estado.value})")
            sesion.cerrar("Interrumpido")
            self.interrumpida = True  # RF8: lo visible ya no es una observación actual
            self.mensaje = f"Fuente interrumpida: {estado.value}. {causa}."

    # ------------------------------------------------------------ lectura
    def imagen(self, vista):
        """Devuelve (ndarray, frame_id) de la vista pedida, o (None, id)."""
        with self.lock:
            r = self.ultimo
            if r is None:
                return None, self.frame_id
            img = {"detecciones": r.anotado, "mascara": r.mascara_hsv,
                   "limpia": r.mascara_limpia}.get(vista, r.anotado)
            return img, self.frame_id

    def estado_json(self):
        with self.lock:
            seg = max(time.perf_counter() - self.t_inicio, 1e-6) if self.t_inicio else 1.0
            obs, reg, inc = [], [], []
            if self.ultimo:
                obs = [{"id": o.id, "ancho_px": o.ancho_px, "ancho_mm": o.ancho_mm,
                        "calibre": o.calibre, "estado_calibre": o.estado_calibre,
                        "madurez": o.madurez, "manchas": o.manchas,
                        "validez": o.validez, "valida": o.valida and o.en_zona}
                       for o in self.ultimo.observaciones]
            if self.sesion:
                reg = [{k: v for k, v in f.items() if not k.startswith("_")}
                       for _, f in sorted(self.sesion.filas.items())]
                inc = [{"hora": h, "origen": o, "causa": c} for h, o, c in self.sesion.incidencias]
            return {
                "estado": self.estado, "mensaje": self.mensaje,
                "fuente": self.fuente[2] if self.fuente else None,
                "sesion": self.sesion.id_sesion if self.sesion else None,
                "cuadros": self.cuadros, "frame_id": self.frame_id,
                "fps": round(self.cuadros / seg, 1) if self._ocupado() else None,
                "ocupado": self._ocupado(), "interrumpida": self.interrumpida,
                "calibracion": self.calibracion,
                "hsv": {"min": list(self.hsv[0]), "max": list(self.hsv[1]),
                        "defecto_min": list(HSV_DEFECTO[0]), "defecto_max": list(HSV_DEFECTO[1])},
                "observaciones": obs, "registro": reg, "incidencias": inc,
                "puede_guardar": bool(self.sesion and self.sesion.filas),
            }

    def dashboard_json(self):
        with self.lock:
            filas = self.sesion.filas_definitivas() if self.sesion else []
            total = len(self.sesion.filas) if self.sesion else 0

            def contar(campo):
                return dict(Counter(f[campo] for f in filas if f.get(campo)))

            return {"definitivos": len(filas), "provisionales": total - len(filas),
                    "madurez": contar("madurez"), "manchas": contar("manchas"),
                    "calibre": contar("calibre")}

    def exportar_csv(self):
        """Escribe el CSV en una carpeta temporal y devuelve (ok, ruta_o_mensaje)."""
        with self.lock:
            if not self.sesion or not self.sesion.filas:
                return False, "No hay registros para guardar todavía"
            ruta = self.carpeta_tmp / f"registro_{self.sesion.id_sesion}.csv"
            ok, msg = self.sesion.exportar_csv(ruta)
            if not ok:
                self.sesion.incidencia("Exportación", msg)
                return False, msg
            return True, ruta
