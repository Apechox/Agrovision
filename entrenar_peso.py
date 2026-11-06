"""Ajusta el modelo de peso (A3.4) a partir de datos de balanza.

CSV de entrada (una fila por ejemplar):  ejemplar_id, ancho_mm, peso_g
  ancho_mm = medido con la MISMA definición de dimensión del perfil (idealmente por
  el propio sistema o con pie de metro, según protocolo A1.3).

Uso:
    python entrenar_peso.py datos/balanza_tomate.csv
"""
import argparse
from pathlib import Path

from funciones.peso import PesoModelo

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--variable", choices=("ancho_mm", "area_mm2"), default="ancho_mm")
    ap.add_argument("--tipo", default="tomate")
    ap.add_argument("--salida", type=Path, default=None,
                    help="Por defecto config/peso_modelo_<tipo>.json")
    args = ap.parse_args()
    modelo = PesoModelo.desde_csv(args.csv, args.variable, args.tipo)
    salida = args.salida or Path("config") / f"peso_modelo_{args.tipo}.json"
    modelo.guardar(salida)
    d = modelo.datos
    print(f"[OK] {salida}  n={d['n']}  peso = {d['a']:.5f} * {d['variable']}^{d['b']:.3f}")
    print(f"     R²={d['r2']}  RMSE (leave-one-out)={d['rmse_loo_g']} g")

if __name__ == "__main__":
    main()
