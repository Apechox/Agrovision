"""Estimación de peso (A3.4, OE3).

Modelo potencial  peso_g = a * x^b  con x = ancho_mm (o área proyectada en mm²),
ajustado por mínimos cuadrados en escala logarítmica con datos de balanza por ejemplar.

El modelo se guarda en JSON (con n, R², RMSE por validación cruzada leave-one-out)
para que cada resultado sea trazable a una versión del ajuste (RNF3).
"""
import csv
import json
from pathlib import Path

import numpy as np

from funciones.caracteristicas.perfiles import NO_APLICA, NO_EVALUABLE, FUERA_DE_RANGO, RAIZ

MIN_EJEMPLARES = 8


class PesoModelo:
    def __init__(self, datos=None):
        self.datos = datos

    # ---------- ajuste ----------
    @staticmethod
    def _ajustar(x, y):
        b, ln_a = np.polyfit(np.log(x), np.log(y), 1)
        return float(np.exp(ln_a)), float(b)

    @classmethod
    def ajustar(cls, x, y, variable="ancho_mm", tipo="tomate", version=None):
        x, y = np.asarray(x, float), np.asarray(y, float)
        ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        x, y = x[ok], y[ok]
        if len(x) < MIN_EJEMPLARES:
            raise ValueError(f"Se requieren al menos {MIN_EJEMPLARES} ejemplares válidos "
                             f"(hay {len(x)})")
        a, b = cls._ajustar(x, y)
        pred = a * x ** b
        ss_res = float(((y - pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        # Leave-one-out: error esperado sobre ejemplares no vistos
        err = []
        for i in range(len(x)):
            m = np.arange(len(x)) != i
            ai, bi = cls._ajustar(x[m], y[m])
            err.append(y[i] - ai * x[i] ** bi)
        rmse_loo = float(np.sqrt(np.mean(np.square(err))))

        datos = {"tipo": tipo, "variable": variable, "a": a, "b": b, "n": int(len(x)),
                 "x_min": float(x.min()), "x_max": float(x.max()),
                 "r2": round(r2, 4), "rmse_loo_g": round(rmse_loo, 2),
                 "version": version or f"peso-{tipo}-n{len(x)}"}
        return cls(datos)

    def guardar(self, ruta):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(self.datos, f, indent=2, ensure_ascii=False)

    @classmethod
    def cargar(cls, ruta):
        ruta = Path(ruta)
        if not ruta.is_absolute():
            ruta = RAIZ / ruta
        if not ruta.exists():
            return cls(None)
        with open(ruta, encoding="utf-8") as f:
            return cls(json.load(f))

    @classmethod
    def desde_csv(cls, ruta_csv, variable="ancho_mm", tipo="tomate"):
        """CSV con columnas: ejemplar_id, ancho_mm (o area_mm2), peso_g."""
        xs, ys = [], []
        with open(ruta_csv, newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                try:
                    xs.append(float(fila[variable]))
                    ys.append(float(fila["peso_g"]))
                except (KeyError, ValueError):
                    continue
        return cls.ajustar(xs, ys, variable=variable, tipo=tipo)

    # ---------- predicción ----------
    @property
    def disponible(self):
        return self.datos is not None

    @property
    def version(self):
        return self.datos["version"] if self.datos else None

    def predecir(self, x):
        d = self.datos
        if d is None:
            return None
        return round(d["a"] * float(x) ** d["b"], 1)


class PesoEvaluator:
    def __init__(self, perfil, modelo=None):
        self.perfil = perfil
        ruta = perfil.seccion("peso").get("modelo")
        self.modelo = modelo if modelo is not None else PesoModelo.cargar(ruta) if ruta \
            else PesoModelo(None)

    @staticmethod
    def _res(estado, causa=None, peso=None, version=None):
        return {"peso_g": peso, "estado": estado, "causa": causa, "modelo_version": version}

    def evaluate(self, calibre, area_mm2=None):
        if not self.perfil.aplica("peso"):
            return self._res(NO_APLICA, "El perfil no define peso")
        if not self.modelo.disponible:
            return self._res(NO_EVALUABLE, "Sin modelo ajustado (faltan datos de balanza)")
        if calibre.get("ancho_mm") is None or calibre["estado"] in (NO_EVALUABLE, FUERA_DE_RANGO, NO_APLICA):
            return self._res(NO_EVALUABLE, "Sin calibre válido", version=self.modelo.version)

        var = self.modelo.datos["variable"]
        x = calibre["ancho_mm"] if var == "ancho_mm" else area_mm2
        if x is None:
            return self._res(NO_EVALUABLE, f"Falta {var}", version=self.modelo.version)

        d = self.modelo.datos
        if not d["x_min"] * 0.9 <= x <= d["x_max"] * 1.1:
            return self._res("Fuera de rango", f"{var}={x} fuera del rango de ajuste "
                             f"[{d['x_min']:.1f}, {d['x_max']:.1f}]", version=self.modelo.version)
        return self._res("Estimado", None, self.modelo.predecir(x), self.modelo.version)
