"""Safety gate, intervention registry, and idempotent restoration."""

from dataclasses import dataclass, field
import os
import time
import uuid
from typing import Any, Dict, Optional, Set

try:
    import psutil
except ImportError:
    psutil = None

from backend.control_interface import ControlAdapter, ControlResult
from backend.process_identity import ProcessIdentity


LIFECYCLE_STATES = (
    "DETECTED", "PROPOSED", "BID_SELECTED", "SAFETY_CHECKED", "APPLIED",
    "MONITORED", "RECOVERED", "RESTORED", "VERIFIED", "RECORDED",
    "REJECTED", "FAILED", "EXPIRED", "RESTORATION_FAILED",
)
LEGAL_TRANSITIONS = {
    "DETECTED": {"PROPOSED", "REJECTED"},
    "PROPOSED": {"BID_SELECTED", "REJECTED"},
    "BID_SELECTED": {"SAFETY_CHECKED", "REJECTED"},
    "SAFETY_CHECKED": {"APPLIED", "FAILED", "REJECTED"},
    "APPLIED": {"MONITORED", "EXPIRED", "FAILED"},
    "MONITORED": {"MONITORED", "RECOVERED", "EXPIRED", "FAILED"},
    "RECOVERED": {"RESTORED", "FAILED", "RESTORATION_FAILED"},
    "RESTORED": {"VERIFIED", "RESTORATION_FAILED"},
    "VERIFIED": {"RECORDED"},
    "RECORDED": set(),
    "REJECTED": set(),
    "FAILED": set(),
    "EXPIRED": {"RESTORED", "RESTORATION_FAILED"},
    "RESTORATION_FAILED": set(),
}


@dataclass
class InterventionState:
    intervention_id: str
    process_identity: ProcessIdentity
    resource_domain: str
    selected_action: str
    start_time: float
    current_state: str
    telemetry_before: Dict[str, Any]
    expected_relief: Optional[float] = None
    actual_relief: Optional[float] = None
    safety_decision: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    restoration_result: Optional[Dict[str, Any]] = None
    telemetry_after: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None
    failure_reason: Optional[str] = None
    recovery_samples: int = 0

    def transition(self, next_state: str) -> None:
        if next_state not in LIFECYCLE_STATES:
            raise ValueError(f"Unknown intervention state: {next_state}")
        if next_state not in LEGAL_TRANSITIONS.get(self.current_state, set()):
            raise ValueError(f"Invalid intervention transition: {self.current_state} -> {next_state}")
        self.current_state = next_state

    def to_dict(self) -> Dict[str, Any]:
        return {"intervention_id": self.intervention_id,
                "process_identity": self.process_identity.to_dict(),
                "resource_domain": self.resource_domain,
                "selected_action": self.selected_action,
                "start_time": self.start_time,
                "current_state": self.current_state,
                "telemetry_before": self.telemetry_before,
                "expected_relief": self.expected_relief,
                "actual_relief": self.actual_relief,
                "safety_decision": self.safety_decision,
                "execution_result": self.execution_result,
                "restoration_result": self.restoration_result,
                "telemetry_after": self.telemetry_after,
                "duration": self.duration,
                "failure_reason": self.failure_reason,
                "recovery_samples": self.recovery_samples}


@dataclass
class GovernorLimits:
    max_cpu_reduction: float = 0.75
    max_duration_seconds: float = 30.0
    max_simultaneous_interventions: int = 3
    cooldown_seconds: float = 5.0
    max_repeated_failures: int = 3
    minimum_confidence: float = 0.50
    recovery_threshold: float = 0.50
    recovery_consecutive_samples: int = 2


@dataclass
class Intervention:
    process_identity: ProcessIdentity
    action: str
    start_time: float
    original_state: Dict[str, Any]
    applied_state: Dict[str, Any]
    reason: str
    telemetry_before: Dict[str, Any]
    expected_benefit: Dict[str, Any]
    expires_at: float
    restoration_token: Optional[Dict[str, Any]] = None
    status: str = "active"
    restoration_result: Optional[Dict[str, Any]] = None
    failure_count: int = 0
    lifecycle: Optional[InterventionState] = None


