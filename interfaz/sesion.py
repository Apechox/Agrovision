"""
REGISTRO DE SESIÓN DE LA INTERFAZ (RF7 / RF8)

Mantiene UNA fila por ID de tracking (no una por fotograma) y la lista de incidencias.
Es un registro provisional del lado de la interfaz: cuando `funciones/registro.py` (M6)
se integre al repo, esta clase debe reemplazarse por esa.

Reglas:
- Se elige como observación del paso la más cercana al centro de la zona de medición.
- Un dato ausente queda vacío, nunca en cero.
- El guardado solo se confirma tras una escritura exitosa.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

PROVISIONAL = "Provisional"
CONFIRMADO = "Confirmado"


INCIDENCIA_AUSENTES = "madurez y manchas vacías: módulos A3.1/A3.2 no integrados"

# Dos CSV de salida, pensados para lectores distintos:
# - operador: lo que se lee en Excel en español (separador ";", coma decimal, columnas cortas).
#   Solo trae registros definitivos, porque no incluye la columna de estado del registro.
# - técnico: todas las filas y toda la configuración desglosada en columnas, para procesarlo con
#   código (separador ",", punto decimal, nombres de columna técnicos).
CAMPOS_OPERADOR = ["Sesión", "Hora", "Fuente", "ID", "Cuadro", "Tipo", "Ancho (px)", "Ancho (mm)",
                   "Peso (g)", "Calibre", "Madurez", "Manchas"]
CAMPOS_TECNICO = ["sesion", "fuente", "id", "cuadro", "instante", "tipo", "ancho_px", "ancho_mm", "peso_g",
                  "calibre", "estado_calibre", "madurez", "manchas", "estado_registro",
                  "px_per_mm", "calibracion_validada", "distancia_camara_cm", "roi_x", "roi_y", "roi_w", "roi_h",
                  "hsv_h_min", "hsv_s_min", "hsv_v_min", "hsv_h_max", "hsv_s_max", "hsv_v_max", "incidencia"]
ALIAS_FORMATO = {"excel": "operador", "operador": "operador", "datos": "tecnico", "tecnico": "tecnico"}


def _coma(valor):
    return str(valor).replace(".", ",") if isinstance(valor, float) else valor


def _tipo_base(tipo):
    """"Tomate (asumido, sin modelo de tipo)" -> "Tomate"."""
    return str(tipo).split(" (")[0].strip()


def _fila_operador(fila):
    instante = fila["instante"]
    hora = (datetime.fromtimestamp(instante).strftime("%H:%M:%S") if instante > 1e9
            else f"{instante:.2f} s")
    return {
        "Sesión": fila["sesion"], "Hora": hora, "Fuente": fila["fuente"], "ID": fila["id"],
        "Cuadro": fila["cuadro"], "Tipo": _tipo_base(fila["tipo"]),
        "Ancho (px)": fila["ancho_px"], "Ancho (mm)": _coma(fila["ancho_mm"]),
        "Peso (g)": _coma(fila.get("peso_g", "")),
        "Calibre": fila["calibre"], "Madurez": fila["madurez"], "Manchas": fila["manchas"],
    }


def _fila_tecnico(fila):
    """Fila para procesar con código: la configuración vigente va desglosada en columnas."""
    version = fila["version_calibracion"]
    px_mm = re.search(r"px_per_mm=([\d.]+)", version)
    validada = re.search(r"validada=(\w+)", version)
    roi = re.search(r"roi=\[(\d+), (\d+), (\d+), (\d+)\]", version)
    hsv = re.search(r"hsv=\[(\d+), (\d+), (\d+)\]-\[(\d+), (\d+), (\d+)\]", version)
    dist = re.search(r"dist_cm=([\d.]+)", version)
    cfg = {"px_per_mm": px_mm.group(1) if px_mm else "", "distancia_camara_cm": dist.group(1) if dist else "",
           "calibracion_validada": {"sí": "true", "si": "true", "no": "false"}.get(validada.group(1), "") if validada else ""}
    for k, v in zip(("roi_x", "roi_y", "roi_w", "roi_h"), roi.groups() if roi else [""] * 4):
        cfg[k] = v
    for k, v in zip(("hsv_h_min", "hsv_s_min", "hsv_v_min", "hsv_h_max", "hsv_s_max", "hsv_v_max"),
                    hsv.groups() if hsv else [""] * 6):
        cfg[k] = v
    return {**{k: fila.get(k, "") for k in CAMPOS_TECNICO if k not in cfg}, **cfg}


def exportar_sesiones(sesiones, ruta, formato="operador"):
    """Escribe en un solo CSV las filas de varias sesiones (una por archivo de la cola).
    formato='operador' (o 'excel') o formato='tecnico' (o 'datos'); ver los comentarios de arriba."""
    formato = ALIAS_FORMATO.get(formato, "operador")
    ruta = Path(ruta)
    filas = [f for s in sesiones for _, f in sorted(s.filas.items())]
    if formato == "operador":
        filas = [f for f in filas if f["estado_registro"] != PROVISIONAL]  # sin columna de estado: solo definitivos
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            if formato == "operador":
                escritor = csv.DictWriter(f, fieldnames=CAMPOS_OPERADOR, delimiter=";")
                escritor.writeheader()
                for fila in filas:
                    escritor.writerow(_fila_operador(fila))
            else:
                escritor = csv.DictWriter(f, fieldnames=CAMPOS_TECNICO)
                escritor.writeheader()
                for fila in filas:
                    escritor.writerow(_fila_tecnico(fila))
    except OSError as exc:
        return False, f"No se pudo escribir {ruta}: {exc}"
    for s in sesiones:
        s.version_guardada = s.version
    return True, f"{len(filas)} registro(s) guardados en {ruta}"



class SesionRegistro:
    def __init__(self, id_sesion, fuente, version_calibracion):
        self.id_sesion = id_sesion
        self.fuente = fuente
        self.version_calibracion = version_calibracion
        self.filas = {}
        self.incidencias = []  # (hora, origen, causa)
        self.version = 0
        self.version_guardada = 0
        self._unicas = set()

    @property
    def sin_guardar(self):
        return bool(self.filas) and self.version != self.version_guardada

    def incidencia(self, origen, causa, unica=False):
        clave = (origen, causa)
        if unica and clave in self._unicas:
            return
        self._unicas.add(clave)
        self.incidencias.append((datetime.now().strftime("%H:%M:%S"), origen, causa))

    def observar(self, obs, cuadro, instante):
        if obs.id is None or not obs.valida or not obs.en_zona:
            return
        actual = self.filas.get(obs.id)
        if actual and actual["estado_registro"] != PROVISIONAL:
            return
        if actual and actual["_dist"] <= obs.dist_centro:
            return
        self.filas[obs.id] = {
            "sesion": self.id_sesion, "fuente": self.fuente, "id": obs.id, "cuadro": cuadro,
            "instante": round(instante, 3), "tipo": "Tomate (asumido, sin modelo de tipo)",
            "ancho_px": obs.ancho_px,
            "ancho_mm": "" if obs.ancho_mm is None else obs.ancho_mm,
            "peso_g": "",  # A3.4 (estimación de peso) aún no está integrada: vacío, nunca cero
            "calibre": obs.calibre, "estado_calibre": obs.estado_calibre,
            "madurez": "", "manchas": "",
            "estado_registro": PROVISIONAL, "version_calibracion": self.version_calibracion,
            "incidencia": INCIDENCIA_AUSENTES, "_dist": obs.dist_centro,
        }
        self.version += 1

    def confirmar_ausentes(self, ids_activos):
        """Un ID que ya no está activo terminó su paso: su fila pasa a Confirmado."""
        for fila in self.filas.values():
            if fila["estado_registro"] == PROVISIONAL and fila["id"] not in ids_activos:
                fila["estado_registro"] = CONFIRMADO
                self.version += 1

    def cerrar(self, motivo):
        """Cierra lo pendiente con un estado explícito (fin de sesión, fuente interrumpida)."""
        for fila in self.filas.values():
            if fila["estado_registro"] == PROVISIONAL:
                fila["estado_registro"] = motivo
                self.version += 1

    def filas_definitivas(self):
        return [f for f in self.filas.values() if f["estado_registro"] != PROVISIONAL]

    def exportar_csv(self, ruta, formato="excel"):
        return exportar_sesiones([self], ruta, formato)
