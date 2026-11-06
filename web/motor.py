"""
MOTOR DE LA INTERFAZ WEB

Mismo flujo que la GUI de Tkinter (`interfaz/app.py`) pero sin widgets: guarda el estado
de la cola y el último resultado, y el servidor HTTP (`web/server.py`) los expone.
Reutiliza `interfaz/pipeline.py` y `interfaz/sesion.py`; no duplica lógica de visión.

Cola: se pueden cargar varios archivos. Cada archivo se procesa uno tras otro con su propia
sesión de registro (sus IDs de tracking no se mezclan con los de otro archivo) y al guardar
se exporta un solo CSV con las filas de toda la cola.

Concurrencia: un hilo de procesamiento escribe el estado; los hilos HTTP lo leen. Todo acceso
al estado compartido pasa por `self.lock`.
"""

import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from funciones.acq import SourceState, VideoSource
from interfaz.pipeline import PipelineInspeccion, leer_imagen
from interfaz.sesion import SesionRegistro, exportar_sesiones

RAIZ = Path(__file__).resolve().parent.parent
MUESTRA = RAIZ / "dataset" / "fotos" / "summerlast.png"

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp"}
EXT_VIDEO = {".mp4", ".avi", ".mov", ".mkv"}
PERIODO_CUADRO = 1 / 25  # ritmo de reproducción, no velocidad de la cinta

ESPERANDO, LISTO, PROCESANDO, RESULTADO = "ESPERANDO", "LISTO", "PROCESANDO", "RESULTADO"
EN_ESPERA, EN_PROCESO, TERMINADO, INTERRUMPIDO, DETENIDO, ERROR = (
    "En espera", "Procesando", "Listo", "Interrumpido", "Detenido", "Error")

ROI_MIN = 20  # lado mínimo de la zona de medición, en px
# Umbrales HSV por defecto de ClassicSegmenter y tope de cada canal (H 0-179, S y V 0-255).
HSV_DEFECTO = ((0, 70, 50), (179, 255, 255))
HSV_TOPE = (179, 255, 255)


def _es_imagen(fuente):
    return fuente[0] == "archivo" and fuente[1].suffix.lower() in EXT_IMAGEN


