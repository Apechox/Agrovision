"""Asociación geométrica conjunta y rechazo conservador de alternativas ambiguas.

SciPy resuelve la asignación. Las columnas ficticias permiten dejar tracks sin
detección: primero se maximiza el número de pares dentro del umbral y luego se
minimiza su distancia total. Esto no demuestra identidad física por sí solo.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment


def associate(predictions, centroids, max_distance, ambiguity_margin):
    """Devuelve {índice detección: ID}, índices dudosos e IDs afectados.

Una alternativa con igual número de pares y coste a no más de ambiguity_margin
píxeles del óptimo bloquea todos los pares que cambian entre ambas soluciones.
No se crean IDs nuevos para detecciones dudosas en ese cuadro.
"""
    ids = sorted(predictions)
    if not ids or not centroids:
        return {}, set(), set()
    positions = np.asarray([predictions[i] for i in ids], dtype=float)
    detected = np.asarray(centroids, dtype=float)
    distances = np.linalg.norm(positions[:, None, :] - detected[None, :, :], axis=2)
    n, m = distances.shape
    # Cada distancia admisible normalizada <= 1; perder un par cuesta > n.
    scale = max(max_distance, 1.0)
    penalty = float(n + 1)
    costs = np.full((n, m + n), penalty, dtype=float)
    costs[:, :m] = np.where(distances <= max_distance, distances / scale, np.inf)

    def solve(matrix):
        rows, cols = linear_sum_assignment(matrix)
        pairs = {int(r): int(c) for r, c in zip(rows, cols) if c < m}
        total = sum(float(distances[r, c]) for r, c in pairs.items())
        return pairs, total

    best, best_cost = solve(costs)
    uncertain_rows, uncertain_cols = set(), set()
    # Prohibir cada par del óptimo detecta también intercambios globales, no solo
    # empates con el vecino más cercano. Coste mayor que una única asignación.
    for row, col in best.items():
        alternative_costs = costs.copy()
        alternative_costs[row, col] = np.inf
        alternative, total = solve(alternative_costs)
        if len(alternative) != len(best) or total - best_cost > ambiguity_margin + 1e-9:
            continue
        for changed_row in set(best) | set(alternative):
            if best.get(changed_row) != alternative.get(changed_row):
                uncertain_rows.add(changed_row)
                if changed_row in best:
                    uncertain_cols.add(best[changed_row])
                if changed_row in alternative:
                    uncertain_cols.add(alternative[changed_row])
    matches = {col: ids[row] for row, col in best.items()
               if row not in uncertain_rows and col not in uncertain_cols}
    return matches, uncertain_cols, {ids[row] for row in uncertain_rows}
