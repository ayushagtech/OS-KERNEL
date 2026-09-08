"""Deterministic, bounded adaptive mitigation memory.

This is explainable outcome statistics with decay, not machine learning or
reinforcement learning. History can adjust ranking only after safety checks.
"""

from dataclasses import dataclass
import json
import math
import os
import time
from typing import Any, Dict, Iterable, List, Optional


MEMORY_VERSION = 1
DEFAULT_LIMIT = 200
DEFAULT_HALF_LIFE_SECONDS = 3600.0
MAX_HISTORY_ADJUSTMENT = 2.5


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, _finite(value)))


def pressure_bucket(value: Any) -> str:
    value = _clamp(value)
    if value < 0.25:
        return "LOW"
    if value < 0.50:
        return "MEDIUM"
    if value < 0.75:
        return "HIGH"
    return "CRITICAL"


@dataclass(frozen=True)
class StateSignature:
    cpu: str
    memory: str
    swap: str
    io: str
    network: str
    process_class: str
    foreground: bool
    security: str
    cpu_characteristic: str
    memory_characteristic: str

    def general_key(self) -> str:
        return "|".join((self.cpu, self.memory, self.swap, self.io, self.network,
                         str(self.foreground), self.security,
                         self.cpu_characteristic, self.memory_characteristic))

    def process_key(self) -> str:
        return f"{self.general_key()}|class={self.process_class}"

    def to_dict(self) -> Dict[str, Any]:
        return {"cpu": self.cpu, "memory": self.memory, "swap": self.swap,
                "io": self.io, "network": self.network,
                "process_class": self.process_class, "foreground": self.foreground,
                "security": self.security,
                "cpu_characteristic": self.cpu_characteristic,
                "memory_characteristic": self.memory_characteristic}


def build_state_signature(telemetry: Dict[str, Any], process: Dict[str, Any]) -> StateSignature:
    state = telemetry.get("resource_state", {})
    cpu = _clamp(state.get("cpu_pressure", telemetry.get("cpu", {}).get("pressure")))
    memory = _clamp(state.get("memory_pressure"))
    swap = _clamp(state.get("swap_pressure"))
    io = _clamp(state.get("io_pressure"))
    network = _clamp(state.get("network_pressure"))
    security = _clamp(process.get("security_suspicion", 0.0))
    cpu_characteristic = "HIGH_CPU" if _finite(process.get("cpu_percent")) >= 50 else "NORMAL_CPU"
    memory_characteristic = "HIGH_MEMORY" if _finite(process.get("memory_percent")) >= 15 else "NORMAL_MEMORY"
    return StateSignature(
        cpu=pressure_bucket(cpu), memory=pressure_bucket(memory),
        swap=pressure_bucket(swap), io=pressure_bucket(io),
        network=pressure_bucket(network),
        process_class=str(process.get("process_category", "unknown")),
        foreground=bool(process.get("is_foreground")),
        security=pressure_bucket(security),
        cpu_characteristic=cpu_characteristic,
        memory_characteristic=memory_characteristic,
    )


