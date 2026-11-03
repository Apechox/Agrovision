import argparse
from pathlib import Path

import cv2

from funciones.acq import SourceState, VideoSource
from funciones.seg import ClassicSegmenter
from funciones.track import CentroidTracker


def preview(frame, segmenter, tracker):
    raw_mask, clean_mask, instances = segmenter.process_with_masks(frame)
    annotated = frame.copy()
    for obj in tracker.update(instances):
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 255, 0), 2)
        cv2.circle(annotated, obj["centroid"], 4, (0, 255, 0), -1)
        cv2.putText(annotated, f'ID {obj["id"]}', (x, max(18, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

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

    segmenter = ClassicSegmenter(hsv_lower=args.hsv_min, hsv_upper=args.hsv_max)
    tracker = CentroidTracker()
    if args.foto:
        frame = cv2.imread(str(args.foto))
        if frame is None:
            parser.exit(1, f"No se pudo leer la foto {args.foto}\n")
        views = preview(frame, segmenter, tracker)
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
        return

    source = VideoSource(source=args.video if args.video else 0)
    try:
        while True:
            state, meta, frame = source.read_frame()
            if meta["suspend_observations"]:
                tracker.reset()
                if state == SourceState.EOF and meta["frame_idx"] > 0:
                    break
                parser.exit(1, f"Fuente sin cuadros disponibles: {state.value}\n")

            for name, view in preview(frame, segmenter, tracker).items():
                cv2.imshow(name, view)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
