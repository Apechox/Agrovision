import argparse
import hashlib
import json
from pathlib import Path

import cv2

from funciones.acq import SourceState, VideoSource
from funciones.seg import ClassicSegmenter
from funciones.tracking.track import CentroidTracker


def preview(frame, segmenter, tracker, stats=None):
    raw_mask, clean_mask, instances = segmenter.process_with_masks(frame)
    annotated = frame.copy()
    tracked = tracker.update(instances)
    if stats is not None:
        stats["cuadros"] += 1
        stats["detecciones"] += len(instances)
        stats["detecciones_borde"] += sum(not obj["is_valid_mask"] for obj in instances)
        stats["observaciones_seguidas"] += len(tracked)
        stats["max_simultaneos"] = max(stats["max_simultaneos"], len(tracked))
        stats["ids"].update(obj["id"] for obj in tracked)
    for obj in tracked:
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 255, 0), 2)
        cv2.circle(annotated, obj["centroid"], 4, (0, 255, 0), -1)
        cv2.putText(annotated, f'ID {obj["id"]}', (x, max(18, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    if any(e["code"] == "ASSOCIATION_AMBIGUOUS" for e in getattr(tracker, "last_events", [])):
        cv2.putText(annotated, "Asociacion ambigua: observaciones suspendidas", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

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
    parser.add_argument("--tracker", choices=("centroide", "kalman"), default="centroide")
    parser.add_argument("--sin-ventanas", action="store_true", help="Procesa video sin interfaz.")
    parser.add_argument("--salida-video", type=Path, help="Video MP4 con detecciones y máscaras.")
    parser.add_argument("--resumen", type=Path, help="Resumen técnico JSON de la ejecución.")
    parser.add_argument("--max-distance", type=float, default=80.0, help="Distancia máxima en píxeles.")
    parser.add_argument("--max-disappeared", type=int, default=10, help="Actualizaciones ausentes toleradas.")
    parser.add_argument("--ambiguity-margin", type=float, default=2.0,
                        help="Margen de coste total en píxeles para alternativas ambiguas (Kalman).")
    parser.add_argument("--hsv-min", type=int, nargs=3, default=(0, 70, 50))
    parser.add_argument("--hsv-max", type=int, nargs=3, default=(179, 255, 255))
    args = parser.parse_args()
    if args.foto and args.video:
        parser.error("Indica una foto o un video.")
    if args.salida_foto and not args.foto:
        parser.error("--salida-foto requiere --foto.")
    if args.foto and (args.salida_video or args.resumen or args.sin_ventanas):
        parser.error("Las opciones de ejecución de video requieren una fuente de video.")
    if args.sin_ventanas and not args.video:
        parser.error("--sin-ventanas requiere un archivo de video.")
    if args.salida_video and args.video and args.salida_video.resolve() == Path(args.video).resolve():
        parser.error("El video de salida debe ser distinto del archivo de entrada.")
    for low, high, limit in zip(args.hsv_min, args.hsv_max, (179, 255, 255)):
        if not 0 <= low <= high <= limit:
            parser.error("Cada límite HSV debe cumplir 0 <= mínimo <= máximo <= límite del canal.")

    segmenter = ClassicSegmenter(hsv_lower=args.hsv_min, hsv_upper=args.hsv_max)
    if args.tracker == "kalman":
        from funciones.tracking.track_kalman import KalmanCentroidTracker
        tracker = KalmanCentroidTracker(max_distance=args.max_distance,
                                       max_disappeared=args.max_disappeared,
                                       ambiguity_margin=args.ambiguity_margin)
    else:
        tracker = CentroidTracker(max_distance=args.max_distance,
                                  max_disappeared=args.max_disappeared)
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
    writer = None
    stats = {"cuadros": 0, "detecciones": 0, "detecciones_borde": 0,
             "observaciones_seguidas": 0, "max_simultaneos": 0, "ids": set()}
    ending = "DETENIDO_POR_USUARIO"
    try:
        while True:
            state, meta, frame = source.read_frame()
            if meta["suspend_observations"]:
                tracker.reset()
                if state == SourceState.EOF and meta["frame_idx"] > 0:
                    ending = state.value
                    break
                parser.exit(1, f"Fuente sin cuadros disponibles: {state.value}\n")

            views = preview(frame, segmenter, tracker, stats)
            for event in getattr(tracker, "last_events", []):
                if event["severity"] == "warning":
                    print(json.dumps({"session_id": meta["session_id"],
                                      "frame_idx": meta["frame_idx"], **event}))
            if args.salida_video:
                panel = cv2.hconcat([
                    views["Detecciones"],
                    cv2.cvtColor(views["Mascara HSV"], cv2.COLOR_GRAY2BGR),
                    cv2.cvtColor(views["Mascara limpia"], cv2.COLOR_GRAY2BGR),
                ])
                if writer is None:
                    args.salida_video.parent.mkdir(parents=True, exist_ok=True)
                    fps = source.cap.get(cv2.CAP_PROP_FPS)
                    if not 0 < fps < 1000:
                        fps = 30
                    writer = cv2.VideoWriter(str(args.salida_video),
                                             cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                             (panel.shape[1], panel.shape[0]))
                    if not writer.isOpened():
                        parser.exit(1, f"No se pudo abrir la salida {args.salida_video}\n")
                writer.write(panel)
            if not args.sin_ventanas:
                for name, view in views.items():
                    cv2.imshow(name, view)
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    break
    finally:
        source.release()
        if writer is not None:
            writer.release()
        if not args.sin_ventanas:
            cv2.destroyAllWindows()

    if args.resumen:
        stats["ids"] = sorted(stats["ids"])
        stats["ids_asignados"] = len(stats["ids"])
        stats["fuente"] = args.video if args.video else "camara:0"
        if args.video:
            with open(args.video, "rb") as input_file:
                stats["sha256"] = hashlib.file_digest(input_file, "sha256").hexdigest()
        stats["tracker"] = args.tracker
        stats["hsv_min"] = args.hsv_min
        stats["hsv_max"] = args.hsv_max
        stats["estado_final"] = ending
        stats["opencv"] = cv2.__version__
        args.resumen.parent.mkdir(parents=True, exist_ok=True)
        args.resumen.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")



if __name__ == "__main__":
    main()
