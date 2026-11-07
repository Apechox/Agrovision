"""M6 · Consolidación y registro por unidad (RF7, A3.5).

Una fila por ID de tracking (no una por fotograma). Mientras el tomate sigue en la
zona de medición la fila es PROVISIONAL y se reemplaza solo si aparece una observación
más cercana al centro de la zona (criterio fijo, desempate temporal: gana la primera).
Cuando el ID deja de verse por más de `gap_confirmacion` cuadros, la fila pasa a
CONFIRMADO. Lo que quede pendiente se cierra con un estado explícito (close).

Reglas: dato ausente = vacío (nunca 0); el guardado solo se confirma tras una
escritura exitosa; un fallo de escritura se informa como incidencia.
Basado en el registro provisional de la interfaz (SesionRegistro).
"""

import csv
import re
from datetime import datetime
from pathlib import Path
 
PROVISIONAL = "Provisional"
CONFIRMADO = "Confirmado"
 
INCIDENCIA_AUSENTES = "madurez y manchas sin dato (no evaluables o no calculadas)"
ESTADOS_SIN_CATEGORIA = ("Fuera de rango", "No evaluable", "No aplica")
 
CAMPOS_OPERADOR = ["Sesión", "Hora", "Fuente", "ID", "Cuadro", "Tipo", "Ancho (px)", "Ancho (mm)",
                   "Peso (g)", "Calibre", "Madurez", "Manchas"]
CAMPOS_TECNICO = ["sesion", "fuente", "id", "cuadro", "instante", "tipo", "ancho_px", "ancho_mm", "peso_g",
                  "calibre", "estado_calibre", "madurez", "manchas", "estado_registro",
                  "px_per_mm", "calibracion_validada", "distancia_camara_cm", "roi_x", "roi_y", "roi_w", "roi_h",
                  "hsv_h_min", "hsv_s_min", "hsv_v_min", "hsv_h_max", "hsv_s_max", "hsv_v_max", "incidencia"]
CAMPOS_EXTRA = ["c_ratio", "r_ratio", "defect_ratio", "peso_estado", "calibre_causa",
                "altura_corregida", "perfil_version", "peso_modelo_version"]
CAMPOS_COMPLETO = CAMPOS_TECNICO + CAMPOS_EXTRA
ALIAS_FORMATO = {"excel": "operador", "operador": "operador", "datos": "tecnico",
                 "tecnico": "tecnico", "completo": "completo"}
 
 
# ---------------------------------------------------------------- utilidades
def describir_calibracion(px_per_mm, validada, roi, hsv_min, hsv_max, dist_cm=None):
    """Texto de configuración vigente, con el formato que el exportador sabe desglosar."""
    partes = [f"px_per_mm={float(px_per_mm):.4f}", f"validada={'sí' if validada else 'no'}",
              "roi=[" + ", ".join(str(int(round(v))) for v in roi) + "]",
              "hsv=[" + ", ".join(str(int(v)) for v in hsv_min) + "]-["
              + ", ".join(str(int(v)) for v in hsv_max) + "]"]
    if dist_cm:
        partes.append(f"dist_cm={float(dist_cm):.1f}")
    return "; ".join(partes)
 
 
def _coma(valor):
    return str(valor).replace(".", ",") if isinstance(valor, float) else valor
 
 
def _tipo_base(tipo):
    """'Tomate (asumido, sin modelo de tipo)' -> 'Tomate'."""
    t = str(tipo).split(" (")[0].strip()
    return t[:1].upper() + t[1:]
 
 
def _vacio(valor):
    return "" if valor is None or valor in ("—", "-") else valor
 
 
def _hora(instante):
    return (datetime.fromtimestamp(instante).strftime("%H:%M:%S") if instante > 1e9
            else f"{instante:.2f} s")
 
 
def _config(fila):
    """Configuración vigente desglosada: se lee del texto de versión y, si la fila trae
    el dato directo (p. ej. desde main_test), ese tiene prioridad."""
    version = fila.get("version_calibracion", "")
    px_mm = re.search(r"px_per_mm=([\d.]+)", version)
    validada = re.search(r"validada=(\w+)", version)
    roi = re.search(r"roi=\[(\d+), (\d+), (\d+), (\d+)\]", version)
    hsv = re.search(r"hsv=\[(\d+), (\d+), (\d+)\]-\[(\d+), (\d+), (\d+)\]", version)
    dist = re.search(r"dist_cm=([\d.]+)", version)
    cfg = {"px_per_mm": px_mm.group(1) if px_mm else "",
           "distancia_camara_cm": dist.group(1) if dist else "",
           "calibracion_validada": ({"sí": "true", "si": "true", "no": "false"}.get(validada.group(1), "")
                                    if validada else "")}
    for k, v in zip(("roi_x", "roi_y", "roi_w", "roi_h"), roi.groups() if roi else [""] * 4):
        cfg[k] = v
    for k, v in zip(("hsv_h_min", "hsv_s_min", "hsv_v_min", "hsv_h_max", "hsv_s_max", "hsv_v_max"),
                    hsv.groups() if hsv else [""] * 6):
        cfg[k] = v
    if fila.get("px_per_mm") not in (None, ""):
        cfg["px_per_mm"] = fila["px_per_mm"]
    if isinstance(fila.get("calibracion_validada"), bool):
        cfg["calibracion_validada"] = "true" if fila["calibracion_validada"] else "false"
    return cfg
 
 