class InterventionRegistry:
    def __init__(self):
        self.active: Dict[ProcessIdentity, Intervention] = {}
        self.completed: list[Intervention] = []
        self.failures: Dict[ProcessIdentity, int] = {}

    def failure_count(self, identity: ProcessIdentity) -> int:
        return self.failures.get(identity, 0)

    def record_failure(self, identity: ProcessIdentity) -> None:
        self.failures[identity] = self.failure_count(identity) + 1

    def add(self, intervention: Intervention) -> None:
        self.active[intervention.process_identity] = intervention

    def get(self, identity: ProcessIdentity) -> Optional[Intervention]:
        return self.active.get(identity)

    def finish(self, identity: ProcessIdentity, status: str, result: Dict[str, Any]) -> None:
        intervention = self.active.pop(identity, None)
        if intervention:
            intervention.status = status
            intervention.restoration_result = result
            self.completed.append(intervention)
            self.completed = self.completed[-100:]


class SafetyGovernor:
    def __init__(self, adapter: ControlAdapter, limits: Optional[GovernorLimits] = None,
                 protected_identities: Optional[Set[ProcessIdentity]] = None):
        self.adapter = adapter
        self.limits = limits or GovernorLimits()
        self.registry = InterventionRegistry()
        self.protected_identities = protected_identities or set()

    @staticmethod
    def _reject(identity: Optional[ProcessIdentity], action: str, reason: str,
                error_type: str = "SafetyRejected") -> Dict[str, Any]:
        return {"status": "rejected", "success": False, "action": action,
                "process_identity": identity.to_dict() if identity else None,
                "mechanism": "safety-governor", "error_type": error_type,
                "error": reason, "reversible": False, "message": reason}

    def _current_identity(self, identity: ProcessIdentity) -> ProcessIdentity:
        if psutil is None:
            raise RuntimeError("psutil is required for process identity validation")
        process = psutil.Process(identity.pid)
        if not identity.matches_process(process):
            raise RuntimeError("Process identity mismatch")
        return ProcessIdentity.from_process(process)

    def _is_critical(self, identity: ProcessIdentity, process: Dict[str, Any]) -> bool:
        if identity in self.protected_identities:
            return True
        if identity.pid == os.getpid():
            return True
        if identity.pid in (0, 1):
            return True
        if process.get("process_category") == "system":
            return True
        if process.get("is_guardian") or process.get("guardian_process"):
            return True
        return False

    def _validate(self, identity: ProcessIdentity, action: str, process: Dict[str, Any],
                  confidence: float) -> Optional[Dict[str, Any]]:
        if not isinstance(identity.pid, int) or identity.pid <= 0:
            return self._reject(identity, action, "Invalid process identifier", "InvalidPID")
        if not self.adapter.capabilities().get("available"):
            return self._reject(identity, action, "Control adapter is unavailable", "UnsupportedPlatform")
        try:
            self._current_identity(identity)
        except Exception as error:
            return self._reject(identity, action, str(error), type(error).__name__)
        if self._is_critical(identity, process):
            return self._reject(identity, action, "Critical or protected process", "CriticalProcess")
        if process.get("is_foreground") or float(process.get("user_disruption_score", 0.0) or 0.0) >= 0.70:
            return self._reject(identity, action, "Foreground or high-disruption process", "ForegroundProcess")
        if confidence < self.limits.minimum_confidence:
            return self._reject(identity, action, "Safety confidence is below configured minimum", "LowConfidence")
        if len(self.registry.active) >= self.limits.max_simultaneous_interventions:
            return self._reject(identity, action, "Maximum simultaneous interventions reached", "InterventionLimit")
        if self.registry.failure_count(identity) >= self.limits.max_repeated_failures:
            return self._reject(identity, action, "Repeated intervention failures exceeded limit", "RepeatedFailureLimit")
        existing = self.registry.get(identity)
        if existing:
            return self._reject(identity, action, "Process already has an active intervention", "AlreadyActive")
        for completed in reversed(self.registry.completed):
            if completed.process_identity == identity and time.monotonic() - completed.start_time < self.limits.cooldown_seconds:
                return self._reject(identity, action, "Intervention cooldown is active", "Cooldown")
        if action not in {"LOWER_PRIORITY", "CLAMP_AFFINITY", "SUSPEND"}:
            return self._reject(identity, action, "Action is unsupported by the safety governor", "UnsupportedAction")
        if action == "CLAMP_AFFINITY" and hasattr(self.adapter, "affinity_reduction"):
            reduction = self.adapter.affinity_reduction(identity, [0])
            if reduction is not None and reduction > self.limits.max_cpu_reduction:
                return self._reject(identity, action, "Configured maximum CPU reduction exceeded", "CpuReductionLimit")
        return None

    def apply(self, identity: ProcessIdentity, action: str, process: Dict[str, Any],
              telemetry_before: Dict[str, Any], reason: str, expected_benefit: Dict[str, Any],
              confidence: float, resource_domain: str = "UNKNOWN") -> Dict[str, Any]:
        lifecycle = InterventionState(
            intervention_id=str(uuid.uuid4()), process_identity=identity,
            resource_domain=resource_domain, selected_action=action,
            start_time=time.time(), current_state="DETECTED",
            telemetry_before=telemetry_before,
            expected_relief=expected_benefit.get("expected_relief"),
        )
        lifecycle.transition("PROPOSED")
        lifecycle.transition("BID_SELECTED")
        rejection = self._validate(identity, action, process, confidence)
        if rejection:
            lifecycle.failure_reason = rejection.get("error")
            lifecycle.safety_decision = rejection
            lifecycle.transition("REJECTED")
            rejection["lifecycle"] = lifecycle.to_dict()
            return rejection
        lifecycle.safety_decision = {"status": "approved", "confidence": confidence}
        lifecycle.transition("SAFETY_CHECKED")
        methods = {
            "LOWER_PRIORITY": lambda: self.adapter.lower_priority(identity),
            "CLAMP_AFFINITY": lambda: self.adapter.clamp_affinity(identity, [0]),
            "SUSPEND": lambda: self.adapter.suspend(identity),
        }
        result: ControlResult = methods[action]()
        payload = result.to_dict()
        if not result.success:
            self.registry.record_failure(identity)
            lifecycle.failure_reason = result.error
            lifecycle.execution_result = payload
            lifecycle.transition("FAILED")
            payload["lifecycle"] = lifecycle.to_dict()
            return payload
        lifecycle.execution_result = payload
        lifecycle.transition("APPLIED")
        now = time.monotonic()
        intervention = Intervention(
            process_identity=identity, action=action, start_time=now,
            original_state=result.restoration_token or {}, applied_state={"action": action},
            reason=reason, telemetry_before=telemetry_before,
            expected_benefit=expected_benefit,
            expires_at=now + self.limits.max_duration_seconds,
            restoration_token=result.restoration_token,
            lifecycle=lifecycle,
        )
        self.registry.add(intervention)
        payload["intervention_status"] = "active"
        payload["expires_at"] = intervention.expires_at
        payload["lifecycle"] = lifecycle.to_dict()
        return payload

    def monitor(self, identity: ProcessIdentity, telemetry_after: Dict[str, Any],
                recovery_threshold: Optional[float] = None) -> Dict[str, Any]:
        intervention = self.registry.get(identity)
        if not intervention or not intervention.lifecycle:
            return {"status": "error", "error_type": "UnknownIntervention",
                    "message": "No active lifecycle for process identity."}
        lifecycle = intervention.lifecycle
        if lifecycle.current_state == "APPLIED":
            lifecycle.transition("MONITORED")
        elif lifecycle.current_state != "MONITORED":
            raise ValueError(f"Cannot monitor lifecycle in state {lifecycle.current_state}")
        before = intervention.telemetry_before.get("resource_state", {})
        after = telemetry_after.get("resource_state", {})
        before_pressure = before.get("overall_pressure")
        after_pressure = after.get("overall_pressure")
        if before_pressure is not None and after_pressure is not None:
            lifecycle.actual_relief = max(0.0, float(before_pressure) - float(after_pressure))
        lifecycle.telemetry_after = telemetry_after
        threshold = self.limits.recovery_threshold if recovery_threshold is None else recovery_threshold
        if after_pressure is not None and float(after_pressure) <= threshold:
            lifecycle.recovery_samples += 1
        else:
            lifecycle.recovery_samples = 0
        recovered = lifecycle.recovery_samples >= self.limits.recovery_consecutive_samples
        if recovered:
            lifecycle.transition("RECOVERED")
        return {"status": "success", "recovered": recovered,
                "actual_relief": lifecycle.actual_relief,
                "recovery_samples": lifecycle.recovery_samples,
                "lifecycle": lifecycle.to_dict()}

    def restore(self, identity: ProcessIdentity) -> Dict[str, Any]:
        intervention = self.registry.get(identity)
        if not intervention:
            return {"status": "skipped", "success": True, "action": "RESTORE",
                    "process_identity": identity.to_dict(), "message": "Already restored or no active intervention"}
        token = intervention.restoration_token or {}
        lifecycle = intervention.lifecycle
        if lifecycle:
            if lifecycle.current_state == "APPLIED":
                lifecycle.transition("MONITORED")
                lifecycle.transition("RECOVERED")
            elif lifecycle.current_state == "MONITORED":
                lifecycle.transition("RECOVERED")
            elif lifecycle.current_state == "EXPIRED":
                pass
            elif lifecycle.current_state != "RECOVERED":
                raise ValueError(f"Cannot restore lifecycle in state {lifecycle.current_state}")
        results = []
        if intervention.action == "LOWER_PRIORITY" and "priority" in token:
            results.append(self.adapter.restore_priority(identity, token).to_dict())
        elif intervention.action == "CLAMP_AFFINITY" and "affinity" in token:
            results.append(self.adapter.restore_affinity(identity, token).to_dict())
        elif intervention.action == "SUSPEND" and token.get("suspended"):
            results.append(self.adapter.resume(identity).to_dict())
        success = bool(results) and all(item.get("success") for item in results)
        result = {"status": "success" if success else "error", "success": success,
                  "action": "RESTORE", "process_identity": identity.to_dict(),
                  "restored_action": intervention.action,
                  "restoration_success": success, "results": results,
                  "message": "Original state restored and adapter reported success." if success
                  else "Restoration failed or could not be verified."}
        self.registry.finish(identity, "restored" if success else "restoration_failure", result)
        if lifecycle:
            lifecycle.restoration_result = result
            lifecycle.duration = max(0.0, time.time() - lifecycle.start_time)
            if success:
                lifecycle.transition("RESTORED")
                lifecycle.transition("VERIFIED")
                lifecycle.transition("RECORDED")
            else:
                lifecycle.failure_reason = result["message"]
                lifecycle.transition("RESTORATION_FAILED")
            result["lifecycle"] = lifecycle.to_dict()
        if not success:
            self.registry.record_failure(identity)
        return result

    def restore_expired(self) -> list[Dict[str, Any]]:
        expired = [identity for identity, item in self.registry.active.items()
                   if time.monotonic() >= item.expires_at]
        for identity in expired:
            intervention = self.registry.get(identity)
            if intervention and intervention.lifecycle and intervention.lifecycle.current_state == "APPLIED":
                intervention.lifecycle.transition("EXPIRED")
        return [self.restore(identity) for identity in expired]

    def restore_normalized(self, overall_pressure: Optional[float]) -> list[Dict[str, Any]]:
        if overall_pressure is None or overall_pressure >= 0.50:
            return []
        return [self.restore(identity) for identity, intervention in list(self.registry.active.items())
                if intervention.lifecycle and intervention.lifecycle.current_state == "RECOVERED"]

    def monitor_active(self, telemetry: Dict[str, Any]) -> list[Dict[str, Any]]:
        results = []
        for identity, intervention in list(self.registry.active.items()):
            if intervention.lifecycle and intervention.lifecycle.current_state in {"APPLIED", "MONITORED"}:
                results.append(self.monitor(identity, telemetry))
        return results
