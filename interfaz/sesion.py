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
from datetime import datetime
from pathlib import Path

PROVISIONAL = "Provisional"
CONFIRMADO = "Confirmado"

CAMPOS = ["sesion", "fuente", "id", "cuadro", "instante", "tipo", "ancho_px", "ancho_mm",
          "calibre", "estado_calibre", "madurez", "manchas", "estado_registro",
          "version_calibracion", "incidencia"]

INCIDENCIA_AUSENTES = "madurez y manchas vacías: módulos A3.1/A3.2 no integrados"


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

    def exportar_csv(self, ruta):
        ruta = Path(ruta)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
                escritor = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
                escritor.writeheader()
                for _, fila in sorted(self.filas.items()):
                    escritor.writerow(fila)
        except OSError as exc:
            return False, f"No se pudo escribir {ruta}: {exc}"
        self.version_guardada = self.version
        return True, f"{len(self.filas)} registro(s) guardados en {ruta}"
