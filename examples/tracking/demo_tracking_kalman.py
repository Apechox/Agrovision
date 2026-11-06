"""Genera un video sintético de segmentación + tracking y evidencia por cuadro.

python -B -m examples.tracking.demo_tracking_kalman --output salida-tracking
No representa tomates reales ni acredita precisión en la cinta transportadora.
"""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path

import cv2
import numpy as np

from funciones.seg import ClassicSegmenter
from funciones.tracking.track import CentroidTracker
from funciones.tracking.track_kalman import KalmanCentroidTracker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('salida-tracking'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    segmenter = ClassicSegmenter()
    tracker = KalmanCentroidTracker(max_distance=8, max_disappeared=2)
    baseline = CentroidTracker(max_distance=8, max_disappeared=2)
    baseline_last_id, baseline_ids, baseline_switches = {}, set(), 0
    histories = defaultdict(lambda: deque(maxlen=60))
    records, lane_ids = [], {}
    video_path = args.output / 'tracking_sintetico.mp4'
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*'mp4v'), 15, (480, 280))
    if not writer.isOpened():
        raise RuntimeError('No se pudo abrir el escritor de video MP4')
    try:
        for frame_idx in range(1, 56):
            frame = np.full((280, 480, 3), 115, dtype=np.uint8)
            # El fruto A no aparece en cuadros 19 y 20. El tracker no recibe la referencia.
            for y in (90, 190):
                if y == 90 and frame_idx in (19, 20):
                    continue
                cv2.circle(frame, (50 + 5 * frame_idx, y), 19, (0, 0, 225), -1)
            _, instances = segmenter.process(frame)
            baseline_points = []
            for detection in baseline.update(instances):
                cx, cy = detection['centroid']
                obj_id = detection['id']
                if cy in baseline_last_id and baseline_last_id[cy] != obj_id:
                    baseline_switches += 1
                baseline_last_id[cy] = obj_id
                baseline_ids.add(obj_id)
                baseline_points.append({'id': obj_id, 'centroid': [cx, cy]})
            observed = tracker.update(instances)
            expected_count = 1 if frame_idx in (19, 20) else 2
            if len(observed) != expected_count:
                raise AssertionError(f'Cantidad inesperada en cuadro {frame_idx}')
            points = []
            for obj in observed:
                cx, cy = obj['centroid']
                lane_ids.setdefault(cy, obj['id'])
                if obj['id'] != lane_ids[cy]:
                    raise AssertionError(f'Cambio de ID en cuadro {frame_idx}, carril {cy}')
                histories[obj['id']].append((cx, cy))
                points.append({'id': obj['id'], 'centroid': [cx, cy]})
                cv2.rectangle(frame, (cx - 22, cy - 22), (cx + 22, cy + 22), (0, 230, 0), 1)
                cv2.putText(frame, f"ID {obj['id']}", (cx - 18, cy - 28),
                            cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
                cv2.polylines(frame, [np.array(histories[obj['id']], dtype=np.int32)],
                              False, (0, 230, 230), 1)
            records.append({'session_id': 'SINTETICA_HITO2', 'frame_idx': frame_idx,
                            'observations': points, 'baseline_observations': baseline_points,
                            'events': tracker.last_events})
            cv2.putText(frame, 'PRUEBA SINTETICA - NO SON FRUTOS REALES', (10, 23),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
            cv2.putText(frame, f'Cuadro {frame_idx}/55 - IDs con perdida breve', (10, 255),
                        cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1)
            writer.write(frame)
    finally:
        writer.release()
    data = {'synthetic_only': True, 'source_frames': 55, 'unique_track_ids': sorted(lane_ids.values()),
            'id_switches_in_this_fixture': 0, 'parameters': {'max_distance': 8, 'max_disappeared': 2,
            'ambiguity_margin': 2}, 'baseline': {'unique_track_ids': sorted(baseline_ids),
            'id_switches_in_this_fixture': baseline_switches}, 'records': records}
    (args.output / 'tracking_sintetico.json').write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'55 cuadros comprobados; 2 IDs conservados; video: {video_path}')
    print(f'Centroides en la misma secuencia: {len(baseline_ids)} IDs; {baseline_switches} cambios.')


if __name__ == '__main__':
    main()
