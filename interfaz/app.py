"""
MÓDULO DE INTERFAZ GRÁFICA (Actividad A3.6)

¿CÓMO TRABAJAR AQUÍ?
1. Implementa el modelo de navegación de la sección 6.1 del documento de diseño:
   Inicio → Esperando imagen/video → Cargar Imagen/Video → Procesamiento → Resultado.
   Los métodos `adjuntar`, `iniciar_procesamiento`, `guardar`, `repetir` y `salir`
   corresponden 1 a 1 a los eventos (Q)/(W)/(E)/(R)/(Esc) de la sección 6.2.1.
2. NO reimplementa la visión por computador: reutiliza `main_test.py` como librería
   (`evaluate_instances`, `build_row`, `annotate`) para no duplicar lógica ya probada
   por la línea de comandos.
3. El procesamiento de video corre en un hilo aparte (`_procesar_video`) para no
   congelar la ventana; cada cuadro actualiza la imagen y los paneles mediante
   `self.after(0, ...)`, que es la forma segura de tocar widgets de Tkinter desde
   otro hilo.
4. Requiere Pillow (`pip install pillow`) para mostrar cuadros de OpenCV en Tkinter.
   El dashboard (`interfaz/dashboard.py`) requiere además matplotlib.

Ejecuta con (desde la carpeta que contiene main_test.py):
    python -m interfaz.app
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

import main_test2 as pipeline  # reutiliza evaluate_instances / build_row / annotate
from funciones.acq import SourceState, VideoSource
from funciones.calib import Calibrator
from funciones.madurez import ColorMaturityClassifier
from funciones.manchas import DarkSpotDetector
from funciones.registro import SessionRegistry
from funciones.seg import ClassicSegmenter
from funciones.tracking.track_kalman import KalmanCentroidTracker

MADUREZ_A_BARRA = {"Verde": 15, "En transición": 50, "Maduro": 90, "No evaluable": 0}
MANCHAS_A_BARRA = {"Sin manchas": 90, "Con manchas": 20, "No evaluable": 0}
CALIBRE_MAX_REFERENCIA_MM = 90  # solo para escalar la barra 0-100, no es un límite de clasificación


class AgroVisionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AgroVision")
        self.geometry("900x560")
        self.minsize(760, 480)

        self.segmenter = ClassicSegmenter()
        self.tracker = KalmanCentroidTracker()
        self.calibrator = Calibrator()
        self.maturity = ColorMaturityClassifier()
        self.spots = DarkSpotDetector()
        self.registry = SessionRegistry()

        self.media_path = None
        self.is_video = False
        self.video_thread = None
        self.video_stop = threading.Event()
        self.last_annotated_bgr = None
        self.state = "ESPERANDO"  # ESPERANDO | PROCESANDO | RESULTADO

        self._build_ui()
        self._bind_keys()
        self._set_status("Esperando imagen/video")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)
        self.canvas_label = ttk.Label(
            left,
            text="Área correspondiente a la imagen/video\ndel fruto que será procesado",
            anchor="center", relief="solid", background="#f2f2f2", justify="center",
        )
        self.canvas_label.pack(fill="both", expand=True)

        right = ttk.Frame(main, width=260)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        ttk.Button(right, text="Dashboards (D)", command=self.abrir_dashboard).pack(fill="x", pady=(0, 10))

        self.bar_madurez = self._build_bar(right, "MADUREZ VISUAL")
        self.bar_calibre = self._build_bar(right, "CALIBRE APARENTE")
        self.bar_calidad = self._build_bar(right, "CALIDAD VISUAL")

        self.lbl_fruto = ttk.Label(right, text="Fruto detectado: —")
        self.lbl_fruto.pack(fill="x", pady=(10, 0))
        self.lbl_estado = ttk.Label(right, text="Estado: Esperando imagen/video", wraplength=240)
        self.lbl_estado.pack(fill="x", pady=(4, 0))

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="(Q) Adjuntar Imagen/Video", command=self.adjuntar).pack(
            side="left", expand=True, fill="x", padx=2)
        ttk.Button(bottom, text="(W) Iniciar procesamiento", command=self.iniciar_procesamiento).pack(
            side="left", expand=True, fill="x", padx=2)
        ttk.Button(bottom, text="(E) Guardar", command=self.guardar).pack(
            side="left", expand=True, fill="x", padx=2)
        ttk.Button(bottom, text="(R) Repetir", command=self.repetir).pack(
            side="left", expand=True, fill="x", padx=2)
        ttk.Button(bottom, text="(Esc) Salir", command=self.salir).pack(
            side="left", expand=True, fill="x", padx=2)

    def _build_bar(self, parent, title):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text=title, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        bar = ttk.Progressbar(frame, maximum=100, value=0)
        bar.pack(fill="x", pady=(2, 0))
        sub = ttk.Frame(frame)
        sub.pack(fill="x")
        ttk.Label(sub, text="Menor").pack(side="left")
        ttk.Label(sub, text="Mayor").pack(side="right")
        return bar

    def _bind_keys(self):
        for key in ("q", "Q"):
            self.bind(key, lambda e: self.adjuntar())
        for key in ("w", "W"):
            self.bind(key, lambda e: self.iniciar_procesamiento())
        for key in ("e", "E"):
            self.bind(key, lambda e: self.guardar())
        for key in ("r", "R"):
            self.bind(key, lambda e: self.repetir())
        for key in ("d", "D"):
            self.bind(key, lambda e: self.abrir_dashboard())
        self.bind("<Escape>", lambda e: self.salir())

    # ------------------------------------------------------------- Eventos
    def adjuntar(self):
        """(Q) Adjuntar Imagen/Video — sección 6.2.1."""
        path = filedialog.askopenfilename(
            title="Adjuntar Imagen/Video",
            filetypes=[("Imagen o video", "*.png *.jpg *.jpeg *.bmp *.mp4 *.avi *.mov"), ("Todos", "*.*")],
        )
        if not path:
            return
        self.media_path = Path(path)
        self.is_video = self.media_path.suffix.lower() in {".mp4", ".avi", ".mov"}
        self.state = "ESPERANDO"
        self._set_status(f"Archivo listo: {self.media_path.name}")

    def iniciar_procesamiento(self):
        """(W) Iniciar procesamiento — carga una nueva vista, procesa y borra el
        resultado anterior (sección 6.2.1)."""
        if self.media_path is None:
            messagebox.showwarning("AgroVision", "Primero adjunta una imagen o video (Q).")
            return
        self.tracker.reset()
        self.state = "PROCESANDO"
        self._set_status("Procesando…")

        if self.is_video:
            self._procesar_video_async()
        else:
            self._procesar_imagen()

    def _procesar_imagen(self):
        frame = cv2.imread(str(self.media_path))
        if frame is None:
            # "Un error de lectura vuelve a Esperando imagen" (sección 6.1)
            self.state = "ESPERANDO"
            self._set_status("Error de lectura: vuelve a Esperando imagen/video.")
            return
        try:
            self._procesar_frame(frame, frame_idx=1)
        except Exception as exc:  # noqa: BLE001
            # "Un error de procesamiento muestra No evaluable" (sección 6.1)
            self._set_status(f"No evaluable ({exc})")
        self.state = "RESULTADO"

    def _procesar_video_async(self):
        self.video_stop.clear()
        self.video_thread = threading.Thread(target=self._procesar_video, daemon=True)
        self.video_thread.start()

    def _procesar_video(self):
        source = VideoSource(source=str(self.media_path), session_id="GUI_SESION")
        try:
            while not self.video_stop.is_set():
                state, meta, frame = source.read_frame()
                if meta["suspend_observations"]:
                    self.tracker.reset()
                    if state == SourceState.EOF and meta["frame_idx"] > 0:
                        break
                    self.after(0, lambda s=state: self._set_status(f"Fuente interrumpida: {s.value}"))
                    break
                try:
                    self._procesar_frame(frame, meta["frame_idx"])
                except Exception as exc:  # noqa: BLE001
                    self.after(0, lambda e=exc: self._set_status(f"No evaluable ({e})"))
        finally:
            source.release()
            self.state = "RESULTADO"
            self.after(0, lambda: self._set_status("Procesamiento de video finalizado."))

    def _procesar_frame(self, frame, frame_idx):
        raw_mask, clean_mask, instances = self.segmenter.process_with_masks(frame)
        tracked = self.tracker.update(instances)
        results = pipeline.evaluate_instances(frame, tracked, self.calibrator, self.maturity, self.spots)

        for obj, result in zip(tracked, results):
            if result["calibre"]["ancho_mm"] is None:
                continue  # RF9: fuera de la zona de medición, no se consolida
            row = pipeline.build_row("GUI_SESION", frame_idx, 0.0, obj, result, self.calibrator)
            self.registry.register_if_new(obj["id"], row)

        annotated = pipeline.annotate(frame, tracked, results)
        self.last_annotated_bgr = annotated
        self.after(0, lambda: self._mostrar_frame(annotated))
        if results:
            self.after(0, lambda: self._actualizar_paneles(results[0]))

    # -------------------------------------------------------------- Render
    def _mostrar_frame(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        w = self.canvas_label.winfo_width() or 560
        h = self.canvas_label.winfo_height() or 420
        img.thumbnail((max(w, 100), max(h, 100)))
        photo = ImageTk.PhotoImage(img)
        self.canvas_label.configure(image=photo, text="")
        self.canvas_label.image = photo  # evita que el garbage collector la borre

    def _actualizar_paneles(self, result):
        mad = result["madurez"]
        man = result["manchas"]
        cal = result["calibre"]

        self.bar_madurez["value"] = MADUREZ_A_BARRA.get(mad["label"], 0)
        self.bar_calidad["value"] = MANCHAS_A_BARRA.get(man["label"], 0)
        calibre_valor = 0
        if cal["ancho_mm"] is not None:
            calibre_valor = min(100, int(cal["ancho_mm"] / CALIBRE_MAX_REFERENCIA_MM * 100))
        self.bar_calibre["value"] = calibre_valor

        self.lbl_fruto.configure(text="Fruto detectado: Tomate")
        self._set_status(f'Madurez: {mad["label"]} | Calibre: {cal["estado"]} | Manchas: {man["label"]}')

    def _set_status(self, texto):
        self.lbl_estado.configure(text=f"Estado: {texto}")

    # ------------------------------------------------------------- Acciones
    def guardar(self):
        """(E) Guardar — confirma antes de exportar (sección 6.2.1)."""
        if not self.registry.rows:
            messagebox.showinfo("AgroVision", "No hay resultados confirmados para guardar todavía.")
            return
        if not messagebox.askyesno(
                "AgroVision", f"¿Guardar {len(self.registry.rows)} registro(s) en CSV y la vista anotada?"):
            return
        salida = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="registro.csv")
        if not salida:
            return
        ok, msg = self.registry.export_csv(salida)
        if ok and self.last_annotated_bgr is not None:
            cv2.imwrite(str(Path(salida).with_suffix(".png")), self.last_annotated_bgr)
        messagebox.showinfo("AgroVision", msg if ok else f"Incidencia: {msg}")

    def repetir(self):
        """(R) Repetir — vuelve al estado inicial de captura; conserva los registros
        ya confirmados (RF7), solo limpia la vista actual."""
        self.video_stop.set()
        self.media_path = None
        self.is_video = False
        self.tracker.reset()
        self.canvas_label.configure(
            image="", text="Área correspondiente a la imagen/video\ndel fruto que será procesado")
        self.canvas_label.image = None
        for bar in (self.bar_madurez, self.bar_calibre, self.bar_calidad):
            bar["value"] = 0
        self.lbl_fruto.configure(text="Fruto detectado: —")
        self.state = "ESPERANDO"
        self._set_status("Esperando imagen/video")

    def abrir_dashboard(self):
        """(D) Apertura de Dashboards — sección 6.2.2."""
        from interfaz.dashboard import mostrar_dashboard
        mostrar_dashboard(self, self.registry.rows)

    def salir(self):
        """(Esc) Salir — libera recursos y cierra (sección 6.2.1/RF: R7 Cierre)."""
        self.video_stop.set()
        self.destroy()


def main():
    app = AgroVisionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
