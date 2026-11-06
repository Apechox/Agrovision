"""Demostración reproducible del tracker actual con detecciones inventadas.

Desde la raíz: python -B -m examples.demo_tracking
Los nombres A/B y las trayectorias de este guion son evidencia de prueba;
no son información que reciba o produzca automáticamente el tracker.
"""
import argparse
import json
from pathlib import Path

from funciones.tracking.track import CentroidTracker


def run_scenario(name, frames, *, max_distance=30, max_disappeared=2):
    tracker = CentroidTracker(max_distance=max_distance, max_disappeared=max_disappeared)
    records = []
    histories = {}
    print(f"\n{name}")
    for frame_idx, fruits in enumerate(frames, start=1):
        # A/B are ground-truth labels for the reader. Do not send them to tracker.
        detections = [{"centroid": (x, y), "is_valid_mask": True}
                      for _, x, y in fruits]
        observed = tracker.update(detections)
        associations = []
        for (label, _, _), result in zip(fruits, observed):
            row = {"reference_fruit": label, "id": result["id"],
                   "centroid": result["centroid"]}
            associations.append(row)
            histories.setdefault(result["id"], []).append(
                {"frame_idx": frame_idx, "centroid": result["centroid"]})
        records.append({"frame_idx": frame_idx, "observations": associations,
                        "retained_ids": sorted(tracker.objects)})
        text = ", ".join(f"{r['reference_fruit']}:{r['centroid']} -> ID {r['id']}"
                         for r in associations) or "sin detecciones; sin observaciones nuevas"
        print(f"  cuadro {frame_idx}: {text}; IDs retenidos={sorted(tracker.objects)}")
    return {"scenario": name, "parameters": {"max_distance": max_distance,
            "max_disappeared": max_disappeared}, "frames": records,
            "histories_collected_by_demo": histories}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Guardar evidencia sintética en JSON")
    args = parser.parse_args()
    scenarios = [
        run_scenario("Movimiento y desaparicion breve", [
            [("A", 100, 100), ("B", 200, 100)],
            [("B", 210, 100), ("A", 110, 100)],
            [("B", 220, 100)],
            [("A", 130, 100), ("B", 230, 100)],
        ]),
        run_scenario("Perdida prolongada: no se recupera la identidad", [
            [("A", 100, 100)], [], [], [], [("A", 110, 100)],
        ]),
        run_scenario("Limitacion conocida: orden A, B", [
            [("A", 100, 100), ("B", 110, 100)],
            [("A", 106, 100), ("B", 111, 100)],
        ], max_distance=8),
        run_scenario("Misma escena: orden B, A", [
            [("A", 100, 100), ("B", 110, 100)],
            [("B", 111, 100), ("A", 106, 100)],
        ], max_distance=8),
    ]
    print("\nLa demo acumula posiciones observadas; el tracker aun no devuelve historiales ni incidencias.")
    print("Los IDs retenidos pueden estar temporalmente perdidos; no equivalen a frutos visibles.")
    print("Los parametros son didacticos, no estan calibrados con una cinta real.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"synthetic_only": True, "scenarios": scenarios},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Evidencia guardada en: {args.output}")


if __name__ == "__main__":
    main()
