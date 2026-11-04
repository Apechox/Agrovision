"""
MÓDULO DE SEGUIMIENTO CON FILTRO DE KALMAN (Actividad A2.4)

¿CÓMO TRABAJAR AQUÍ?
1. `KalmanCentroidTracker.update()` tiene la MISMA firma y el MISMO contrato de salida que
   `CentroidTracker.update()` en `track.py` (lista de instancias con `"id"` agregado), para que
   `main_test.py` pueda intercambiar uno por otro con `--tracker kalman`.
2. Cada objeto tiene su propio `cv2.KalmanFilter` con estado [x, y, vx, vy] y medición [x, y].
   Ajusta `process_noise`/`measurement_noise` si el seguimiento queda muy "nervioso" (súbelo) o
   muy "lento" para reaccionar a cambios de velocidad reales (bájalo).
3. La asociación usa la posición PREDICHA (`predict()`) de cada Kalman activo, no la última
   medición cruda; así un tomate que se movió durante una oclusión igual se reasocia.

Devuelve la misma lista de diccionarios que entregó Segmentación, agregando `"id"` (int).
"""

import math

import cv2
import numpy as np


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
        # OpenCV inicializa errorCovPost en cero, lo que anula la ganancia de Kalman en la
        # primera corrección (K = P·Hᵀ·(H·P·Hᵀ+R)⁻¹ = 0 si P=0) y deja la velocidad "congelada"
        # en 0 durante varios cuadros. Se parte con incertidumbre alta para que el filtro
        # confíe en las primeras mediciones y la velocidad converja rápido.
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
                 process_noise=1e-2, measurement_noise=1e-1):
        self.next_object_id = 1
        self.tracked = {}  # {id: _TrackedTomato}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

    def reset(self):
        """Regla T2.4.2: limpia los objetos activos tras una interrupción de la fuente."""
        self.tracked.clear()

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
        if suspend_observations:
            return []

        valid_instances = [inst for inst in instances if inst.get("is_valid_mask", True)]

        # Predice la posición de cada tomate ya seguido ANTES de asociar (esto es lo que
        # diferencia a este tracker del CentroidTracker simple).
        predictions = {obj_id: t.predict() for obj_id, t in self.tracked.items()}

        if len(valid_instances) == 0:
            for obj_id in list(self.tracked.keys()):
                self.tracked[obj_id].disappeared += 1
                if self.tracked[obj_id].disappeared > self.max_disappeared:
                    self._deregister(obj_id)
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

        for inst in valid_instances:
            cx, cy = inst["centroid"]
            best_id = None
            min_dist = float("inf")

            for obj_id, (pred_x, pred_y) in predictions.items():
                if obj_id in used_object_ids:
                    continue
                dist = math.hypot(cx - pred_x, cy - pred_y)
                if dist < min_dist and dist <= self.max_distance:
                    min_dist = dist
                    best_id = obj_id

            if best_id is not None:
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

        for obj_id in list(self.tracked.keys()):
            if obj_id not in used_object_ids:
                self.tracked[obj_id].disappeared += 1
                if self.tracked[obj_id].disappeared > self.max_disappeared:
                    self._deregister(obj_id)

        return tracked_outputs
