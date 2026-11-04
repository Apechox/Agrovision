"""
MÓDULO DE DASHBOARD (Actividad A3.6, prototipo de la sección 6.2.2)

¿CÓMO TRABAJAR AQUÍ?
1. `mostrar_dashboard(parent, rows)` recibe `self.registry.rows` de `interfaz/app.py`
   (las mismas filas que se exportan a CSV) y arma 3 gráficos de torta: Madurez
   Visual, Calidad Visual (manchas) y Calibre Aparente, igual al prototipo de la
   sección 6.2.2 del documento de diseño.
2. El selector "Fruto" está fijo en "Tomate" porque el catálogo habilitado hoy solo
   tiene tomate (sección 2 del documento). Cuando se agregue una segunda especie
   (A4.2), cambia `combo = ttk.Combobox(..., values=["Tomate"])` por la lista real
   y filtra `rows` por el campo de tipo antes de graficar.
3. Los límites de calibre (Pequeño/Mediano/Grande) usados aquí para el gráfico son
   solo para visualización; los límites "oficiales" por perfil se definen en A3.3
   y deben sincronizarse acá cuando estén versionados.

Requiere matplotlib (`pip install matplotlib`).
"""

import tkinter as tk
from collections import Counter
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


def contar_por_campo(rows, campo):
    """Cuenta ocurrencias de un campo (p. ej. 'madurez_label') entre las filas del registro."""
    return Counter(r[campo] for r in rows)


def contar_calibre(rows, limites_mm=((55, "Pequeño"), (70, "Mediano"))):
    """Clasifica cada fila con ancho_mm numérico en Pequeño/Mediano/Grande para el gráfico.
    `limites_mm` son los cortes superiores de Pequeño y Mediano; todo lo demás es Grande."""
    counts = Counter()
    (limite_pequeno, _), (limite_mediano, _) = limites_mm
    for r in rows:
        ancho = r.get("ancho_mm")
        if not isinstance(ancho, (int, float)):
            continue
        if ancho < limite_pequeno:
            counts["Pequeño"] += 1
        elif ancho < limite_mediano:
            counts["Mediano"] += 1
        else:
            counts["Grande"] += 1
    return counts


def _dibujar_torta(ax, counts, titulo):
    if not counts:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center")
        ax.set_title(titulo)
        ax.axis("off")
        return
    labels = list(counts.keys())
    values = [counts[k] for k in labels]
    ax.pie(values, labels=labels, autopct=lambda p: f"{p:.0f}%", startangle=90)
    ax.set_title(titulo)


def mostrar_dashboard(parent, rows):
    win = tk.Toplevel(parent)
    win.title("AgroVision — Dashboard de análisis")
    win.geometry("820x420")

    top = ttk.Frame(win, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Fruto:").pack(side="left")
    combo = ttk.Combobox(top, values=["Tomate"], state="readonly", width=12)
    combo.set("Tomate")
    combo.pack(side="left", padx=(4, 0))
    ttk.Label(top, text=f"Total de frutos analizados: {len(rows)}").pack(side="right")

    fig = Figure(figsize=(8, 3.6))
    ax1, ax2, ax3 = fig.subplots(1, 3)
    _dibujar_torta(ax1, contar_por_campo(rows, "madurez_label"), "Madurez Visual")
    _dibujar_torta(ax2, contar_por_campo(rows, "manchas_label"), "Calidad Visual")
    _dibujar_torta(ax3, contar_calibre(rows), "Calibre Aparente")
    fig.tight_layout()

    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
