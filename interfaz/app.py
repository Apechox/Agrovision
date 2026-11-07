"""
INTERFAZ GRÁFICA DE AGROVISION (Actividad A3.6) — Tkinter

Ejecutar desde la carpeta que contiene `main_test.py`:
    python -m interfaz.app

Eventos de la sección 6.2.1 del documento de diseño:
    (Q) Adjuntar imagen/video   (W) Iniciar procesamiento   (S) Detener
    (E) Guardar CSV + vista     (R) Repetir                 (D) Dashboard   (Esc) Salir

Diseño:
- La visión vive en `interfaz/pipeline.py` (usa seg/track/calib); aquí solo hay UI.
- Video y cámara se procesan en un hilo; el hilo NO toca widgets: deja mensajes en una
  cola y la ventana los consume con `after()` (única forma segura en Tkinter).
- Cada corrida usa su propia cola y su propio Event, así un hilo viejo no contamina una
  corrida nueva.
- Los estados se comunican con texto además de color (RNF4).
"""

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from funciones.acq import SourceState, VideoSource
from interfaz.dashboard import mostrar_dashboard
from interfaz.pipeline import PipelineInspeccion, leer_imagen
from interfaz.sesion import SesionRegistro

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp"}
EXT_VIDEO = {".mp4", ".avi", ".mov", ".mkv"}
PERIODO_CUADRO = 1 / 25  # ritmo de reproducción de video, no velocidad de la cinta
REFRESCO_MS = 40
import main_test2 as pipeline  # reutiliza evaluate_instances / build_row / annotate
from funciones.acq import SourceState, VideoSource
from funciones.caracteristicas.calib import Calibrator
from funciones.caracteristicas.madurez import ColorMaturityClassifier
from funciones.caracteristicas.manchas import DarkSpotDetector
from funciones.registro import SessionRegistry
from funciones.seg import ClassicSegmenter
from funciones.tracking.track_kalman import KalmanCentroidTracker

ESPERANDO, LISTO, PROCESANDO, RESULTADO = "ESPERANDO", "LISTO", "PROCESANDO", "RESULTADO"

COLUMNAS_ACTUAL = [("id", "ID", 50), ("ancho_px", "Ancho (px)", 80), ("ancho_mm", "Ancho (mm)", 85),
                   ("calibre", "Calibre", 80), ("estado_calibre", "Estado calibre", 210),
                   ("madurez", "Madurez", 80), ("manchas", "Manchas", 80),
                   ("validez", "Validez", 180)]
COLUMNAS_REGISTRO = [("id", "ID", 50), ("cuadro", "Cuadro", 60), ("ancho_mm", "Ancho (mm)", 85),
                     ("calibre", "Calibre", 80), ("estado_registro", "Estado del registro", 150)]
COLUMNAS_INCIDENCIAS = [("hora", "Hora", 70), ("origen", "Origen", 130), ("causa", "Causa", 420)]


class AgroVisionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AgroVision")
        self.geometry("1180x700")
        self.minsize(960, 580)

        # OJO: no llamar `self.state`; pisaría el método state() de tk.Tk.
        self.estado_app = ESPERANDO
        self.fuente = None  # ("archivo", Path) | ("camara", int)
        self.sesion = None
        self.cola = queue.Queue()
        self.detener = threading.Event()
        self.hilo = None
        self.ultimo_anotado = None
        self.cuadros_vistos = 0
        self.t_inicio = 0.0
        self._foto = None
        self._version_vista = -1
        self._n_incidencias_vistas = 0

        self._construir_ui()
        self._atar_teclas()
        self._estado("Esperando imagen/video. Adjunta un archivo (Q) o elige la cámara.")
        self.protocol("WM_DELETE_WINDOW", self.salir)
        self.after(REFRESCO_MS, self._drenar_cola)

    # ------------------------------------------------------------------ UI
    def _construir_ui(self):
        raiz = ttk.Frame(self, padding=8)
        raiz.pack(fill="both", expand=True)

        izq = ttk.Frame(raiz)
        izq.pack(side="left", fill="both", expand=True)
        ttk.Label(izq, text="Video / imagen en inspección", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(izq, bg="#1e1e1e", highlightthickness=1, highlightbackground="#888")
        self.canvas.pack(fill="both", expand=True, pady=(4, 0))
        self._texto_canvas("Área de la imagen/video del fruto a procesar")

        der = ttk.Frame(raiz, width=560)
        der.pack(side="right", fill="both", padx=(10, 0))
        der.pack_propagate(False)

        fuente = ttk.LabelFrame(der, text="Fuente", padding=6)
        fuente.pack(fill="x")
        self.lbl_fuente = ttk.Label(fuente, text="Sin fuente seleccionada", wraplength=520)
        self.lbl_fuente.pack(anchor="w")
        fila = ttk.Frame(fuente)
        fila.pack(fill="x", pady=(4, 0))
        ttk.Label(fila, text="Cámara n°:").pack(side="left")
        self.var_camara = tk.IntVar(value=0)
        ttk.Spinbox(fila, from_=0, to=9, width=4, textvariable=self.var_camara).pack(side="left", padx=4)
        ttk.Button(fila, text="Usar cámara", command=self.usar_camara).pack(side="left")

        self.nb = ttk.Notebook(der)
        self.nb.pack(fill="both", expand=True, pady=(8, 0))

        tab_actual = ttk.Frame(self.nb, padding=4)
        self.nb.add(tab_actual, text="Observaciones actuales")
        self.lbl_actual = ttk.Label(tab_actual, text="Sin observaciones", wraplength=520)
        self.lbl_actual.pack(anchor="w")
        self.tabla_actual = self._tabla(tab_actual, COLUMNAS_ACTUAL)

        tab_reg = ttk.Frame(self.nb, padding=4)
        self.nb.add(tab_reg, text="Registro de sesión")
        self.lbl_reg = ttk.Label(tab_reg, text="Una fila por tomate (por ID), no por cuadro.")
        self.lbl_reg.pack(anchor="w")
        self.tabla_reg = self._tabla(tab_reg, COLUMNAS_REGISTRO)

        tab_inc = ttk.Frame(self.nb, padding=4)
        self.nb.add(tab_inc, text="Incidencias")
        self.tabla_inc = self._tabla(tab_inc, COLUMNAS_INCIDENCIAS)

        barra = ttk.Frame(self, padding=(8, 0, 8, 4))
        barra.pack(fill="x")
        for texto, cmd in (("(Q) Adjuntar Imagen/Video", self.adjuntar),
                           ("(W) Iniciar procesamiento", self.iniciar_procesamiento),
                           ("(S) Detener", self.detener_sesion),
                           ("(E) Guardar", self.guardar),
                           ("(R) Repetir", self.repetir),
                           ("(D) Dashboard", self.abrir_dashboard),
                           ("(Esc) Salir", self.salir)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", expand=True, fill="x", padx=2)

        self.lbl_estado = ttk.Label(self, anchor="w", relief="sunken", padding=(6, 2))
        self.lbl_estado.pack(fill="x", side="bottom")

    def _tabla(self, padre, columnas):
        marco = ttk.Frame(padre)
        marco.pack(fill="both", expand=True, pady=(4, 0))
        tabla = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", height=10)
        for cid, titulo, ancho in columnas:
            tabla.heading(cid, text=titulo)
            tabla.column(cid, width=ancho, anchor="w", stretch=True)
        barra = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=barra.set)
        tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        tabla.tag_configure("aviso", foreground="#b25000")
        return tabla

    def _atar_teclas(self):
        acciones = {"q": self.adjuntar, "w": self.iniciar_procesamiento, "s": self.detener_sesion,
                    "e": self.guardar, "r": self.repetir, "d": self.abrir_dashboard}
        for tecla, accion in acciones.items():
            for t in (tecla, tecla.upper()):
                self.bind_all(t, lambda e, a=accion: self._tecla(a))
        self.bind_all("<Escape>", lambda e: self.salir())

    def _tecla(self, accion):
        # No robar teclas mientras se escribe en el selector de cámara.
        if isinstance(self.focus_get(), ttk.Entry):
            return
        accion()

    # ------------------------------------------------------------- Eventos
    def adjuntar(self):
        """(Q) Adjuntar Imagen/Video."""
        ruta = filedialog.askopenfilename(
            title="Adjuntar Imagen/Video",
            filetypes=[("Imagen o video", "*.png *.jpg *.jpeg *.bmp *.mp4 *.avi *.mov *.mkv"), ("Todos", "*.*")])
        if not ruta:
            return
        self._fijar_fuente(("archivo", Path(ruta)))

    def usar_camara(self):
        try:
            indice = int(self.var_camara.get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("AgroVision", "Indica un número de cámara válido (0, 1, 2…).")
            return
        self._fijar_fuente(("camara", indice))

    def _fijar_fuente(self, fuente):
        if self.hilo and self.hilo.is_alive():
            messagebox.showinfo("AgroVision", "Detén la sesión (S) antes de cambiar la fuente.")
            return
        self.fuente = fuente
        self.estado_app = LISTO
        self.lbl_fuente.configure(text=f"Fuente: {self._nombre_fuente()}")
        self._estado(f"Fuente lista: {self._nombre_fuente()}. Presiona W para iniciar.")

    def _nombre_fuente(self):
        if self.fuente is None:
            return "—"
        tipo, valor = self.fuente
        return valor.name if tipo == "archivo" else f"Cámara {valor}"

    def iniciar_procesamiento(self):
        """(W) Inicia una sesión nueva y borra el resultado anterior."""
        if self.fuente is None:
            messagebox.showwarning("AgroVision", "Primero adjunta una imagen/video (Q) o elige la cámara.")
            return
        if self.hilo and self.hilo.is_alive():
            return
        if not self._confirmar_descartar():
            return

        self._limpiar_vista()
        self.cuadros_vistos = 0
        self.t_inicio = time.perf_counter()
        pipeline_ref = PipelineInspeccion()
        id_sesion = time.strftime("S%Y%m%d_%H%M%S")
        self.sesion = SesionRegistro(id_sesion, self._nombre_fuente(), pipeline_ref.version_calibracion)
        self.sesion.incidencia("Calibración", pipeline_ref.estado_calibracion, unica=True)
        self.estado_app = PROCESANDO
        self._estado("Procesando…")

        tipo, valor = self.fuente
        if tipo == "archivo" and valor.suffix.lower() in EXT_IMAGEN:
            self._procesar_imagen(valor, pipeline_ref)
            return
        if tipo == "archivo" and valor.suffix.lower() not in EXT_VIDEO:
            self.sesion.incidencia("Fuente", f"Formato no soportado: {valor.suffix}")
            self.estado_app = LISTO
            self._estado(f"Formato no soportado: {valor.suffix}")
            return

        self.cola = queue.Queue()
        self.detener = threading.Event()
        origen = str(valor) if tipo == "archivo" else int(valor)
        self.hilo = threading.Thread(
            target=self._trabajador, args=(origen, id_sesion, self.cola, self.detener), daemon=True)
        self.hilo.start()

    def detener_sesion(self):
        """(S) Detiene la captura/lectura; conserva lo ya registrado."""
        if self.hilo and self.hilo.is_alive():
            self.detener.set()
            self._estado("Deteniendo…")

    def guardar(self):
        """(E) Guarda CSV y vista anotada, con confirmación previa."""
        if not self.sesion or not self.sesion.filas:
            messagebox.showinfo("AgroVision", "No hay registros para guardar todavía.")
            return
        if not messagebox.askyesno(
                "AgroVision", f"¿Guardar {len(self.sesion.filas)} registro(s) en CSV y la vista anotada?"):
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="registro.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not ruta:
            return
        ok, msg = self.sesion.exportar_csv(ruta)
        if not ok:
            self.sesion.incidencia("Exportación", msg)
            messagebox.showerror("AgroVision", f"Incidencia: {msg}")
            return
        if self.ultimo_anotado is not None:
            png = Path(ruta).with_suffix(".png")
            try:
                cv2.imencode(".png", self.ultimo_anotado)[1].tofile(str(png))
                msg += f"\nVista anotada: {png}"
            except OSError as exc:
                self.sesion.incidencia("Exportación", f"No se pudo guardar la vista anotada: {exc}")
                msg += f"\nIncidencia: no se pudo guardar la vista anotada ({exc})"
        messagebox.showinfo("AgroVision", msg)

    def repetir(self):
        """(R) Vuelve al estado inicial de captura."""
        if not self._confirmar_descartar():
            return
        self.detener.set()
        self.cola = queue.Queue()  # descarta mensajes pendientes del hilo anterior
        self.sesion = None
        self.fuente = None
        self._limpiar_vista()
        self.lbl_fuente.configure(text="Sin fuente seleccionada")
        self.estado_app = ESPERANDO
        self._estado("Esperando imagen/video.")

    def abrir_dashboard(self):
        """(D) Abre las gráficas estadísticas."""
        mostrar_dashboard(self, self.sesion)

    def salir(self):
        """(Esc) Detiene el hilo, libera la fuente y cierra."""
        self.detener.set()
        if self.hilo and self.hilo.is_alive():
            self.hilo.join(timeout=1.5)
        if self.sesion:
            self.sesion.cerrar("Cierre de sesión")
        self.destroy()

    def _confirmar_descartar(self):
        if self.sesion and self.sesion.sin_guardar:
            return messagebox.askyesno(
                "AgroVision", "Hay registros sin guardar que se perderán. ¿Continuar?")
        return True

    # ------------------------------------------------------ Procesamiento
    def _procesar_imagen(self, ruta, pipeline_ref):
        frame = leer_imagen(ruta)
        if frame is None:
            # Un error de lectura vuelve a "Esperando imagen" (sección 6.1).
            self.sesion.incidencia("Fuente", f"No se pudo leer la imagen {ruta.name}")
            self.estado_app = ESPERANDO
            self.fuente = None
            self._estado("Error de lectura: vuelve a Esperando imagen/video.")
            return
        try:
            resultado = pipeline_ref.procesar(frame)
        except Exception as exc:  # noqa: BLE001
            # Un error de procesamiento muestra "No evaluable" (sección 6.1).
            self.sesion.incidencia("Procesamiento", f"No evaluable: {exc}")
            self.estado_app = RESULTADO
            self._estado(f"No evaluable ({exc})")
            return
        self._aplicar_resultado(resultado, {"frame_idx": 1, "timestamp": time.time()})
        self.sesion.confirmar_ausentes(set())
        self.sesion.cerrar("Cierre de sesión")
        self._mostrar(resultado, actual=True)
        self.estado_app = RESULTADO
        self._estado(f"Imagen procesada: {len(resultado.observaciones)} objeto(s) detectado(s).")

    def _trabajador(self, origen, id_sesion, cola, detener):
        """Hilo de video/cámara. Solo escribe en `cola`; nunca toca widgets."""
        fuente = VideoSource(source=origen, session_id=id_sesion)
        pipeline_ref = PipelineInspeccion()
        try:
            while not detener.is_set():
                t0 = time.perf_counter()
                estado, meta, cuadro = fuente.read_frame()
                if meta["suspend_observations"]:
                    cola.put(("fuente", estado, meta))
                    break
                try:
                    resultado = pipeline_ref.procesar(cuadro)
                except Exception as exc:  # noqa: BLE001
                    cola.put(("error", str(exc), meta))
                    continue
                cola.put(("cuadro", resultado, meta))
                detener.wait(max(0.0, PERIODO_CUADRO - (time.perf_counter() - t0)))
        finally:
            fuente.release()
            cola.put(("fin", None, None))

    def _drenar_cola(self):
        """Consume mensajes del hilo (se ejecuta en el hilo principal)."""
        ultimo = None
        while True:
            try:
                tipo, a, b = self.cola.get_nowait()
            except queue.Empty:
                break
            if tipo == "cuadro":
                self._aplicar_resultado(a, b)
                ultimo = a
                self.cuadros_vistos += 1
            elif tipo == "error":
                self.sesion.incidencia("Procesamiento", f"Cuadro {b['frame_idx']} no evaluable: {a}")
            elif tipo == "fuente":
                self._fuente_terminada(a, b)
            elif tipo == "fin":
                self._sesion_finalizada()
        if ultimo is not None:
            self._mostrar(ultimo, actual=True)
            seg = max(time.perf_counter() - self.t_inicio, 1e-6)
            self._estado(f"Fuente: {self._nombre_fuente()} · ACTIVO · cuadros: {self.cuadros_vistos} · "
                         f"{self.cuadros_vistos / seg:.1f} FPS de proceso")
        self._refrescar_registro()
        self.after(REFRESCO_MS, self._drenar_cola)

    def _aplicar_resultado(self, resultado, meta):
        for obs in resultado.observaciones:
            if obs.id is None and not obs.valida:
                self.sesion.incidencia("Segmentación", f"{obs.causa} (no se mide)", unica=True)
            self.sesion.observar(obs, meta["frame_idx"], meta["timestamp"])
        self.sesion.confirmar_ausentes(resultado.ids_activos)

    def _fuente_terminada(self, estado, meta):
        if estado == SourceState.EOF and meta["frame_idx"] > 0:
            self.sesion.cerrar("Cierre de sesión")
            self._estado("Fin del archivo de video.")
            return
        causa = ("No se pudo abrir la fuente" if meta["frame_idx"] == 0
                 else "Se perdió la señal de la fuente")
        self.sesion.incidencia("Fuente", f"{causa} ({estado.value})")
        self.sesion.cerrar("Interrumpido")
        # RF8: lo que queda en pantalla deja de ser una observación actual.
        self.lbl_actual.configure(
            text="⚠ ÚLTIMOS RESULTADOS — anteriores a la interrupción de la fuente", foreground="#b25000")
        self._estado(f"Fuente interrumpida: {estado.value}. {causa}.")

    def _sesion_finalizada(self):
        if self.estado_app == PROCESANDO:
            self.estado_app = RESULTADO

    # -------------------------------------------------------------- Render
    def _mostrar(self, resultado, actual):
        self._dibujar(resultado.anotado)
        self.ultimo_anotado = resultado.anotado
        if actual:
            self.lbl_actual.configure(
                text=f"Observaciones actuales: {len(resultado.observaciones)} objeto(s) en el cuadro",
                foreground="")
        self.tabla_actual.delete(*self.tabla_actual.get_children())
        for o in resultado.observaciones:
            mm = "—" if o.ancho_mm is None else f"{o.ancho_mm:.1f}"
            valores = ("—" if o.id is None else o.id, o.ancho_px, mm, o.calibre,
                       o.estado_calibre, o.madurez, o.manchas, o.validez)
            self.tabla_actual.insert("", "end", values=valores,
                                     tags=() if o.validez == "Válida" else ("aviso",))

    def _dibujar(self, bgr):
        ancho = max(self.canvas.winfo_width(), 100)
        alto = max(self.canvas.winfo_height(), 100)
        h, w = bgr.shape[:2]
        escala = min(ancho / w, alto / h)
        nuevo = cv2.resize(bgr, (max(1, int(w * escala)), max(1, int(h * escala))))
        self._foto = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(nuevo, cv2.COLOR_BGR2RGB)))
        self.canvas.delete("all")
        self.canvas.create_image(ancho // 2, alto // 2, image=self._foto)

    def _texto_canvas(self, texto):
        self.canvas.delete("all")
        self.canvas.create_text(20, 20, anchor="nw", fill="#cccccc", text=texto)

    def _refrescar_registro(self):
        if not self.sesion:
            return
        if self.sesion.version != self._version_vista:
            self._version_vista = self.sesion.version
            self.tabla_reg.delete(*self.tabla_reg.get_children())
            for _, f in sorted(self.sesion.filas.items()):
                mm = f["ancho_mm"] if f["ancho_mm"] != "" else "—"
                self.tabla_reg.insert("", "end", values=(f["id"], f["cuadro"], mm, f["calibre"],
                                                         f["estado_registro"]))
            prov = len(self.sesion.filas) - len(self.sesion.filas_definitivas())
            self.lbl_reg.configure(text=f"{len(self.sesion.filas)} registro(s) — {prov} provisional(es). "
                                        "Una fila por tomate (por ID), no por cuadro.")
        if len(self.sesion.incidencias) != self._n_incidencias_vistas:
            self._n_incidencias_vistas = len(self.sesion.incidencias)
            self.tabla_inc.delete(*self.tabla_inc.get_children())
            for fila in self.sesion.incidencias:
                self.tabla_inc.insert("", "end", values=fila, tags=("aviso",))
            self.nb.tab(2, text=f"Incidencias ({self._n_incidencias_vistas})")

    def _limpiar_vista(self):
        self._texto_canvas("Área de la imagen/video del fruto a procesar")
        self._foto = None
        self.ultimo_anotado = None
        self.tabla_actual.delete(*self.tabla_actual.get_children())
        self.tabla_reg.delete(*self.tabla_reg.get_children())
        self.tabla_inc.delete(*self.tabla_inc.get_children())
        self.lbl_actual.configure(text="Sin observaciones", foreground="")
        self.lbl_reg.configure(text="Una fila por tomate (por ID), no por cuadro.")
        self.nb.tab(2, text="Incidencias")
        self._version_vista = -1
        self._n_incidencias_vistas = 0

    def _estado(self, texto):
        self.lbl_estado.configure(text=f"Estado: {texto}")


def main():
    AgroVisionApp().mainloop()


if __name__ == "__main__":
    main()
