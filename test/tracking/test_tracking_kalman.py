"""Regresiones de identidad y ambigüedad; parámetros y escenas sintéticos."""
import unittest

import cv2
import numpy as np

from funciones.seg import ClassicSegmenter
from funciones.tracking.track import CentroidTracker
from funciones.tracking.track_kalman import KalmanCentroidTracker


def detection(x, y=100, valid=True):
    return {"centroid": (x, y), "is_valid_mask": valid, "bbox": (x - 10, y - 10, 20, 20)}


class KalmanTrackingTests(unittest.TestCase):
    def test_global_association_preserves_both_ids_in_previous_failure(self):
        for order in ([106, 111], [111, 106]):
            with self.subTest(order=order):
                tracker = KalmanCentroidTracker(max_distance=8)
                tracker.update([detection(100), detection(110)])
                result = tracker.update([detection(x) for x in order])
                self.assertEqual({r['centroid'][0]: r['id'] for r in result}, {106: 1, 111: 2})

    def test_equal_global_alternatives_do_not_transfer_ids(self):
        tracker = KalmanCentroidTracker(max_distance=30)
        tracker.update([detection(100), detection(120)])
        # Two equal total-cost assignments, even though local nearest neighbours differ.
        result = tracker.update([detection(125), detection(130)])
        self.assertEqual(result, [])
        self.assertEqual(tracker.next_object_id, 3)
        event = next(e for e in tracker.last_events if e['code'] == 'ASSOCIATION_AMBIGUOUS')
        self.assertEqual(event['track_ids'], [1, 2])
        self.assertEqual(event['detection_indices'], [0, 1])

    def test_ambiguity_does_not_block_an_independent_fruit(self):
        tracker = KalmanCentroidTracker(max_distance=30)
        tracker.update([detection(100), detection(120), detection(300)])
        result = tracker.update([detection(125), detection(130), detection(305)])
        self.assertEqual([(r['centroid'][0], r['id']) for r in result], [(305, 3)])

    def test_incident_indices_refer_to_original_input_including_invalid_masks(self):
        tracker = KalmanCentroidTracker(max_distance=30)
        tracker.update([detection(100), detection(120)])
        tracker.update([detection(50, valid=False), detection(125), detection(130)])
        event = next(e for e in tracker.last_events if e['code'] == 'ASSOCIATION_AMBIGUOUS')
        self.assertEqual(event['detection_indices'], [1, 2])

    def test_one_track_two_equally_likely_detections_does_not_create_duplicate(self):
        tracker = KalmanCentroidTracker(max_distance=10)
        tracker.update([detection(100)])
        self.assertEqual(tracker.update([detection(99), detection(101)]), [])
        self.assertEqual(tracker.next_object_id, 2)

    def test_prediction_recovers_motion_after_two_missing_frames(self):
        tracker = KalmanCentroidTracker(max_distance=15)
        baseline = CentroidTracker(max_distance=15)
        for x in (100, 110, 120, 130, 140, 150):
            self.assertEqual(tracker.update([detection(x)])[0]['id'], 1)
            baseline.update([detection(x)])
        for _ in range(2):
            self.assertEqual(tracker.update([]), [])
            baseline.update([])
        self.assertEqual(tracker.update([detection(180)])[0]['id'], 1)
        self.assertNotEqual(baseline.update([detection(180)])[0]['id'], 1)
        self.assertIn('TRACK_RECOVERED', [e['code'] for e in tracker.last_events])

    def test_expiry_emits_once_and_reappearance_gets_new_id(self):
        tracker = KalmanCentroidTracker(max_disappeared=1)
        tracker.update([detection(100)])
        tracker.update([])
        tracker.update([])
        self.assertEqual([e['code'] for e in tracker.last_events], ['TRACK_LOST_TIMEOUT'])
        tracker.update([])
        self.assertEqual(tracker.last_events, [])
        self.assertEqual(tracker.update([detection(100)])[0]['id'], 2)

    def test_reset_closes_tracks_without_recycling_ids(self):
        tracker = KalmanCentroidTracker()
        tracker.update([detection(100)])
        tracker.reset(reason='signal_lost')
        self.assertEqual(tracker.tracked, {})
        self.assertEqual(tracker.last_events[0]['reason'], 'signal_lost')
        self.assertEqual(tracker.update([detection(100)])[0]['id'], 2)

    def test_suspension_emits_no_observation_and_does_not_age_tracks(self):
        tracker = KalmanCentroidTracker(max_disappeared=0)
        tracker.update([detection(100)])
        self.assertEqual(tracker.update([], suspend_observations=True), [])
        self.assertEqual(tracker.tracked[1].disappeared, 0)
        self.assertEqual(tracker.update_index, 1)

    def test_far_detection_starts_new_track(self):
        tracker = KalmanCentroidTracker(max_distance=8)
        tracker.update([detection(100)])
        self.assertEqual(tracker.update([detection(200)])[0]['id'], 2)

    def test_zero_distance_gate_accepts_exact_match(self):
        tracker = KalmanCentroidTracker(max_distance=0)
        tracker.update([detection(100)])
        self.assertEqual(tracker.update([detection(100)])[0]['id'], 1)

    def test_invalid_mask_is_not_used_or_emitted(self):
        tracker = KalmanCentroidTracker()
        self.assertEqual(tracker.update([detection(100, valid=False)]), [])
        self.assertEqual(tracker.tracked, {})

    def test_original_detection_data_is_preserved(self):
        tracker = KalmanCentroidTracker()
        original = detection(100)
        original['type_hint'] = 'tomate'
        result = tracker.update([original])[0]
        self.assertNotIn('id', original)
        self.assertEqual({k: v for k, v in result.items() if k != 'id'}, original)

    def test_nonfinite_centroid_rejected_before_state_changes(self):
        tracker = KalmanCentroidTracker()
        tracker.update([detection(100)])
        with self.assertRaises(ValueError):
            tracker.update([detection(float('nan'))])
        self.assertEqual(tracker.update_index, 1)
        self.assertEqual(tracker.tracked[1].disappeared, 0)

    def test_invalid_configuration_rejected(self):
        for kwargs in ({'max_distance': -1}, {'max_distance': float('nan')},
                       {'max_disappeared': -1}, {'ambiguity_margin': -1},
                       {'measurement_noise': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                KalmanCentroidTracker(**kwargs)

    def test_segmentation_to_tracker_on_generated_image_sequence(self):
        segmenter = ClassicSegmenter()
        tracker = KalmanCentroidTracker(max_distance=15)
        identity_by_lane = {}
        for frame_idx in range(15):
            frame = np.full((240, 420, 3), 120, dtype=np.uint8)
            for y in (70, 170):
                cv2.circle(frame, (80 + frame_idx * 8, y), 20, (0, 0, 220), -1)
            _, instances = segmenter.process(frame)
            tracked = tracker.update(instances)
            self.assertEqual(len(tracked), 2)
            for obj in tracked:
                lane = obj['centroid'][1]
                identity_by_lane.setdefault(lane, obj['id'])
                self.assertEqual(obj['id'], identity_by_lane[lane])
        self.assertEqual(len(set(identity_by_lane.values())), 2)


if __name__ == '__main__':
    unittest.main()
