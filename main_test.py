import cv2
from src.acquisition import VideoSource, SourceState
from src.segmentation import ClassicSegmenter
from src.tracking import CentroidTracker
from src.calibration import Calibrator

def main():
    # 1. Inicializar módulos de cada integrante
    # Cambiar source=0 por "data/videos/piloto.mp4" cuando Tomás suba el video
    source = VideoSource(source=0, session_id="SESION_PILOTO_01")
    segmenter = ClassicSegmenter()
    tracker = CentroidTracker()
    calibrator = Calibrator(config_path="config/calibration.json")

    print("=== Iniciando Pipeline AgroVision (OE2) ===")
    print("Presiona 'q' en la ventana de video para salir.")

    while True:
        # PASO 1: Adquisición (Cristóbal y Fernando)
        state, meta, frame = source.read_frame()

        # Regla T2.2.2 (Fernando): Si se pierde la señal o termina el video, suspender
        if meta["suspend_observations"]:
            print(f"[AVISO] Observaciones suspendidas. Estado de fuente: {state.value}")
            if state == SourceState.SIGNAL_LOST:
                tracker.reset()  # Regla T2.4.2 (Valentina): Reiniciar IDs sin transferir
            break

        # PASO 2: Segmentación (Cristóbal y Victoria)
        mask, raw_instances = segmenter.process(frame)

        # PASO 3: Seguimiento / Tracking (Cristóbal y Valentina)
        tracked_objects = tracker.update(raw_instances, meta["suspend_observations"])

        # PASO 4: Calibración y Visualización preliminar (Tomás y Fernando)
        vis_frame = frame.copy()
        
        # Dibujar zona válida de medición definida por Tomás
        rx, ry, rw, rh = calibrator.valid_roi
        cv2.rectangle(vis_frame, (rx, ry), (rx + rw, ry + rh), (255, 255, 0), 1)

        for obj in tracked_objects:
            x, y, w, h = obj["bbox"]
            cx, cy = obj["centroid"]
            obj_id = obj["id"]

            # Calcular calibre en milímetros (Tomás)
            calibre_mm = calibrator.pixels_to_mm(w)

            # Dibujar caja, centroide y datos en pantalla
            cv2.rectangle(vis_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(vis_frame, (cx, cy), 4, (0, 0, 255), -1)
            
            label = f"ID:{obj_id} | {calibre_mm:.1f}mm"
            cv2.putText(vis_frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Mostrar ventanas
        cv2.imshow("AgroVision - Vista Principal", vis_frame)
        cv2.imshow("AgroVision - Mascara Binaria", mask)

        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    source.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
