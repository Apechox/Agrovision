"""
MÓDULO DE SEGUIMIENTO MULTIOBJETO (Actividad A2.4)

¿CÓMO TRABAJAR AQUÍ?
1. Ya incluye un algoritmo funcional de distancia entre centroides (asigna el mismo ID
   al tomate mientras avanza por la cinta).
2. Ajusta `max_distance` (cuántos píxeles máximo se mueve un tomate entre 2 frames)
   y `max_disappeared` según la velocidad real de la cinta.
3. Usa el método `reset()` y haz pruebas cortando el video para verificar que no
   se dupliquen los tomates ni se hereden etiquetas viejas.

Devuelve la misma lista de diccionarios que entregó Segmentación, pero agregando la llave `"id"`:
    inst["id"] = int (ID único del tomate en la sesión)
"""

import math

class CentroidTracker:
    def __init__(self, max_disappeared=10, max_distance=80.0):
        self.next_object_id = 1
        self.objects = {}       # Diccionario: {id: (cx, cy)}
        self.disappeared = {}   # Diccionario: {id: frames_desaparecido}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def reset(self):
        """Regla T2.4.2: Limpia los objetos activos tras una interrupción."""
        self.objects.clear()
        self.disappeared.clear()

    def _register(self, centroid):
        obj_id = self.next_object_id
        self.objects[obj_id] = centroid
        self.disappeared[obj_id] = 0
        self.next_object_id += 1
        return obj_id

    def _deregister(self, obj_id):
        del self.objects[obj_id]
        del self.disappeared[obj_id]

    def update(self, instances, suspend_observations=False):
        # Si la fuente falló, suspender inmediatamente
        if suspend_observations:
            return []

        # Filtrar solo máscaras válidas (que no estén cortadas en el borde)
        valid_instances = [inst for inst in instances if inst.get("is_valid_mask", True)]

        # Si no hay tomates en pantalla, aumentar contador de desaparecidos
        if len(valid_instances) == 0:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)
            return []

        # Si no estábamos siguiendo ningún tomate, registrar todos los nuevos
        if len(self.objects) == 0:
            tracked_outputs = []
            for inst in valid_instances:
                new_id = self._register(inst["centroid"])
                inst_copy = inst.copy()
                inst_copy["id"] = new_id
                tracked_outputs.append(inst_copy)
            return tracked_outputs

        # Emparejar tomates actuales con los del frame anterior por distancia mínima
        tracked_outputs = []
        used_object_ids = set()

        for inst in valid_instances:
            cx, cy = inst["centroid"]
            best_id = None
            min_dist = float("inf")

            for obj_id, (prev_cx, prev_cy) in self.objects.items():
                if obj_id in used_object_ids:
                    continue
                dist = math.hypot(cx - prev_cx, cy - prev_cy)
                if dist < min_dist and dist <= self.max_distance:
                    min_dist = dist
                    best_id = obj_id

            if best_id is not None:
                # Es el mismo tomate que avanzó en la cinta
                self.objects[best_id] = (cx, cy)
                self.disappeared[best_id] = 0
                used_object_ids.add(best_id)
                assigned_id = best_id
            else:
                # Es un tomate nuevo entrando a la zona válida
                assigned_id = self._register((cx, cy))
                used_object_ids.add(assigned_id)

            inst_copy = inst.copy()
            inst_copy["id"] = assigned_id
            tracked_outputs.append(inst_copy)

        # Actualizar los que no aparecieron en este frame
        for obj_id in list(self.objects.keys()):
            if obj_id not in used_object_ids:
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)

        return tracked_outputs
