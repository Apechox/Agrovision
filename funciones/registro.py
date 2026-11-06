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
from datetime import datetime
from pathlib import Path

PROVISIONAL = "Provisional"
CONFIRMADO = "Confirmado"

# clave interna -> encabezado legible (formato "excel")
ENCABEZADOS_EXCEL = {
    "session_id": "Sesión", "fuente": "Fuente", "id": "ID", "frame_idx": "Cuadro",
    "timestamp": "Hora", "tipo": "Tipo",
    "ancho_mm": "Ancho (mm)", "calibre_categoria": "Calibre",
    "calibre_estado": "Estado del calibre", "calibre_causa": "Observación calibre",
    "peso_g": "Peso (g)", "peso_estado": "Estado del peso",
    "madurez_label": "Madurez", "c_ratio": "C (transición)", "r_ratio": "R (rojo)",
    "madurez_causa": "Observación madurez",
    "manchas_label": "Manchas", "defect_ratio": "Área de manchas (proporción)",
    "manchas_causa": "Observación manchas",
    "px_per_mm": "px por mm", "calibracion_validada": "Calibración validada",
    "altura_corregida": "Corrección de altura", "perfil_version": "Versión del perfil",
    "peso_modelo_version": "Versión modelo de peso",
    "estado_registro": "Estado del registro",
}


def _hora(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts and ts > 1e9 else f"{ts} s"


def _excel(clave, valor):
    if clave == "timestamp" and valor != "":
        return _hora(valor)
    return str(valor).replace(".", ",") if isinstance(valor, float) else valor


class SessionRegistry:
    def __init__(self, gap_confirmacion=10):
        self.filas = {}          # {id: fila}
        self._dist = {}          # {id: distancia al centro de la observación guardada}
        self._ultimo_visto = {}  # {id: frame_idx}
        self.incidencias = []    # (hora, origen, causa)
        self.gap_confirmacion = gap_confirmacion

    # ---------- captura ----------
    def observe(self, obj_id, fila, dist_centro, frame_idx):
        """Ofrece una observación válida y en zona. Guarda la más cercana al centro."""
        self._ultimo_visto[obj_id] = frame_idx
        actual = self.filas.get(obj_id)
        if actual is not None and actual["estado_registro"] != PROVISIONAL:
            return False  # el paso ya se consolidó: no se duplica
        if actual is not None and self._dist[obj_id] <= dist_centro:
            return False
        fila = dict(fila)
        fila["estado_registro"] = PROVISIONAL
        self.filas[obj_id] = fila
        self._dist[obj_id] = dist_centro
        return True

    def tick(self, frame_idx):
        """Confirma los IDs que llevan más de `gap_confirmacion` cuadros sin verse."""
        for i, fila in self.filas.items():
            if (fila["estado_registro"] == PROVISIONAL
                    and frame_idx - self._ultimo_visto.get(i, frame_idx) > self.gap_confirmacion):
                fila["estado_registro"] = CONFIRMADO

    def close(self, motivo=CONFIRMADO):
        """Cierra lo pendiente con un estado explícito (fin de video, interrupción, etc.)."""
        for fila in self.filas.values():
            if fila["estado_registro"] == PROVISIONAL:
                fila["estado_registro"] = motivo
                self.incidencia("registro", f"Fila ID {fila['id']} cerrada: {motivo}")

    def incidencia(self, origen, causa):
        self.incidencias.append((datetime.now().strftime("%H:%M:%S"), origen, causa))

    # ---------- exportación ----------
    def export_csv(self, ruta, formato="excel"):
        """formato='excel': ';', coma decimal, encabezados legibles (Excel en español).
        formato='datos': ',', punto decimal, nombres técnicos."""
        ruta = Path(ruta)
        filas = [f for _, f in sorted(self.filas.items())]
        if not filas:
            return False, "No hay registros para exportar"
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
                claves = list(ENCABEZADOS_EXCEL) if formato == "excel" else list(filas[0].keys())
                if formato == "excel":
                    w = csv.DictWriter(f, fieldnames=list(ENCABEZADOS_EXCEL.values()), delimiter=";")
                    w.writeheader()
                    for fila in filas:
                        w.writerow({ENCABEZADOS_EXCEL[k]: _excel(k, fila.get(k, "")) for k in claves})
                else:
                    w = csv.DictWriter(f, fieldnames=claves, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(filas)
        except OSError as exc:
            self.incidencia("exportación", f"No se pudo escribir {ruta}: {exc}")
            return False, f"No se pudo escribir {ruta}: {exc}"
        return True, f"{len(filas)} registro(s) guardados en {ruta}"
