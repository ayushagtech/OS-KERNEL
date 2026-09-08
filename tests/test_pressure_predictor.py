import unittest

from backend.pressure_predictor import PressurePredictor, PressurePredictionConfig


class PressurePredictorTests(unittest.TestCase):
    def predictor(self, minimum_samples=5):
        return PressurePredictor(("memory",), PressurePredictionConfig(
            minimum_samples=minimum_samples, minimum_confidence=0.50,
            minimum_pressure=0.60, maximum_horizon_seconds=100.0,
        ))

    def add(self, predictor, values, start=0.0, step=10.0):
        for index, value in enumerate(values):
            predictor.add_sample("memory", start + index * step, value)

    def test_insufficient_samples(self):
        predictor = self.predictor()
        self.add(predictor, [0.6, 0.7, 0.8])
        result = predictor.predict("memory", 0.9)
        self.assertIsNone(result["seconds_to_threshold"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertFalse(result["predicted_threshold_crossing"])

    def test_stable_resource_has_no_crossing(self):
        predictor = self.predictor()
        self.add(predictor, [0.7] * 6)
        result = predictor.predict("memory", 0.9)
        self.assertEqual(result["trend_per_second"], 0.0)
        self.assertIsNone(result["seconds_to_threshold"])

    def test_increasing_resource_crosses_threshold(self):
        predictor = self.predictor()
        self.add(predictor, [0.60, 0.65, 0.70, 0.75, 0.80, 0.85])
        result = predictor.predict("memory", 0.90)
        self.assertGreater(result["trend_per_second"], 0.0)
        self.assertIsNotNone(result["seconds_to_threshold"])
        self.assertTrue(result["predicted_threshold_crossing"])
        self.assertGreaterEqual(result["confidence"], 0.50)

    def test_decreasing_resource_has_no_crossing(self):
        predictor = self.predictor()
        self.add(predictor, [0.85, 0.80, 0.75, 0.70, 0.65, 0.60])
        result = predictor.predict("memory", 0.90)
        self.assertLess(result["trend_per_second"], 0.0)
        self.assertIsNone(result["seconds_to_threshold"])

    def test_noisy_resource_does_not_trigger_false_positive(self):
        predictor = self.predictor()
        self.add(predictor, [0.62, 0.82, 0.61, 0.84, 0.63, 0.80])
        result = predictor.predict("memory", 0.90)
        self.assertFalse(result["predicted_threshold_crossing"])

    def test_confidence_is_bounded(self):
        predictor = self.predictor()
        self.add(predictor, [0.60, 0.65, 0.70, 0.75, 0.80, 0.85])
        result = predictor.predict("memory", 0.90)
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_threshold_already_crossed_is_explicit(self):
        predictor = self.predictor()
        self.add(predictor, [0.8, 0.85, 0.91, 0.92, 0.93])
        result = predictor.predict("memory", 0.90)
        self.assertEqual(result["seconds_to_threshold"], 0.0)
        self.assertTrue(result["predicted_threshold_crossing"])


if __name__ == "__main__":
    unittest.main()
