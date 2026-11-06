import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from funciones.acq import SourceState, VideoSource
from funciones.calib import Calibrator
from funciones.seg import ClassicSegmenter
from funciones.track import CentroidTracker
from funciones.track_kalman import KalmanCentroidTracker


def instance_mask(shape_hw, contour):
    """Construye la máscara binaria (0/255) de UN solo tomate a partir de su contorno,
    para que madurez.py y manchas.py evalúen solo los píxeles de ese fruto."""
    mask = np.zeros(shape_hw, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    return mask


def evaluate_instances(frame, tracked, calibrator, maturity, spots):
    """Calcula calibre, madurez y manchas por tomate seguido (RF3, RF4, RF5) y
    devuelve la lista de resultados en el mismo orden que `tracked`."""
    h, w = frame.shape[:2]
    results = []
    for obj in tracked:
        mask = instance_mask((h, w), obj["contour"])

        inside_zone = calibrator.is_inside_valid_zone(obj["centroid"])
        if not inside_zone:
            calibre = {"ancho_mm": None, "estado": "Fuera de rango"}
        else:
            _, _, bw, _ = obj["bbox"]
            calibre = {
                "ancho_mm": calibrator.pixels_to_mm(bw),
                "estado": "Estimado (calibración pendiente de validar con pie de metro)",
            }

        mad = maturity.process(frame, mask)
        man = spots.process(frame, mask)
        results.append({"calibre": calibre, "madurez": mad, "manchas": man})
    return results


def build_row(session_id, frame_idx, timestamp, obj, result, calibrator):
    mad = result["madurez"]
    man = result["manchas"]
    cal = result["calibre"]
    return {
        "session_id": session_id,
        "frame_idx": frame_idx,
        "id": obj["id"],
        "timestamp": round(timestamp, 3),
        "ancho_mm": cal["ancho_mm"] if cal["ancho_mm"] is not None else "",
        "calibre_estado": cal["estado"],
        "madurez_label": mad["label"],
        "c_ratio": mad["c_ratio"] if mad["c_ratio"] is not None else "",
        "r_ratio": mad["r_ratio"] if mad["r_ratio"] is not None else "",
        "manchas_label": man["label"],
        "defect_ratio": man["defect_ratio"] if man["defect_ratio"] is not None else "",
        "px_per_mm": calibrator.scale_px_per_mm,
    }


def annotate(frame, tracked, results):
    annotated = frame.copy()
    for obj, result in zip(tracked, results):
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 255, 0), 2)
        cv2.circle(annotated, obj["centroid"], 4, (0, 255, 0), -1)

        cal = result["calibre"]
        ancho = f'{cal["ancho_mm"]} mm' if cal["ancho_mm"] is not None else cal["estado"]
        lines = [
            f'ID {obj["id"]}  {ancho}',
            f'Madurez: {result["madurez"]["label"]}',
            f'Manchas: {result["manchas"]["label"]}',
        ]
        # Ancla el bloque de texto a un mínimo fijo y lo apila siempre hacia abajo,
        # para que no se superponga cuando el tomate toca el borde superior del cuadro.
        top = max(16, y - 8 - 16 * len(lines))
        for i, line in enumerate(lines):
            cv2.putText(annotated, line, (x, top + 16 * i),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
    return annotated


def preview(frame, segmenter, tracker, calibrator, maturity, spots, registry,
            session_id, frame_idx, timestamp):
    raw_mask, clean_mask, instances = segmenter.process_with_masks(frame)
    tracked = tracker.update(instances)
    results = evaluate_instances(frame, tracked, calibrator, maturity, spots)

    if registry is not None:
        for obj, result in zip(tracked, results):
            if result["calibre"]["ancho_mm"] is None:
                continue  # fuera de zona de medición: no se consolida todavía (RF9)
            row = build_row(session_id, frame_idx, timestamp, obj, result, calibrator)
            registry.register_if_new(obj["id"], row)

    annotated = annotate(frame, tracked, results)

    for obj in instances:
        if obj["is_valid_mask"]:
            continue
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 165, 255), 2)
        cv2.putText(annotated, "Cortado por borde", (x, max(18, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

    return {
        "Detecciones": annotated,
        "Mascara HSV": raw_mask,
        "Mascara limpia": clean_mask,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="?", help="Ruta al video. Por defecto usa la cámara 0.")
    parser.add_argument("--foto", type=Path)
    parser.add_argument("--salida-foto", type=Path, help="Guarda las tres vistas sin abrir ventanas.")
    parser.add_argument("--salida-csv", type=Path, help="Exporta el registro consolidado por tomate (RF7).")
    parser.add_argument("--sesion", default="SESION_01", help="Identificador de sesión para el CSV (RF9).")
    parser.add_argument("--tracker", choices=("centroide", "kalman"), default="centroide",
                         help="centroide = asociación por distancia a la última posición (track.py). "
                              "kalman = asociación por posición PREDICHA con velocidad constante "
                              "(track_kalman.py, Unidad 7), más robusto a oclusiones breves.")
    parser.add_argument("--hsv-min", type=int, nargs=3, default=(0, 70, 50))
    parser.add_argument("--hsv-max", type=int, nargs=3, default=(179, 255, 255))
    args = parser.parse_args()
    if args.foto and args.video:
        parser.error("Indica una foto o un video.")
    if args.salida_foto and not args.foto:
        parser.error("--salida-foto requiere --foto.")
    for low, high, limit in zip(args.hsv_min, args.hsv_max, (179, 255, 255)):
        if not 0 <= low <= high <= limit:
            parser.error("Cada límite HSV debe cumplir 0 <= mínimo <= máximo <= límite del canal.")

    try:
        from funciones.madurez import ColorMaturityClassifier
        from funciones.manchas import DarkSpotDetector
        from funciones.registro import SessionRegistry
    except ModuleNotFoundError as error:
        parser.exit(1, f"Falta una dependencia del flujo ampliado: {error.name}. "
                    "Consultar docs/pruebas_video_hito2.md.\n")

    segmenter = ClassicSegmenter(hsv_lower=args.hsv_min, hsv_upper=args.hsv_max)
    tracker = KalmanCentroidTracker() if args.tracker == "kalman" else CentroidTracker()
    calibrator = Calibrator()
    maturity = ColorMaturityClassifier()
    spots = DarkSpotDetector()
    registry = SessionRegistry() if args.salida_csv else None

    def export_if_requested():
        if not args.salida_csv:
            return
        ok, msg = registry.export_csv(str(args.salida_csv))
        print(("[OK] " if ok else "[INCIDENCIA] ") + msg)

    if args.foto:
        frame = cv2.imread(str(args.foto))
        if frame is None:
            parser.exit(1, f"No se pudo leer la foto {args.foto}\n")
        views = preview(frame, segmenter, tracker, calibrator, maturity, spots, registry,
                         args.sesion, 1, time.time())
        if args.salida_foto:
            args.salida_foto.mkdir(parents=True, exist_ok=True)
            for name, view in views.items():
                path = args.salida_foto / (name.lower().replace(" ", "_") + ".png")
                if not cv2.imwrite(str(path), view):
                    parser.exit(1, f"No se pudo guardar {path}\n")
        else:
            try:
                for name, view in views.items():
                    cv2.imshow(name, view)
                cv2.waitKey(0)
            finally:
                cv2.destroyAllWindows()
        export_if_requested()
        return

    source = VideoSource(source=args.video if args.video else 0, session_id=args.sesion)
    try:
        while True:
            state, meta, frame = source.read_frame()
            if meta["suspend_observations"]:
                tracker.reset()
                if state == SourceState.EOF and meta["frame_idx"] > 0:
                    break
                parser.exit(1, f"Fuente sin cuadros disponibles: {state.value}\n")

            views = preview(frame, segmenter, tracker, calibrator, maturity, spots, registry,
                             args.sesion, meta["frame_idx"], meta["timestamp"])
            for name, view in views.items():
                cv2.imshow(name, view)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        source.release()
        cv2.destroyAllWindows()
        export_if_requested()


if __name__ == "__main__":
    main()
