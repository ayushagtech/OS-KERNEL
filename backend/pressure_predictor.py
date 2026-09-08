"""Deterministic short-horizon pressure prediction.

This module estimates threshold crossings from recent measurements. It is a
bounded heuristic, not machine learning and not a crash predictor.
"""

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class PressureSample:
    timestamp: float
    value: float


@dataclass(frozen=True)
class PressurePredictionConfig:
    minimum_samples: int = 5
    minimum_confidence: float = 0.65
    minimum_pressure: float = 0.60
    minimum_trend: float = 0.0001
    maximum_horizon_seconds: float = 900.0
    history_limit: int = 45


class PressurePredictor:
    def __init__(self, resources: Iterable[str], config: PressurePredictionConfig = PressurePredictionConfig()):
        self.config = config
        self.history: Dict[str, List[PressureSample]] = {resource: [] for resource in resources}

    def add_sample(self, resource: str, timestamp: float, value: float) -> None:
        if resource not in self.history or not math.isfinite(float(timestamp)) or not math.isfinite(float(value)):
            return
        samples = self.history[resource]
        samples.append(PressureSample(float(timestamp), max(0.0, min(1.0, float(value)))))
        self.history[resource] = samples[-self.config.history_limit:]

    @staticmethod
    def _regression(samples: List[PressureSample]) -> Tuple[float, float, float]:
        origin = samples[0].timestamp
        xs = [sample.timestamp - origin for sample in samples]
        ys = [sample.value for sample in samples]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator <= 0:
            return 0.0, mean_y, 0.0
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
        intercept = mean_y - slope * mean_x
        predicted = [intercept + slope * x for x in xs]
        residual_variance = sum((y - estimate) ** 2 for y, estimate in zip(ys, predicted)) / len(ys)
        return slope, mean_y, residual_variance

    def predict(self, resource: str, threshold: float, now: Optional[float] = None) -> Dict[str, object]:
        samples = self.history.get(resource, [])
        config = self.config
        if len(samples) < config.minimum_samples:
            return self._result(resource, samples, threshold, None, 0.0,
                                "Insufficient sustained samples for prediction.")
        ordered = sorted(samples, key=lambda sample: sample.timestamp)
        elapsed = ordered[-1].timestamp - ordered[0].timestamp
        if elapsed <= 0:
            return self._result(resource, ordered, threshold, None, 0.0,
                                "Sample timestamps are not distinct.")
        slope, average, residual_variance = self._regression(ordered)
        latest = ordered[-1].value
        differences = [right.value - left.value for left, right in zip(ordered, ordered[1:])]
        direction = 1 if slope > 0 else -1 if slope < 0 else 0
        consistent = (sum(1 for difference in differences if difference * direction >= 0) / len(differences)
                      if direction and differences else 0.0)
        value_variance = sum((sample.value - average) ** 2 for sample in ordered) / len(ordered)
        noise_scale = max(value_variance, 1e-9)
        fit_stability = max(0.0, min(1.0, 1.0 - residual_variance / noise_scale))
        # A short observed span is still useful; confidence increases as the
        # trend remains observable across a one-minute evidence window.
        recency = max(0.0, min(1.0, elapsed / 60.0))
        sample_confidence = min(1.0, (len(ordered) - config.minimum_samples + 1) / 8.0)
        confidence = max(0.0, min(1.0, 0.30 * sample_confidence
                                 + 0.30 * consistent
                                 + 0.20 * fit_stability
                                 + 0.20 * recency))
        time_to_threshold = None
        if latest >= threshold:
            time_to_threshold = 0.0
        elif slope > config.minimum_trend:
            estimate = (threshold - latest) / slope
            if estimate >= 0:
                time_to_threshold = estimate
        predictive = (time_to_threshold is not None
                      and time_to_threshold <= config.maximum_horizon_seconds
                      and latest >= config.minimum_pressure
                      and slope >= config.minimum_trend
                      and confidence >= config.minimum_confidence
                      and consistent >= 0.60)
        if time_to_threshold is None:
            reason = "Trend does not indicate an increasing threshold crossing."
        elif predictive:
            reason = "Sustained increasing trend indicates a possible short-horizon threshold crossing."
        else:
            reason = "A crossing estimate exists, but pressure, confidence, consistency, or horizon gates are not met."
        return self._result(resource, ordered, threshold, time_to_threshold, confidence, reason,
                            slope=slope, average=average, variance=value_variance,
                            predictive=predictive)

    @staticmethod
    def _result(resource: str, samples: List[PressureSample], threshold: float,
                time_to_threshold: Optional[float], confidence: float, reason: str,
                slope: float = 0.0, average: float = 0.0, variance: float = 0.0,
                predictive: bool = False) -> Dict[str, object]:
        current = samples[-1].value if samples else None
        return {"resource": resource, "current_pressure": current,
                "trend_per_second": slope, "recent_average": average,
                "variance": variance, "threshold": threshold,
                "seconds_to_threshold": time_to_threshold,
                "confidence": max(0.0, min(1.0, confidence)),
                "predicted_threshold_crossing": predictive,
                "reason": reason, "sample_count": len(samples)}

    def predict_all(self, thresholds: Dict[str, float], now: Optional[float] = None) -> Dict[str, Dict[str, object]]:
        return {resource: self.predict(resource, threshold, now=now)
                for resource, threshold in thresholds.items() if resource in self.history}