def _fila_operador(fila):
    return {
        "Sesión": fila["sesion"], "Hora": _hora(fila["instante"]), "Fuente": fila["fuente"],
        "ID": fila["id"], "Cuadro": fila["cuadro"], "Tipo": _tipo_base(fila["tipo"]),
        "Ancho (px)": fila["ancho_px"], "Ancho (mm)": _coma(fila["ancho_mm"]),
        "Peso (g)": _coma(fila.get("peso_g", "")),
        "Calibre": fila["calibre"], "Madurez": fila["madurez"], "Manchas": fila["manchas"],
    }
 
 
def _fila_tecnico(fila, campos):
    cfg = _config(fila)
    return {k: cfg[k] if k in cfg else fila.get(k, "") for k in campos}
 
 
def exportar_sesiones(sesiones, ruta, formato="operador"):
    """Escribe en un solo CSV las filas de varias sesiones (una por archivo de la cola).
    formato: 'operador' (o 'excel'), 'tecnico' (o 'datos') o 'completo'."""
    formato = ALIAS_FORMATO.get(formato, "operador")
    ruta = Path(ruta)
    filas = [f for s in sesiones for _, f in sorted(s.filas.items())]
    if not filas:
        return False, "No hay registros para exportar"
    if formato == "operador":
        filas = [f for f in filas if f["estado_registro"] != PROVISIONAL]  # solo definitivos
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            if formato == "operador":
                escritor = csv.DictWriter(f, fieldnames=CAMPOS_OPERADOR, delimiter=";")
                escritor.writeheader()
                for fila in filas:
                    escritor.writerow(_fila_operador(fila))
            else:
                campos = CAMPOS_COMPLETO if formato == "completo" else CAMPOS_TECNICO
                escritor = csv.DictWriter(f, fieldnames=campos)
                escritor.writeheader()
                for fila in filas:
                    escritor.writerow(_fila_tecnico(fila, campos))
    except OSError as exc:
        return False, f"No se pudo escribir {ruta}: {exc}"
    for s in sesiones:
        s.version_guardada = s.version
    return True, f"{len(filas)} registro(s) guardados en {ruta}"
 
 