@dataclass(frozen=True)
class EffectivenessStats:
    count: int
    weighted_effectiveness: float
    success_rate: float
    average_recovery_time: float
    escalation_rate: float
    historical_adjustment: float

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class AdaptiveMitigationMemory:
    def __init__(self, path: Optional[str] = None, limit: int = DEFAULT_LIMIT,
                 half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS):
        self.path = (os.environ.get("GUARDIAN_EXPERIENCE_PATH", "guardian_experience.json")
                 if path is None else path)
        self.limit = max(1, int(limit))
        self.half_life_seconds = max(1.0, float(half_life_seconds))
        self.records: List[Dict[str, Any]] = []
        self.load()

    @staticmethod
    def effectiveness(actual_relief: Any, stability_improvement: Any,
                      restoration_success: bool, user_disruption: Any,
                      collateral_cost: Any, failed: bool,
                      escalation_required: bool) -> float:
        score = (0.45 * _clamp(actual_relief)
                 + 0.20 * _clamp(stability_improvement)
                 + 0.15 * (1.0 if restoration_success else 0.0)
                 - 0.10 * _clamp(user_disruption)
                 - 0.05 * _clamp(collateral_cost)
                 - 0.20 * (1.0 if failed else 0.0)
                 - 0.05 * (1.0 if escalation_required else 0.0))
        return _clamp(score)

    @staticmethod
    def _valid_record(record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        required = {"state_signature", "action", "timestamp", "effectiveness"}
        if not required.issubset(record):
            return False
        timestamp = _finite(record.get("timestamp"), -1.0)
        return timestamp > 0 and 0.0 <= _finite(record.get("effectiveness"), -1.0) <= 1.0

    def load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("version") != MEMORY_VERSION or not isinstance(payload.get("records"), list):
                return
            self.records = [record for record in payload["records"] if self._valid_record(record)][-self.limit:]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.records = []

    def save(self) -> None:
        if not self.path:
            return
        payload = {"version": MEMORY_VERSION, "records": self.records[-self.limit:]}
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
        except OSError:
            return

    def record(self, *, state_signature: StateSignature, process_identity: Optional[Dict[str, Any]],
               action: str, telemetry_before: Dict[str, Any], telemetry_after: Dict[str, Any],
               expected_relief: float, actual_relief: float, user_disruption: float,
               duration_seconds: float, restoration_result: Dict[str, Any],
               escalation_required: bool, failed: bool, safety_outcome: Dict[str, Any],
               collateral_cost: float = 0.0, stability_improvement: float = 0.0,
               timestamp: Optional[float] = None) -> Dict[str, Any]:
        timestamp = _finite(timestamp, time.time())
        record = {
            "state_signature": state_signature.to_dict(),
            "state_key": state_signature.process_key(),
            "general_state_key": state_signature.general_key(),
            "process_identity": process_identity,
            "action": str(action),
            "timestamp": timestamp,
            "telemetry_before": telemetry_before,
            "telemetry_after": telemetry_after,
            "expected_relief": _clamp(expected_relief),
            "actual_relief": _clamp(actual_relief),
            "user_disruption": _clamp(user_disruption),
            "duration_seconds": max(0.0, _finite(duration_seconds)),
            "restoration_result": restoration_result,
            "restoration_success": bool(restoration_result.get("restoration_success", False)),
            "escalation_required": bool(escalation_required),
            "failed": bool(failed),
            "safety_outcome": safety_outcome,
            "collateral_cost": _clamp(collateral_cost),
            "stability_improvement": _clamp(stability_improvement),
        }
        record["effectiveness"] = self.effectiveness(
            record["actual_relief"], record["stability_improvement"],
            record["restoration_success"], record["user_disruption"],
            record["collateral_cost"], record["failed"], record["escalation_required"])
        if self._valid_record(record):
            self.records.append(record)
            self.records = self.records[-self.limit:]
            self.save()
        return record

    def _stats(self, records: Iterable[Dict[str, Any]], now: Optional[float] = None) -> EffectivenessStats:
        now = _finite(now, time.time())
        weighted = []
        for record in records:
            age = max(0.0, now - _finite(record.get("timestamp"), now))
            weight = math.exp(-math.log(2.0) * age / self.half_life_seconds)
            weighted.append((record, weight))
        total_weight = sum(weight for _, weight in weighted)
        if not weighted or total_weight <= 0:
            return EffectivenessStats(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        average = sum(record["effectiveness"] * weight for record, weight in weighted) / total_weight
        success = sum((not record.get("failed")) * weight for record, weight in weighted) / total_weight
        recovery = sum(record.get("duration_seconds", 0.0) * weight for record, weight in weighted) / total_weight
        escalation = sum(bool(record.get("escalation_required")) * weight for record, weight in weighted) / total_weight
        confidence = min(0.85, total_weight / 10.0)
        adjustment = max(-MAX_HISTORY_ADJUSTMENT, min(MAX_HISTORY_ADJUSTMENT,
                         (average - 0.5) * 5.0 * confidence))
        return EffectivenessStats(len(weighted), average, success, recovery, escalation, adjustment)

    def stats(self, state_signature: StateSignature, action: str) -> Dict[str, Any]:
        specific = [record for record in self.records
                    if record.get("state_key") == state_signature.process_key()
                    and record.get("action") == action]
        general = [record for record in self.records
                   if record.get("general_state_key") == state_signature.general_key()
                   and record.get("action") == action]
        specific_stats = self._stats(specific)
        general_stats = self._stats(general)
        selected = specific_stats if specific_stats.count else general_stats
        return {"specific": specific_stats.to_dict(), "general": general_stats.to_dict(),
                "selected": selected.to_dict(), "adjustment": selected.historical_adjustment}

    def action_summary(self) -> List[Dict[str, Any]]:
        actions = sorted({record.get("action") for record in self.records if record.get("action")})
        summary = []
        for action in actions:
            stats = self._stats([record for record in self.records if record.get("action") == action])
            summary.append({"action": action, **stats.to_dict()})
        return summary

    def update_restoration(self, process_identity: Optional[Dict[str, Any]], action: str,
                           restoration_result: Dict[str, Any]) -> None:
        """Attach the verified restoration result to the latest matching record."""
        for record in reversed(self.records):
            if (record.get("action") == action
                    and record.get("process_identity") == process_identity):
                record["restoration_result"] = restoration_result
                record["restoration_success"] = bool(restoration_result.get("restoration_success", False))
                record["effectiveness"] = self.effectiveness(
                    record.get("actual_relief"), record.get("stability_improvement"),
                    record["restoration_success"], record.get("user_disruption"),
                    record.get("collateral_cost"), record.get("failed", False),
                    record.get("escalation_required", False))
                self.save()
                return
