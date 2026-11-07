"""Perfiles por tipo de producto (RF10, RNF7).

Un perfil define atributos aplicables, unidades, categorías y umbrales. Los criterios
del tomate NO se trasladan a otros productos: cada tipo tiene su propio JSON.
"""
import json
import os
from pathlib import Path


def _buscar_raiz():
    candidatas = []
    if os.environ.get("AGROVISION_RAIZ"):
        candidatas.append(Path(os.environ["AGROVISION_RAIZ"]))
    aqui = Path(__file__).resolve()
    candidatas += list(aqui.parents)
    cwd = Path.cwd().resolve()
    candidatas += [cwd, *cwd.parents]
    for c in candidatas:
        if (c / "config" / "perfiles").is_dir():
            return c
    return aqui.parent.parent  # último recurso: el comportamiento anterior


RAIZ = _buscar_raiz()
PERFILES_DIR = RAIZ / "config" / "perfiles"

NO_APLICA = "No aplica"
NO_EVALUABLE = "No evaluable"
FUERA_DE_RANGO = "Fuera de rango"


class PerfilInvalido(ValueError):
    pass


class Perfil:
    def __init__(self, datos):
        for clave in ("tipo", "version", "atributos"):
            if clave not in datos:
                raise PerfilInvalido(f"Perfil sin '{clave}'")
        self.datos = datos
        self.tipo = datos["tipo"]
        self.version = datos["version"]
        self._validar_calibre()

    def _validar_calibre(self):
        cal = self.datos.get("calibre")
        if not cal:
            return
        lo, hi = cal["rango_validado_mm"]
        if not lo < hi:
            raise PerfilInvalido("rango_validado_mm debe cumplir min < max")
        cats = cal["categorias"]
        for c in cats:
            if not c["min_mm"] < c["max_mm"]:
                raise PerfilInvalido(f"Categoría '{c['nombre']}': min_mm debe ser < max_mm")
        for a, b in zip(cats, cats[1:]):
            if a["max_mm"] != b["min_mm"]:
                raise PerfilInvalido(
                    f"Categorías '{a['nombre']}' y '{b['nombre']}' no son contiguas")

    def aplica(self, atributo):
        return bool(self.datos["atributos"].get(atributo, False))

    def seccion(self, nombre):
        return self.datos.get(nombre, {})

    @classmethod
    def cargar(cls, tipo="tomate", directorio=PERFILES_DIR):
        ruta = Path(directorio) / f"{tipo}.json"
        if not ruta.exists():
            raise PerfilInvalido(f"No existe el perfil '{tipo}' en {directorio}")
        with open(ruta, encoding="utf-8") as f:
            return cls(json.load(f))