class Motor:
    def __init__(self):
        self.lock = threading.RLock()
        self.carpeta_tmp = Path(tempfile.mkdtemp(prefix="agrovision_"))
        self.estado = ESPERANDO
        self.mensaje = "Esperando imagen/video"
        self.cola = []              # [{"fuente": (tipo, valor, nombre), "estado": str, "sesion": SesionRegistro|None}]
        self.sesion = None          # sesión del archivo en proceso (o la última)
        self.ultimo = None          # ResultadoCuadro más reciente
        self.frame_id = 0
        self.cuadros = 0
        self.t_inicio = 0.0
        self.interrumpida = False
        self.detener_ev = threading.Event()
        self.hilo = None
        self.hsv = HSV_DEFECTO      # se reemplaza completo (tupla), nunca se muta
        self.roi = None             # zona de medición (x, y, ancho, alto); None = cuadro completo
        self.frame_vista = None     # cuadro fijo para la vista previa (imagen o 1.er cuadro de un video)
        self.calibracion = PipelineInspeccion().estado_calibracion
        self._n_archivo = 0         # para nombres únicos de subida
        self._n_sesion = 0          # para ids únicos de sesión
        self._lote = None

    # -------------------------------------------------------------- cola
    def _ocupado(self):
        return self.hilo is not None and self.hilo.is_alive()

    def ruta_subida(self, nombre):
        with self.lock:
            self._n_archivo += 1
            return self.carpeta_tmp / f"fuente_{self._n_archivo}{Path(nombre).suffix.lower()}"

    def _agregar(self, fuente):
        if any(it["fuente"][0] == "camara" for it in self.cola):
            return False, "La cámara no admite cola: vacía la cola para usar archivos"
        self.cola.append({"fuente": fuente, "estado": EN_ESPERA, "sesion": None})
        if not self._ocupado():
            self._mirar(fuente)
            self.estado = LISTO
            self.mensaje = f"{len(self.cola)} archivo(s) en la cola. Presiona Iniciar."
        return True, f"Agregado a la cola: {fuente[2]} ({len(self.cola)} en total)"

    def fijar_archivo(self, ruta, nombre):
        suf = Path(nombre).suffix.lower()
        if suf not in EXT_IMAGEN | EXT_VIDEO:
            return False, f"Formato no soportado: {suf or 'sin extensión'}"
        with self.lock:
            return self._agregar(("archivo", Path(ruta), Path(nombre).name))

    def fijar_muestra(self):
        if not MUESTRA.exists():
            return False, "No se encontró la foto de ejemplo del dataset"
        with self.lock:
            return self._agregar(("archivo", MUESTRA, MUESTRA.name))

    def fijar_camara(self, n):
        with self.lock:
            if self._ocupado():
                return False, "Detén la sesión antes de cambiar la fuente"
            if self.cola:
                return False, "Vacía la cola antes de usar la cámara"
            self.cola.append({"fuente": ("camara", int(n), f"Cámara {int(n)}"), "estado": EN_ESPERA, "sesion": None})
            self.frame_vista = None
            self.estado, self.mensaje = LISTO, f"Cámara {int(n)} lista. Presiona Iniciar."
            return True, self.mensaje

    def quitar(self, i):
        with self.lock:
            if not 0 <= i < len(self.cola):
                return False, "Ese archivo no está en la cola"
            if self.cola[i]["estado"] == EN_PROCESO:
                return False, "No se puede quitar el archivo que se está procesando: detén la sesión"
            nombre = self.cola.pop(i)["fuente"][2]
            self._tras_cambio_de_cola()
            return True, f"Quitado de la cola: {nombre}"

    def mover(self, de, a):
        """Cambia el orden de análisis: mueve el archivo `de` a la posición `a`.
        Solo se puede mover un archivo que sigue en espera."""
        with self.lock:
            n = len(self.cola)
            if not (0 <= de < n and 0 <= a < n):
                return False, "Posición inválida"
            if self.cola[de]["estado"] != EN_ESPERA:
                return False, "Solo se puede reordenar un archivo que sigue en espera"
            if de != a:
                self.cola.insert(a, self.cola.pop(de))
            return True, f"Orden actualizado: {self.cola[a]['fuente'][2]} ahora es el n.º {a + 1}"

    def vaciar(self):
        with self.lock:
            if self._ocupado():
                return False, "Detén la sesión antes de vaciar la cola"
            self.cola.clear()
            self._tras_cambio_de_cola()
            return True, "Cola vacía"

    def _tras_cambio_de_cola(self):
        if not self.cola:
            self.sesion, self.ultimo, self.frame_vista, self._lote = None, None, None, None
            self.frame_id = self.cuadros = 0
            self.interrumpida = False
            self.estado, self.mensaje = ESPERANDO, "Esperando imagen/video"
        elif not self._ocupado():
            self.sesion = next((it["sesion"] for it in reversed(self.cola) if it["sesion"]), None)

    def _mirar(self, fuente):
        """Muestra el primer cuadro de la fuente recién agregada para poder ajustar la zona
        y los umbrales antes de iniciar (no toca el registro)."""
        frame = None
        try:
            if _es_imagen(fuente):
                frame = leer_imagen(fuente[1])
            elif fuente[0] == "archivo":
                cap = cv2.VideoCapture(str(fuente[1]))
                try:
                    ok, frame = cap.read()
                    frame = frame if ok else None
                finally:
                    cap.release()
        except Exception:  # noqa: BLE001  la vista previa es opcional; el error real saldrá al iniciar
            frame = None
        if frame is not None:
            self.frame_vista = frame
            self._previsualizar()

    # --------------------------------------------------------- umbrales HSV
    def _aplicar_hsv(self, pipeline):
        minimo, maximo = self.hsv
        pipeline.segmentador.hsv_lower = np.array(minimo)
        pipeline.segmentador.hsv_upper = np.array(maximo)

    def fijar_hsv(self, minimo, maximo):
        """Cambia los umbrales de segmentación. Con una vista previa cargada y sin sesión en
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
                if self.sesion:  # trazabilidad: el CSV registra la configuración vigente por fila
                    self.sesion.incidencia(
                        "Configuración", f"Umbrales HSV cambiados durante la sesión a {list(minimo)}-{list(maximo)}")
                return True, "Umbrales HSV actualizados (se aplican al video en curso)"
            if self.frame_vista is None:
                return True, "Umbrales HSV actualizados"
            ok, msg = self._previsualizar()
            if not ok:
                return False, f"No evaluable con esos umbrales: {msg}"
            return True, "Vista previa actualizada. Presiona Iniciar para registrar con estos umbrales."

    def _previsualizar(self):
        """Reprocesa el cuadro de vista previa con la configuración actual (sin tocar el registro)."""
        try:
            pipeline = PipelineInspeccion()
            self._configurar(pipeline, self.frame_vista)
            self.ultimo = pipeline.procesar(self.frame_vista)
            self.frame_id += 1
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        return True, ""

    # ------------------------------------------------- zona de medición (ROI)
    def _roi_efectivo(self, ancho, alto):
        """Zona vigente para un cuadro de ancho×alto: el cuadro completo si no se personalizó;
        si se personalizó para otra resolución, se recorta a este cuadro."""
        if self.roi is None:
            return (0, 0, ancho, alto)
        x, y, w, h = self.roi
        x = min(max(x, 0), max(ancho - 1, 0))
        y = min(max(y, 0), max(alto - 1, 0))
        return (x, y, max(1, min(w, ancho - x)), max(1, min(h, alto - y)))

    def _configurar(self, pipeline, cuadro, sesion=None):
        """Aplica al pipeline los umbrales y la zona vigentes para este cuadro. Si hay sesión,
        deja en ella la configuración exacta con que se mide (queda en cada fila del CSV)."""
        self._aplicar_hsv(pipeline)
        alto, ancho = cuadro.shape[:2]
        pipeline.calibrador.valid_roi = list(self._roi_efectivo(ancho, alto))
        if sesion is not None:
            minimo, maximo = self.hsv
            sesion.version_calibracion = f"{pipeline.version_calibracion}; hsv={list(minimo)}-{list(maximo)}"

    def _dim_cuadro(self):
        """(ancho, alto) del último cuadro mostrado, o None si aún no hay ninguno."""
        if self.ultimo is None:
            return None
        alto, ancho = self.ultimo.anotado.shape[:2]
        return ancho, alto

    def _roi_cambiado(self, descripcion):
        if self._ocupado():
            if self.sesion:
                self.sesion.incidencia("Configuración", f"Zona de medición cambiada durante la sesión a {descripcion}")
            return True, "Zona actualizada (se aplica al video en curso)"
        if self.frame_vista is None:
            return True, "Zona actualizada"
        ok, msg = self._previsualizar()
        if not ok:
            return False, f"No evaluable con esa zona: {msg}"
        return True, "Vista previa actualizada. Presiona Iniciar para registrar con esta zona."

    def fijar_roi(self, x, y, ancho, alto):
        try:
            x, y, ancho, alto = (int(v) for v in (x, y, ancho, alto))
        except (TypeError, ValueError):
            return False, "Zona inválida: se esperan 4 números enteros"
        if ancho < ROI_MIN or alto < ROI_MIN or x < 0 or y < 0:
            return False, f"La zona debe empezar en 0 o más y medir al menos {ROI_MIN} px por lado"
        with self.lock:
            dim = self._dim_cuadro()
            if dim and (x + ancho > dim[0] or y + alto > dim[1]):
                return False, f"La zona se sale de la imagen ({dim[0]}×{dim[1]} px)"
            self.roi = (x, y, ancho, alto)
            return self._roi_cambiado(str([x, y, ancho, alto]))

    def restablecer_roi(self):
        """Vuelve a medir sobre el cuadro completo (es el valor por defecto)."""
        with self.lock:
            self.roi = None
            return self._roi_cambiado("cuadro completo")

    # ------------------------------------------------------------ control
    def iniciar(self):
        with self.lock:
            if not self.cola:
                return False, "Primero agrega una fuente (archivos, cámara o foto de ejemplo)"
            if self._ocupado():
                return False, "Ya hay una sesión en curso"
            if not any(it["estado"] == EN_ESPERA for it in self.cola):
                return False, "No quedan archivos en espera. Usa Repetir para reprocesar la cola."
            if self._lote is None:
                self._lote = time.strftime("S%Y%m%d_%H%M%S")
            self.cuadros, self.t_inicio = 0, time.perf_counter()
            self.interrumpida = False
            self.estado, self.mensaje = PROCESANDO, "Procesando…"
            self.detener_ev = threading.Event()
            self.hilo = threading.Thread(target=self._trabajador, args=(self.detener_ev,), daemon=True)
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
        """Descarta los resultados y deja toda la cola de nuevo en espera."""
        with self.lock:
            self.detener_ev.set()
            self.detener_ev = threading.Event()  # el hilo viejo queda descartado y no contamina
            for it in self.cola:
                it["estado"], it["sesion"] = EN_ESPERA, None
            self.sesion, self.ultimo, self._lote = None, None, None
            self.frame_id = self.cuadros = 0
            self.interrumpida = False
            if self.frame_vista is not None:
                self._previsualizar()
            self.estado = LISTO if self.cola else ESPERANDO
            self.mensaje = (f"{len(self.cola)} archivo(s) en la cola. Presiona Iniciar."
                            if self.cola else "Esperando imagen/video")
            return True, self.mensaje

    def cerrar(self):
        self.detener_ev.set()

    # ------------------------------------------------------ procesamiento
    def _vigente(self, detener):
        return self.detener_ev is detener

    def _trabajador(self, detener):
        """Procesa, uno tras otro, los archivos de la cola que están en espera."""
        try:
            while not detener.is_set():
                with self.lock:
                    item = next((it for it in self.cola if it["estado"] == EN_ESPERA), None)
                    if item is None or not self._vigente(detener):
                        break
                    self._n_sesion += 1
                    nombre = item["fuente"][2]
                    sesion = SesionRegistro(f"{self._lote}-{self._n_sesion}", nombre, "")
                    item["estado"], item["sesion"] = EN_PROCESO, sesion
                    self.sesion, self.interrumpida = sesion, False
                    pipeline = PipelineInspeccion()
                    sesion.incidencia("Calibración", pipeline.estado_calibracion, unica=True)
                    hechos = sum(1 for it in self.cola if it["estado"] != EN_ESPERA)
                    self.mensaje = f"Procesando {nombre} ({hechos} de {len(self.cola)})…"
                if _es_imagen(item["fuente"]):
                    self._procesar_imagen(item, pipeline, sesion, detener)
                else:
                    self._procesar_video(item, pipeline, sesion, detener)
        finally:
            with self.lock:
                if self._vigente(detener):
                    if self.estado == PROCESANDO:
                        self.estado = RESULTADO
                    if detener.is_set():
                        self.mensaje = "Sesión detenida"
                    elif not self.mensaje.startswith(("Fuente interrumpida", "Error")):
                        listos = sum(1 for it in self.cola if it["estado"] == TERMINADO)
                        self.mensaje = f"Cola procesada: {listos} de {len(self.cola)} archivo(s) completos"

    def _procesar_imagen(self, item, pipeline, sesion, detener):
        ruta = item["fuente"][1]
        frame = leer_imagen(ruta)
        with self.lock:
            if not self._vigente(detener):
                return
            if frame is None:  # error de lectura (sección 6.1): se marca y se sigue con el resto
                sesion.incidencia("Fuente", f"No se pudo leer la imagen {ruta.name}")
                item["estado"] = ERROR
                self.mensaje = f"Error de lectura en {ruta.name}"
                return
            self.frame_vista = frame
            self._configurar(pipeline, frame, sesion)
        try:
            resultado = pipeline.procesar(frame)
        except Exception as exc:  # noqa: BLE001  error de procesamiento: "No evaluable"
            with self.lock:
                if self._vigente(detener):
                    sesion.incidencia("Procesamiento", f"No evaluable: {exc}")
                    item["estado"] = ERROR
            return
        self._aplicar(resultado, {"frame_idx": 1, "timestamp": time.time()}, sesion, detener)
        with self.lock:
            if self._vigente(detener):
                sesion.confirmar_ausentes(set())
                sesion.cerrar("Cierre de sesión")
                item["estado"] = TERMINADO

    def _procesar_video(self, item, pipeline, sesion, detener):
        tipo, valor, _ = item["fuente"]
        origen = str(valor) if tipo == "archivo" else int(valor)
        fuente = VideoSource(source=origen, session_id=sesion.id_sesion)
        try:
            while not detener.is_set():
                t0 = time.perf_counter()
                estado, meta, cuadro = fuente.read_frame()
                if meta["suspend_observations"]:
                    self._fuente_terminada(estado, meta, sesion, item, detener)
                    break
                with self.lock:  # recoge los sliders y la zona también durante el video
                    self._configurar(pipeline, cuadro, sesion)
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
                if self._vigente(detener) and item["estado"] == EN_PROCESO:
                    sesion.cerrar("Cierre de sesión")
                    item["estado"] = DETENIDO if detener.is_set() else TERMINADO

    def _aplicar(self, resultado, meta, sesion, detener):
        with self.lock:
            if detener.is_set() or not self._vigente(detener):
                return  # sesión descartada con Repetir: no contaminar la siguiente
            for obs in resultado.observaciones:
                if obs.id is None and not obs.valida:
                    sesion.incidencia("Segmentación", f"{obs.causa} (no se mide)", unica=True)
                sesion.observar(obs, meta["frame_idx"], meta["timestamp"])
            sesion.confirmar_ausentes(resultado.ids_activos)
            self.ultimo = resultado
            self.frame_id += 1
            self.cuadros += 1

    def _fuente_terminada(self, estado, meta, sesion, item, detener):
        with self.lock:
            if detener.is_set() or not self._vigente(detener):
                return
            if estado == SourceState.EOF and meta["frame_idx"] > 0:
                self.mensaje = f"Fin de {item['fuente'][2]}"
                return
            causa = ("No se pudo abrir la fuente" if meta["frame_idx"] == 0
                     else "Se perdió la señal de la fuente")
            sesion.incidencia("Fuente", f"{causa} ({estado.value})")
            sesion.cerrar("Interrumpido")
            item["estado"] = INTERRUMPIDO
            self.interrumpida = True  # RF8: lo visible ya no es una observación actual
            self.mensaje = f"Fuente interrumpida: {item['fuente'][2]} — {estado.value}. {causa}."

    # ------------------------------------------------------------ lectura
    def _sesiones(self):
        return [it["sesion"] for it in self.cola if it["sesion"]]

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
            sesiones = self._sesiones()
            for s in sesiones:
                reg += [{k: v for k, v in f.items() if not k.startswith("_")}
                        for _, f in sorted(s.filas.items())]
                inc += [{"hora": h, "origen": o, "causa": c, "fuente": s.fuente} for h, o, c in s.incidencias]
            dim = self._dim_cuadro()
            roi = list(self._roi_efectivo(*dim)) if dim else None
            cola = [{"i": i, "nombre": it["fuente"][2],
                     "tipo": "cámara" if it["fuente"][0] == "camara" else (
                         "imagen" if _es_imagen(it["fuente"]) else "video"),
                     "estado": it["estado"], "registros": len(it["sesion"].filas) if it["sesion"] else 0}
                    for i, it in enumerate(self.cola)]
            return {
                "estado": self.estado, "mensaje": self.mensaje,
                "cola": cola,
                "sesion": self.sesion.id_sesion if self.sesion else None,
                "cuadros": self.cuadros, "frame_id": self.frame_id,
                "fps": round(self.cuadros / seg, 1) if self._ocupado() else None,
                "ocupado": self._ocupado(), "interrumpida": self.interrumpida,
                "calibracion": self.calibracion,
                "hsv": {"min": list(self.hsv[0]), "max": list(self.hsv[1]),
                        "defecto_min": list(HSV_DEFECTO[0]), "defecto_max": list(HSV_DEFECTO[1])},
                "roi": {"valor": roi, "cuadro": list(dim) if dim else None, "personalizada": self.roi is not None},
                "observaciones": obs, "registro": reg, "incidencias": inc,
                "puede_guardar": any(s.filas for s in sesiones),
            }

    def dashboard_json(self):
        with self.lock:
            sesiones = self._sesiones()
            filas = [f for s in sesiones for f in s.filas_definitivas()]
            total = sum(len(s.filas) for s in sesiones)

            def contar(campo):
                return dict(Counter(f[campo] for f in filas if f.get(campo)))

            return {"definitivos": len(filas), "provisionales": total - len(filas),
                    "madurez": contar("madurez"), "manchas": contar("manchas"),
                    "calibre": contar("calibre")}

    def exportar_csv(self, formato="excel"):
        """Escribe el CSV de toda la cola en una carpeta temporal y devuelve (ok, ruta_o_mensaje)."""
        with self.lock:
            sesiones = [s for s in self._sesiones() if s.filas]
            if not sesiones:
                return False, "No hay registros para guardar todavía"
            formato = "datos" if formato == "datos" else "excel"
            sufijo = "_datos" if formato == "datos" else ""
            ruta = self.carpeta_tmp / f"registro_{self._lote}{sufijo}.csv"
            ok, msg = exportar_sesiones(sesiones, ruta, formato)
            if not ok:
                if self.sesion:
                    self.sesion.incidencia("Exportación", msg)
                return False, msg
            return True, ruta
