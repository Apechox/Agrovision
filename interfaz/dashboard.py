"""
DASHBOARD (sección 6.2.2): tres gráficos de torta sobre los registros definitivos.

- Solo cuenta filas NO provisionales (los provisionales no entran a agregados finales).
- Madurez y Calidad muestran "Sin datos" mientras A3.1/A3.2 no estén integradas.
- El selector de fruto tiene solo "Tomate" porque es el único catálogo habilitado.
"""

import tkinter as tk
from collections import Counter
from tkinter import messagebox, ttk


def contar(filas, campo):
    """Cuenta valores no vacíos de un campo; un dato ausente no se grafica como categoría."""
    return Counter(f[campo] for f in filas if f.get(campo))


def _torta(ax, conteo, titulo):
    ax.set_title(titulo)
    if not conteo:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center")
        ax.axis("off")
        return
    etiquetas = list(conteo)
    ax.pie([conteo[k] for k in etiquetas],
           labels=[f"{k} ({conteo[k]})" for k in etiquetas],
           autopct=lambda p: f"{p:.0f}%", startangle=90)


def mostrar_dashboard(parent, sesion):
    try:
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
    except ImportError:
        messagebox.showerror("AgroVision", "Falta matplotlib: pip install matplotlib")
        return

    definitivas = sesion.filas_definitivas() if sesion else []
    provisionales = (len(sesion.filas) - len(definitivas)) if sesion else 0

    win = tk.Toplevel(parent)
    win.title("AgroVision — Dashboard de análisis")
    win.geometry("900x440")

    top = ttk.Frame(win, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Fruto:").pack(side="left")
    combo = ttk.Combobox(top, values=["Tomate"], state="readonly", width=12)
    combo.set("Tomate")
    combo.pack(side="left", padx=(4, 0))
    ttk.Label(top, text=f"Registros definitivos: {len(definitivas)} "
                        f"(provisionales excluidos: {provisionales})").pack(side="right")

    fig = Figure(figsize=(9, 3.8))
    ax1, ax2, ax3 = fig.subplots(1, 3)
    _torta(ax1, contar(definitivas, "madurez"), "Madurez Visual")
    _torta(ax2, contar(definitivas, "manchas"), "Calidad Visual")
    _torta(ax3, contar(definitivas, "calibre"), "Calibre Aparente")
    fig.tight_layout()

    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
