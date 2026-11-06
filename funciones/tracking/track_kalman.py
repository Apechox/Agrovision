"""
MÓDULO DE SEGUIMIENTO CON FILTRO DE KALMAN (Actividad A2.4)

¿CÓMO TRABAJAR AQUÍ?
1. `update()` conserva la lista de instancias con `"id"` agregado. Las detecciones
   ambiguas no se emiten ni reciben un ID nuevo; se describen en `last_events`.
2. Cada objeto tiene su propio `cv2.KalmanFilter` con estado [x, y, vx, vy] y medición [x, y].
   Más ruido de proceso permite alejarse del modelo; más ruido de medición reduce
   la confianza en las detecciones. Se ajustan por separado con datos de desarrollo.
3. La asociación usa la posición PREDICHA (`predict()`) de cada Kalman activo, no la última
   medición cruda; esto puede ayudar en pérdidas breves, sin garantizar identidad.
4. La asociación es conjunta, con umbral de distancia y rechazo de alternativas
   similares. Un paso temporal equivale a una llamada válida a update(), no a un segundo.

Devuelve la misma lista de diccionarios que entregó Segmentación, agregando `"id"` (int).
"""

import math

import cv2
import numpy as np

from .association import associate


class _TrackedTomato:
    def __init__(self, obj_id, centroid, process_noise, measurement_noise):
        self.obj_id = obj_id
        self.disappeared = 0
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.transitionMatrix = np.array(
            [[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32
        )
        self.kf.measurementMatrix = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32
        )
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * process_noise
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_noise
        # Incertidumbre inicial no nula para aprender velocidad desde las mediciones.
        # Con P inicial cero, predict() incorpora Q: no corresponde afirmar que la
        # primera ganancia sea necesariamente cero si el ruido de proceso es positivo.
        self.kf.errorCovPost = np.eye(4, dtype=np.float32) * 1.0
        cx, cy = centroid
        self.kf.statePost = np.array([[cx], [cy], [0], [0]], dtype=np.float32)
        self.predicted = (cx, cy)

    def predict(self):
        p = self.kf.predict()
        self.predicted = (float(p[0, 0]), float(p[1, 0]))
        return self.predicted

    def correct(self, centroid):
        cx, cy = centroid
        self.kf.correct(np.array([[np.float32(cx)], [np.float32(cy)]]))


class KalmanCentroidTracker:
    def __init__(self, max_disappeared=10, max_distance=80.0,
                 process_noise=1e-2, measurement_noise=1e-1, ambiguity_margin=2.0):
        if not isinstance(max_disappeared, int) or max_disappeared < 0:
            raise ValueError("max_disappeared debe ser un entero no negativo")
        for name, value in (("max_distance", max_distance), ("ambiguity_margin", ambiguity_margin),
                            ("process_noise", process_noise), ("measurement_noise", measurement_noise)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} debe ser finito y no negativo")
        if measurement_noise == 0:
            raise ValueError("measurement_noise debe ser positivo")
        self.next_object_id = 1
        self.tracked = {}  # {id: _TrackedTomato}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.ambiguity_margin = ambiguity_margin
        self.last_events = []
        self.update_index = 0

    def reset(self, reason="reset"):
        """Limpia asociaciones sin reciclar IDs. El llamador identifica la sesión."""
        self.last_events = []
        if self.tracked:
            self._event("TRACKS_CLOSED", sorted(self.tracked), reason=reason)
        self.tracked.clear()

    def _event(self, code, track_ids, severity="info", **details):
        self.last_events.append({"code": code, "severity": severity,
                                 "update_index": self.update_index,
                                 "track_ids": list(track_ids), **details})

    def _age_unmatched(self, matched):
        for obj_id in list(self.tracked):
            if obj_id in matched:
                continue
            track = self.tracked[obj_id]
            track.disappeared += 1
            if track.disappeared > self.max_disappeared:
                self._event("TRACK_LOST_TIMEOUT", [obj_id], severity="warning")
                self._deregister(obj_id)
            elif track.disappeared == 1:
                self._event("TRACK_TEMPORARILY_LOST", [obj_id])

    def _register(self, centroid):
        obj_id = self.next_object_id
        self.tracked[obj_id] = _TrackedTomato(
            obj_id, centroid, self.process_noise, self.measurement_noise
        )
        self.next_object_id += 1
        return obj_id

    def _deregister(self, obj_id):
        del self.tracked[obj_id]

    def update(self, instances, suspend_observations=False):
        # last_events corresponde solo a esta operación; consumir antes de la siguiente.
        self.last_events = []
        if suspend_observations:
            return []

        valid_indices = [i for i, inst in enumerate(instances) if inst.get("is_valid_mask", True)]
        valid_instances = [instances[i] for i in valid_indices]
        for inst in valid_instances:
            point = inst.get("centroid", ())
            if len(point) != 2 or not all(math.isfinite(float(v)) for v in point):
                raise ValueError("Cada centroide debe contener dos coordenadas finitas")
        self.update_index += 1

        # Predice la posición de cada tomate ya seguido ANTES de asociar (esto es lo que
        # diferencia a este tracker del CentroidTracker simple).
        predictions = {obj_id: t.predict() for obj_id, t in self.tracked.items()}

        if len(valid_instances) == 0:
            self._age_unmatched(set())
            return []

        if len(self.tracked) == 0:
            tracked_outputs = []
            for inst in valid_instances:
                new_id = self._register(inst["centroid"])
                inst_copy = inst.copy()
                inst_copy["id"] = new_id
                tracked_outputs.append(inst_copy)
            return tracked_outputs

        tracked_outputs = []
        used_object_ids = set()
        matches, uncertain, affected = associate(
            predictions, [inst["centroid"] for inst in valid_instances],
            self.max_distance, self.ambiguity_margin)
        if uncertain:
            self._event("ASSOCIATION_AMBIGUOUS", sorted(affected), severity="warning",
                        detection_indices=sorted(valid_indices[i] for i in uncertain))

        for index, inst in enumerate(valid_instances):
            if index in uncertain:
                continue
            cx, cy = inst["centroid"]
            best_id = matches.get(index)

            if best_id is not None:
                if self.tracked[best_id].disappeared:
                    self._event("TRACK_RECOVERED", [best_id])
                self.tracked[best_id].correct((cx, cy))
                self.tracked[best_id].disappeared = 0
                used_object_ids.add(best_id)
                assigned_id = best_id
            else:
                assigned_id = self._register((cx, cy))
                used_object_ids.add(assigned_id)

            inst_copy = inst.copy()
            inst_copy["id"] = assigned_id
            tracked_outputs.append(inst_copy)

        self._age_unmatched(used_object_ids)

        return tracked_outputs
