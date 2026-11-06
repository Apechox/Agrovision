"""Pruebas aisladas del tracker existente; sin cámara, OpenCV ni dataset.

El fallo esperado documenta una limitación real, no una función implementada.
"""
import unittest

from funciones.tracking.track import CentroidTracker


def detection(x, y=100, valid=True):
    return {"centroid": (x, y), "bbox": (x - 5, y - 5, 10, 10),
            "area_px": 100.0, "is_valid_mask": valid}


class TrackingBaselineTests(unittest.TestCase):
    def test_one_fruit_keeps_id_while_moving(self):
        tracker = CentroidTracker(max_distance=15)
        ids = [tracker.update([detection(x)])[0]["id"] for x in (100, 110, 120)]
        self.assertEqual(ids, [1, 1, 1])

    def test_separated_fruits_keep_ids_when_detection_order_changes(self):
        tracker = CentroidTracker(max_distance=15)
        tracker.update([detection(100), detection(200)])
        result = tracker.update([detection(210), detection(110)])
        self.assertEqual({r["centroid"][0]: r["id"] for r in result}, {110: 1, 210: 2})

    def test_short_gap_recovers_id_within_distance_gate(self):
        tracker = CentroidTracker(max_disappeared=2, max_distance=30)
        first = tracker.update([detection(100)])[0]["id"]
        self.assertEqual(tracker.update([]), [])
        self.assertEqual(tracker.update([]), [])
        self.assertEqual(tracker.update([detection(125)])[0]["id"], first)

    def test_expired_track_does_not_reuse_old_identity(self):
        tracker = CentroidTracker(max_disappeared=2)
        first = tracker.update([detection(100)])[0]["id"]
        for _ in range(3):
            tracker.update([])
        self.assertEqual(tracker.objects, {})
        self.assertNotEqual(tracker.update([detection(100)])[0]["id"], first)

    def test_distant_detection_is_not_attached_to_old_fruit(self):
        tracker = CentroidTracker(max_distance=15)
        first = tracker.update([detection(100)])[0]["id"]
        self.assertNotEqual(tracker.update([detection(200)])[0]["id"], first)

    def test_one_id_is_not_assigned_twice_in_one_frame(self):
        tracker = CentroidTracker(max_distance=15)
        tracker.update([detection(100)])
        ids = [r["id"] for r in tracker.update([detection(105), detection(110)])]
        self.assertEqual(len(set(ids)), 2)

    def test_missing_fruit_ages_even_if_other_fruit_is_visible(self):
        tracker = CentroidTracker(max_disappeared=1, max_distance=15)
        tracker.update([detection(100), detection(200)])
        tracker.update([detection(110)])
        result = tracker.update([detection(120)])
        self.assertEqual(result[0]["id"], 1)
        self.assertNotIn(2, tracker.objects)

    def test_reset_removes_old_associations(self):
        tracker = CentroidTracker()
        old_id = tracker.update([detection(100)])[0]["id"]
        tracker.reset()
        self.assertEqual(tracker.objects, {})
        self.assertEqual(tracker.disappeared, {})
        # Current reset intentionally characterized: its ID counter is not reset.
        self.assertNotEqual(tracker.update([detection(100)])[0]["id"], old_id)

    def test_suspension_emits_nothing_but_currently_freezes_tracks(self):
        tracker = CentroidTracker(max_disappeared=1)
        tracker.update([detection(100)])
        for _ in range(3):
            self.assertEqual(tracker.update([], suspend_observations=True), [])
        self.assertEqual(tracker.objects, {1: (100, 100)})
        self.assertEqual(tracker.disappeared, {1: 0})

    def test_invalid_mask_is_currently_excluded_from_tracking(self):
        tracker = CentroidTracker()
        self.assertEqual(tracker.update([detection(100, valid=False)]), [])
        self.assertEqual(tracker.objects, {})

    def test_output_preserves_detection_fields_without_adding_id_to_input(self):
        tracker = CentroidTracker()
        original = detection(100)
        original["type_hint"] = "tomate"  # Preserved metadata, not inferred by tracker.
        result = tracker.update([original])[0]
        self.assertNotIn("id", original)
        self.assertEqual({k: v for k, v in result.items() if k != "id"}, original)

    @unittest.expectedFailure
    def test_known_gap_association_should_not_depend_on_list_order(self):
        def associate(positions):
            tracker = CentroidTracker(max_distance=8)
            tracker.update([detection(100), detection(110)])
            return {r["centroid"][0]: r["id"]
                    for r in tracker.update([detection(x) for x in positions])}
        # Same scene, different list order: current greedy matching gives different IDs.
        self.assertEqual(associate([106, 111]), associate([111, 106]))


if __name__ == "__main__":
    unittest.main()
