import argparse
import hashlib
import json
import math
import time
import unicodedata
from pathlib import Path

import cv2
import numpy as np

from funciones.acq import SourceState, VideoSource
from funciones.caracteristicas.calib import Calibrator
from funciones.caracteristicas.calibre import CalibreEvaluator
from funciones.caracteristicas.madurez import ColorMaturityClassifier
from funciones.caracteristicas.manchas import DarkSpotDetector
from funciones.caracteristicas.perfiles import Perfil, PerfilInvalido
from funciones.caracteristicas.peso import PesoEvaluator
from funciones.registro import SessionRegistry
from funciones.seg import ClassicSegmenter
from funciones.tracking.track import CentroidTracker


class Evaluadores:
    """Agrupa el perfil y los evaluadores por atributo (M4 + M5 + peso)."""

    def __init__(self, perfil, calibrator, fuente):
        self.perfil = perfil
        self.calibrator = calibrator
        self.fuente = fuente
        self.calibre = CalibreEvaluator(perfil)
        self.peso = PesoEvaluator(perfil)
        self.maturity = ColorMaturityClassifier(perfil)
        self.spots = DarkSpotDetector(perfil)


def instance_mask(shape_hw, contour):
    """Construye la máscara binaria (0/255) de un solo tomate a partir de su contorno."""
    mask = np.zeros(shape_hw, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    return mask


def _no_evaluable(causa):
    return {
        "label": "No evaluable",
        "c_ratio": None,
        "r_ratio": None,
        "g_ratio": None,
        "defect_ratio": None,
        "regiones": [],
        "causa": causa,
    }


def evaluate_instances(frame, tracked, ev):
    """Calcula calibre, peso, madurez y manchas por tomate seguido."""
    h, w = frame.shape[:2]
    scale = getattr(ev.calibrator, "scale_px_per_mm", None)
    results = []
    for obj in tracked:
        mask = instance_mask((h, w), obj["contour"])
        calibre = ev.calibre.evaluate(obj, ev.calibrator)

        if obj.get("is_valid_mask") is False:
            mad = _no_evaluable("Máscara recortada o ambigua")
            man = _no_evaluable("Máscara recortada o ambigua")
        else:
            mad = ev.maturity.process(frame, mask)
            man = ev.spots.process(frame, mask)

        area_mm2 = (cv2.countNonZero(mask) / (scale**2)) if scale else None
        peso = ev.peso.evaluate(calibre, area_mm2)
        results.append({"calibre": calibre, "peso": peso, "madurez": mad, "manchas": man})
    return results


def _v(x):
    """Dato ausente => cadena vacía."""
    return "" if x is None else x


def build_row(session_id, frame_idx, timestamp, obj, result, ev):
    mad, man, cal, pes = result["madurez"], result["manchas"], result["calibre"], result["peso"]
    return {
        "session_id": session_id,
        "fuente": ev.fuente,
        "frame_idx": frame_idx,
        "id": obj["id"],
        "timestamp": round(timestamp, 3),
        "tipo": ev.perfil.tipo,
        "ancho_mm": _v(cal["ancho_mm"]),
        "calibre_categoria": _v(cal["categoria"]),
        "calibre_estado": cal["estado"],
        "calibre_causa": _v(cal["causa"]),
        "peso_g": _v(pes["peso_g"]),
        "peso_estado": pes["estado"],
        "madurez_label": mad["label"],
        "c_ratio": _v(mad["c_ratio"]),
        "r_ratio": _v(mad["r_ratio"]),
        "madurez_causa": _v(mad.get("causa")),
        "manchas_label": man["label"],
        "defect_ratio": _v(man["defect_ratio"]),
        "manchas_causa": _v(man.get("causa")),
        "px_per_mm": _v(ev.calibrator.scale_px_per_mm),
        "calibracion_validada": cal["calibracion_validada"],
        "altura_corregida": cal["altura_corregida"],
        "perfil_version": ev.perfil.version,
        "peso_modelo_version": _v(pes["modelo_version"]),
    }


def _ascii(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _texto(img, linea, x, y, color=(0, 255, 0)):
    linea = _ascii(linea)
    (tw, _), _ = cv2.getTextSize(linea, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    x = max(2, min(x, img.shape[1] - tw - 2))
    cv2.putText(img, linea, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def annotate(frame, tracked, results, modo="interfaz"):
    """modo='interfaz' -> solo el ID.
    modo='prueba' -> métricas limpias sobre el video (estilo original).
    """
    annotated = frame.copy()
    for obj, result in zip(tracked, results):
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 255, 0), 2)
        cv2.circle(annotated, obj["centroid"], 4, (0, 255, 0), -1)

        if modo == "interfaz":
            _texto(annotated, f'ID {obj["id"]}', x, max(16, y - 8))
            continue

        if result["manchas"]["regiones"]:
            cv2.drawContours(annotated, result["manchas"]["regiones"], -1, (0, 255, 255), 2)

        cal, pes = result["calibre"], result["peso"]
        mad, man = result["madurez"], result["manchas"]

        # Ancho / Calibre
        if cal["ancho_mm"] is not None:
            ancho = f'{cal["ancho_mm"]} mm (prov.)' if not cal["calibracion_validada"] else f'{cal["ancho_mm"]} mm'
            ancho += f' [{cal["categoria"]}]' if cal["categoria"] else f' [{cal["estado"]}]'
        else:
            ancho = cal["estado"]

        # Peso
        peso = f'{pes["peso_g"]} g' if pes["peso_g"] is not None else pes["estado"]

        # Madurez (sin ratios en pantalla)
        madurez = mad["label"]

        # Manchas (con porcentaje solo si hay defecto)
        manchas = man["label"]
        if man["defect_ratio"] is not None and man["defect_ratio"] > 0:
            manchas += f' ({man["defect_ratio"] * 100:.1f}%)'

        lines = [
            f'ID {obj["id"]}  {ancho}',
            f"Peso: {peso}",
            f"Madurez: {madurez}",
            f"Manchas: {manchas}",
        ]

        # Bloque apilado encima del tomate
        top = max(16, y - 8 - 18 * len(lines))
        for k, line in enumerate(lines):
            _texto(annotated, line, x, top + 18 * k)

    return annotated

def _dist_centro(obj, calibrator):
    rx, ry, rw, rh = calibrator.valid_roi
    cx, cy = obj["centroid"]
    return math.hypot(cx - (rx + rw / 2), cy - (ry + rh / 2))


def preview(
    frame,
    segmenter,
    tracker,
    ev,
    registry,
    session_id,
    frame_idx,
    timestamp,
    modo="interfaz",
):
    raw_mask, clean_mask, instances = segmenter.process_with_masks(frame)
    tracked = tracker.update(instances)
    results = evaluate_instances(frame, tracked, ev)

    if registry is not None:
        for obj, result in zip(tracked, results):
            if not result["calibre"]["en_zona_medicion"]:
                continue
            row = build_row(session_id, frame_idx, timestamp, obj, result, ev)
            registry.observe(obj["id"], row, _dist_centro(obj, ev.calibrator), frame_idx)
        registry.tick(frame_idx)

    annotated = annotate(frame, tracked, results, modo)

    if any(e["code"] == "ASSOCIATION_AMBIGUOUS" for e in getattr(tracker, "last_events", [])):
        cv2.putText(
            annotated,
            "Asociacion ambigua: observaciones suspendidas",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 165, 255),
            1,
        )

    for obj in instances:
        if not obj["is_valid_mask"]:
            x, y, _, _ = obj["bbox"]
            cv2.drawContours(annotated, [obj["contour"]], -1, (0, 165, 255), 2)
            cv2.putText(
                annotated,
                "Cortado por borde",
                (x, max(18, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 165, 255),
                2,
            )

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
    parser.add_argument("--salida-csv", type=Path, help="Exporta el registro consolidado por tomate.")
    parser.add_argument(
        "--formato-csv",
        choices=("excel", "datos"),
        default="excel",
        help="excel = ';' y coma decimal; datos = ',' y punto decimal.",
    )
    parser.add_argument("--sesion", default="SESION_01", help="Identificador de sesión para el CSV.")
    parser.add_argument(
        "--modo",
        choices=("prueba", "interfaz"),
        default="interfaz",
        help="interfaz = solo ID; prueba = métricas completas en pantalla.",
    )
    parser.add_argument("--perfil", default="tomate", help="Perfil en config/perfiles/<tipo>.json.")
    parser.add_argument(
        "--altura-camara-mm",
        type=float,
        default=None,
        help="Altura de la cámara sobre la cinta en mm.",
    )
    parser.add_argument(
        "--calib-validada",
        action="store_true",
        help="Indica calibración validada físicamente.",
    )
    parser.add_argument(
        "--tracker",
        choices=("centroide", "kalman"),
        default="centroide",
        help="Algoritmo de seguimiento.",
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=80.0,
        help="Distancia máxima de asociación en píxeles.",
    )
    parser.add_argument(
        "--max-disappeared",
        type=int,
        default=10,
        help="Cuadros consecutivos ausentes tolerados.",
    )
    parser.add_argument(
        "--ambiguity-margin",
        type=float,
        default=2.0,
        help="Margen de coste en píxeles para ambigüedad (Kalman).",
    )
    parser.add_argument("--hsv-min", type=int, nargs=3, default=(0, 70, 50))
    parser.add_argument("--hsv-max", type=int, nargs=3, default=(179, 255, 255))
    parser.add_argument("--resumen", type=Path, help="Ruta para exportar métricas JSON al finalizar.")
    parser.add_argument("--salida-video", type=Path, help="Ruta para guardar el video procesado.")
    parser.add_argument("--sin-ventanas", action="store_true", help="Ejecuta sin abrir ventanas OpenCV.")
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

    try:
        perfil = Perfil.cargar(args.perfil)
    except (PerfilInvalido, KeyError, ValueError) as e:
        parser.exit(1, f"Perfil no válido: {e}\n")

    if args.altura_camara_mm is not None:
        perfil.datos.setdefault("calibre", {})["altura_camara_mm"] = args.altura_camara_mm

    segmenter = ClassicSegmenter(hsv_lower=args.hsv_min, hsv_upper=args.hsv_max)

    if args.tracker == "kalman":
        from funciones.tracking.track_kalman import KalmanCentroidTracker

        tracker = KalmanCentroidTracker(
            max_distance=args.max_distance,
            max_disappeared=args.max_disappeared,
            ambiguity_margin=args.ambiguity_margin,
        )
    else:
        tracker = CentroidTracker(
            max_distance=args.max_distance,
            max_disappeared=args.max_disappeared,
        )

    calibrator = Calibrator()
    if args.calib_validada:
        calibrator.validated = True

    fuente = str(args.foto or args.video or "camara_0")
    ev = Evaluadores(perfil, calibrator, fuente)
    registry = SessionRegistry() if args.salida_csv else None

    def export_if_requested(motivo):
        if not args.salida_csv:
            return
        registry.close(motivo)
        ok, msg = registry.export_csv(str(args.salida_csv), args.formato_csv)
        print(("[OK] " if ok else "[INCIDENCIA] ") + msg)

    if args.foto:
        frame = cv2.imread(str(args.foto))
        if frame is None:
            parser.exit(1, f"No se pudo leer la foto {args.foto}\n")
        views = preview(
            frame,
            segmenter,
            tracker,
            ev,
            registry,
            args.sesion,
            1,
            time.time(),
            args.modo,
        )
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
        export_if_requested("Confirmado")
        return

    source = VideoSource(source=args.video if args.video else 0, session_id=args.sesion)
    motivo = "Cerrado por interrupción del operador"
    tracked_ids = set()
    video_writer = None

    try:
        while True:
            state, meta, frame = source.read_frame()
            if meta["suspend_observations"]:
                tracker.reset()
                if state == SourceState.EOF and meta["frame_idx"] > 0:
                    motivo = "Cerrado por fin de video"
                    break
                motivo = "Cerrado por fuente interrumpida"
                parser.exit(1, f"Fuente sin cuadros disponibles: {state.value}\n")

            views = preview(
                frame,
                segmenter,
                tracker,
                ev,
                registry,
                args.sesion,
                meta["frame_idx"],
                meta["timestamp"],
                args.modo,
            )

            # Acumular IDs observados para el resumen
            for obj in getattr(tracker, "objects", {}).keys():
                tracked_ids.add(obj)

            for event in getattr(tracker, "last_events", []):
                if event.get("severity") == "warning":
                    print(
                        json.dumps(
                            {
                                "session_id": meta["session_id"],
                                "frame_idx": meta["frame_idx"],
                                **event,
                            }
                        )
                    )

            if args.salida_video:
                if video_writer is None:
                    h, w = views["Detecciones"].shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    args.salida_video.parent.mkdir(parents=True, exist_ok=True)
                    video_writer = cv2.VideoWriter(str(args.salida_video), fourcc, 30.0, (w, h))
                video_writer.write(views["Detecciones"])

            if not args.sin_ventanas:
                for name, view in views.items():
                    cv2.imshow(name, view)
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    break
    finally:
        if video_writer is not None:
            video_writer.release()
        source.release()
        cv2.destroyAllWindows()
        export_if_requested(motivo)

    if args.resumen:
        stats = {
            "ids": sorted(list(tracked_ids)),
            "ids_asignados": len(tracked_ids),
            "fuente": args.video if args.video else "camara:0",
            "tracker": args.tracker,
            "hsv_min": args.hsv_min,
            "hsv_max": args.hsv_max,
            "estado_final": motivo,
            "opencv": cv2.__version__,
        }
        if args.video and Path(args.video).is_file():
            with open(args.video, "rb") as input_file:
                stats["sha256"] = hashlib.file_digest(input_file, "sha256").hexdigest()

        args.resumen.parent.mkdir(parents=True, exist_ok=True)
        args.resumen.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()