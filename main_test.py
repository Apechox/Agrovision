import argparse
import math
import time
import unicodedata
from pathlib import Path

import cv2
import numpy as np

from funciones.acq import SourceState, VideoSource
from funciones.calib import Calibrator
from funciones.calibre import CalibreEvaluator
from funciones.madurez import ColorMaturityClassifier
from funciones.manchas import DarkSpotDetector
from funciones.perfiles import Perfil, PerfilInvalido
from funciones.peso import PesoEvaluator
from funciones.registro import SessionRegistry
from funciones.seg import ClassicSegmenter
from funciones.track import CentroidTracker
from funciones.track_kalman import KalmanCentroidTracker


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
    """Construye la máscara binaria (0/255) de UN solo tomate a partir de su contorno,
    para que madurez.py y manchas.py evalúen solo los píxeles de ese fruto."""
    mask = np.zeros(shape_hw, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    return mask


def _no_evaluable(causa):
    return {"label": "No evaluable", "c_ratio": None, "r_ratio": None, "g_ratio": None,
            "defect_ratio": None, "regiones": [], "causa": causa}


def evaluate_instances(frame, tracked, ev):
    """Calcula calibre, peso, madurez y manchas por tomate seguido (RF3, RF4, RF5) y
    devuelve la lista de resultados en el mismo orden que `tracked`."""
    h, w = frame.shape[:2]
    scale = getattr(ev.calibrator, "scale_px_per_mm", None)
    results = []
    for obj in tracked:
        mask = instance_mask((h, w), obj["contour"])
        calibre = ev.calibre.evaluate(obj, ev.calibrator)

        # La madurez y las manchas no dependen de la calibración, pero sí de una máscara válida
        if obj.get("is_valid_mask") is False:
            mad, man = _no_evaluable("Máscara recortada o ambigua"), _no_evaluable("Máscara recortada o ambigua")
        else:
            mad = ev.maturity.process(frame, mask)
            man = ev.spots.process(frame, mask)

        area_mm2 = (cv2.countNonZero(mask) / (scale ** 2)) if scale else None
        peso = ev.peso.evaluate(calibre, area_mm2)
        results.append({"calibre": calibre, "peso": peso, "madurez": mad, "manchas": man})
    return results


def _v(x):
    """Dato ausente => vacío (nunca cero), RF7."""
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
    """cv2.putText no dibuja tildes ni ñ: se muestran sin diacríticos en pantalla."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _texto(img, linea, x, y, color=(0, 255, 0)):
    """Dibuja una línea de texto sin salirse por el borde derecho del cuadro."""
    linea = _ascii(linea)
    (tw, _), _ = cv2.getTextSize(linea, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    x = max(2, min(x, img.shape[1] - tw - 2))
    cv2.putText(img, linea, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def annotate(frame, tracked, results, modo="interfaz"):
    """modo='interfaz' (por defecto) -> solo el ID; el detalle lo muestra la interfaz.
    modo='prueba' -> toda la información del tomate sobre el video (para desarrollo)."""
    annotated = frame.copy()
    for obj, result in zip(tracked, results):
        x, y, _, _ = obj["bbox"]
        cv2.drawContours(annotated, [obj["contour"]], -1, (0, 255, 0), 2)
        cv2.circle(annotated, obj["centroid"], 4, (0, 255, 0), -1)

        if modo == "interfaz":
            _texto(annotated, f'ID {obj["id"]}', x, max(16, y - 8))
            continue

        if result["manchas"]["regiones"]:  # RF5: mostrar las regiones detectadas
            cv2.drawContours(annotated, result["manchas"]["regiones"], -1, (0, 255, 255), 2)

        cal, pes = result["calibre"], result["peso"]
        mad, man = result["madurez"], result["manchas"]
        if cal["ancho_mm"] is not None:
            ancho = f'{cal["ancho_mm"]} mm' + ("" if cal["calibracion_validada"] else " (prov.)")
            ancho += f' [{cal["categoria"]}]' if cal["categoria"] else f' [{cal["estado"]}]'
        else:
            ancho = cal["estado"]
        peso = f'{pes["peso_g"]} g' if pes["peso_g"] is not None else pes["estado"]
        madurez = mad["label"]
        if mad["r_ratio"] is not None:
            madurez += f' (R {mad["r_ratio"]:.2f}  C {mad["c_ratio"]:.2f})'
        manchas = man["label"]
        if man["defect_ratio"] is not None:
            manchas += f' ({man["defect_ratio"] * 100:.1f}%, {man["n_regiones"]} reg.)'
        lines = [f'ID {obj["id"]}  {ancho}', f'Peso: {peso}',
                 f'Madurez: {madurez}', f'Manchas: {manchas}']
        causas = [c for c in (cal["causa"], pes["causa"], mad.get("causa"), man.get("causa")) if c]
        if causas:
            lines.append("Obs: " + causas[0])
        # Bloque anclado a un mínimo fijo y apilado hacia abajo, sin salirse del cuadro
        top = max(16, y - 8 - 16 * len(lines))
        for k, line in enumerate(lines):
            _texto(annotated, line, x, top + 16 * k)
    return annotated


def _dist_centro(obj, calibrator):
    """Distancia del centroide al centro de la zona de medición (criterio de RF9/5.3)."""
    rx, ry, rw, rh = calibrator.valid_roi
    cx, cy = obj["centroid"]
    return math.hypot(cx - (rx + rw / 2), cy - (ry + rh / 2))


def preview(frame, segmenter, tracker, ev, registry, session_id, frame_idx, timestamp,
            modo="interfaz"):
    raw_mask, clean_mask, instances = segmenter.process_with_masks(frame)
    tracked = tracker.update(instances)
    results = evaluate_instances(frame, tracked, ev)

    if registry is not None:
        for obj, result in zip(tracked, results):
            if not result["calibre"]["en_zona_medicion"]:
                continue  # fuera de zona de medición: no se consolida todavía (RF9)
            row = build_row(session_id, frame_idx, timestamp, obj, result, ev)
            registry.observe(obj["id"], row, _dist_centro(obj, ev.calibrator), frame_idx)
        registry.tick(frame_idx)  # confirma los IDs que ya salieron de la zona

    annotated = annotate(frame, tracked, results, modo)

    # Tomate cortado por el borde del cuadro: solo cambia el color del contorno (naranja),
    # sin texto, en cualquier modo.
    for obj in instances:
        if not obj["is_valid_mask"]:
            cv2.drawContours(annotated, [obj["contour"]], -1, (0, 165, 255), 2)

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
    parser.add_argument("--formato-csv", choices=("excel", "datos"), default="excel",
                        help="excel = ';' y coma decimal con encabezados legibles; "
                             "datos = ',' y punto decimal con nombres técnicos.")
    parser.add_argument("--sesion", default="SESION_01", help="Identificador de sesión para el CSV (RF9).")
    parser.add_argument("--modo", choices=("prueba", "interfaz"), default="interfaz",
                        help="interfaz (por defecto) = solo el ID sobre el video; "
                             "prueba = toda la información del tomate (para desarrollo).")
    parser.add_argument("--perfil", default="tomate",
                        help="Perfil de producto en config/perfiles/<tipo>.json (RF10).")
    parser.add_argument("--altura-camara-mm", type=float, default=None,
                        help="Altura de la cámara sobre la cinta; activa la corrección por altura "
                             "del producto (A2.5). Sin este dato no se corrige.")
    parser.add_argument("--calib-validada", action="store_true",
                        help="Declara que px_per_mm fue validado con patrón y pie de metro. "
                             "Sin este flag el calibre se entrega como 'Provisional'.")
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
        parser.exit(1, f"Perfil no válido: {e}\n")  # RF10: configuración incompatible no se habilita
    if args.altura_camara_mm is not None:
        perfil.datos.setdefault("calibre", {})["altura_camara_mm"] = args.altura_camara_mm

    segmenter = ClassicSegmenter(hsv_lower=args.hsv_min, hsv_upper=args.hsv_max)
    tracker = KalmanCentroidTracker() if args.tracker == "kalman" else CentroidTracker()
    calibrator = Calibrator()
    if args.calib_validada:
        calibrator.validated = True
    fuente = str(args.foto or args.video or "camara_0")
    ev = Evaluadores(perfil, calibrator, fuente)
    registry = SessionRegistry() if args.salida_csv else None

    def export_if_requested(motivo):
        if not args.salida_csv:
            return
        registry.close(motivo)  # lo pendiente se cierra con un estado explícito
        ok, msg = registry.export_csv(str(args.salida_csv), args.formato_csv)
        print(("[OK] " if ok else "[INCIDENCIA] ") + msg)

    if args.foto:
        frame = cv2.imread(str(args.foto))
        if frame is None:
            parser.exit(1, f"No se pudo leer la foto {args.foto}\n")
        views = preview(frame, segmenter, tracker, ev, registry, args.sesion, 1, time.time(),
                         args.modo)
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

            views = preview(frame, segmenter, tracker, ev, registry,
                            args.sesion, meta["frame_idx"], meta["timestamp"], args.modo)
            for name, view in views.items():
                cv2.imshow(name, view)
            if cv2.waitKey(30) & 0xFF == ord("q"):
                break
    finally:
        source.release()
        cv2.destroyAllWindows()
        export_if_requested(motivo)

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