# ------------------------------------------------------------------- sesión
class SesionRegistro:
    def __init__(self, id_sesion="SESION_01", fuente="", version_calibracion="", gap_confirmacion=0):
        self.id_sesion = id_sesion
        self.fuente = fuente
        self.version_calibracion = version_calibracion
        self.gap_confirmacion = gap_confirmacion  # 0 = confirma en cuanto el ID no está activo
        self.filas = {}
        self.incidencias = []  # (hora, origen, causa)
        self.version = 0
        self.version_guardada = 0
        self._unicas = set()
        self._ausencias = {}      # {id: cuadros consecutivos sin estar activo}
        self._ultimo_cuadro = {}  # {id: último cuadro en que se ofreció una observación}
 
    @property
    def sin_guardar(self):
        return bool(self.filas) and self.version != self.version_guardada
 
    def incidencia(self, origen, causa, unica=False):
        clave = (origen, causa)
        if unica and clave in self._unicas:
            return
        self._unicas.add(clave)
        self.incidencias.append((datetime.now().strftime("%H:%M:%S"), origen, causa))
 
    # ---------- captura: interfaz ----------
    def observar(self, obs, cuadro, instante):
        """Observación de la interfaz (objeto `obs`). Los datos de peso y del análisis
        se leen si el objeto los trae; si no, quedan vacíos (nunca cero)."""
        if obs.id is None or not obs.valida or not obs.en_zona:
            return
        g = lambda nombre: _vacio(getattr(obs, nombre, ""))  # noqa: E731
        calibre = g("calibre")
        madurez, manchas = g("madurez"), g("manchas")
        incidencia = g("incidencia") or (INCIDENCIA_AUSENTES if not madurez and not manchas else "")
        fila = {
            "sesion": self.id_sesion, "fuente": self.fuente, "id": obs.id, "cuadro": cuadro,
            "instante": round(instante, 3), "tipo": g("tipo") or "Tomate",
            "ancho_px": obs.ancho_px, "ancho_mm": _vacio(obs.ancho_mm), "peso_g": g("peso_g"),
            "calibre": calibre, "estado_calibre": g("estado_calibre"),
            "madurez": madurez, "manchas": manchas,
            "version_calibracion": self.version_calibracion, "incidencia": incidencia,
            "c_ratio": g("c_ratio"), "r_ratio": g("r_ratio"), "defect_ratio": g("defect_ratio"),
            "peso_estado": g("peso_estado"), "calibre_causa": g("calibre_causa"),
            "altura_corregida": g("altura_corregida"), "perfil_version": g("perfil_version"),
            "peso_modelo_version": g("peso_modelo_version"),
        }
        self._guardar(obs.id, fila, obs.dist_centro, cuadro)
 
    # ---------- captura: main_test / pipeline ----------
    def observe(self, obj_id, fila, dist_centro, frame_idx):
        """Observación ya armada por `main_test.build_row` (claves del pipeline)."""
        f = fila
        v = lambda k: _vacio(f.get(k, ""))  # noqa: E731
        estado = v("calibre_estado")
        causas = [f"{etq}: {v(k)}" for etq, k in (("Calibre", "calibre_causa"), ("Peso", "peso_causa"),
                                                  ("Madurez", "madurez_causa"), ("Manchas", "manchas_causa"))
                  if v(k)]
        norm = {
            "sesion": f.get("session_id", self.id_sesion), "fuente": f.get("fuente", self.fuente),
            "id": obj_id, "cuadro": frame_idx, "instante": f.get("timestamp", 0),
            "tipo": v("tipo") or "Tomate", "ancho_px": v("ancho_px"), "ancho_mm": v("ancho_mm"),
            "peso_g": v("peso_g"),
            "calibre": v("calibre_categoria") or (estado if estado in ESTADOS_SIN_CATEGORIA else ""),
            "estado_calibre": estado, "madurez": v("madurez_label"), "manchas": v("manchas_label"),
            "version_calibracion": self.version_calibracion,
            "px_per_mm": v("px_per_mm"), "calibracion_validada": f.get("calibracion_validada", ""),
            "incidencia": "; ".join(causas),
            "c_ratio": v("c_ratio"), "r_ratio": v("r_ratio"), "defect_ratio": v("defect_ratio"),
            "peso_estado": v("peso_estado"), "calibre_causa": v("calibre_causa"),
            "altura_corregida": f.get("altura_corregida", ""), "perfil_version": v("perfil_version"),
            "peso_modelo_version": v("peso_modelo_version"),
        }
        return self._guardar(obj_id, norm, dist_centro, frame_idx)
 
    def _guardar(self, obj_id, fila, dist_centro, cuadro):
        self._ultimo_cuadro[obj_id] = cuadro
        actual = self.filas.get(obj_id)
        if actual and actual["estado_registro"] != PROVISIONAL:
            return False  # el paso ya se consolidó: no se duplica
        if actual and actual["_dist"] <= dist_centro:
            return False
        fila = dict(fila)
        fila["estado_registro"] = PROVISIONAL
        fila["_dist"] = dist_centro
        self.filas[obj_id] = fila
        self.version += 1
        return True
 
    # ---------- consolidación ----------
    def confirmar_ausentes(self, ids_activos):
        """Un ID que ya no está activo terminó su paso: su fila pasa a Confirmado
        (tras `gap_confirmacion` cuadros consecutivos sin estar activo)."""
        for fila in self.filas.values():
            if fila["estado_registro"] != PROVISIONAL:
                continue
            i = fila["id"]
            if i in ids_activos:
                self._ausencias[i] = 0
                continue
            self._ausencias[i] = self._ausencias.get(i, 0) + 1
            if self._ausencias[i] > self.gap_confirmacion:
                fila["estado_registro"] = CONFIRMADO
                self.version += 1
 
    def tick(self, frame_idx):
        """main_test: activos = los IDs observados en este cuadro."""
        self.confirmar_ausentes({i for i, c in self._ultimo_cuadro.items() if c == frame_idx})
 
    def cerrar(self, motivo):
        """Cierra lo pendiente con un estado explícito (fin de sesión, fuente interrumpida)."""
        for fila in self.filas.values():
            if fila["estado_registro"] == PROVISIONAL:
                fila["estado_registro"] = motivo
                self.version += 1
 
    close = cerrar
 
    def filas_definitivas(self):
        return [f for f in self.filas.values() if f["estado_registro"] != PROVISIONAL]
 
    # ---------- exportación ----------
    def exportar_csv(self, ruta, formato="excel"):
        return exportar_sesiones([self], ruta, formato)
 
    export_csv = exportar_csv
 
 
class SessionRegistry(SesionRegistro):
    """Nombre que usa main_test.py. Por defecto tolera 10 cuadros sin ver el ID
    antes de confirmar (oclusiones breves)."""
 
    def __init__(self, id_sesion="SESION_01", fuente="", version_calibracion="", gap_confirmacion=10):
        super().__init__(id_sesion, fuente, version_calibracion, gap_confirmacion)
