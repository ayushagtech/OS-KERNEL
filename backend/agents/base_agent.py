from typing import Dict, Any, List, Optional
import time

class Proposal:
    """A telemetry-derived estimate, not a machine-learned prediction.

    All factor values use a 0--100 scale.  The weights intentionally favor
    measurable resource/stability relief while retaining meaningful penalties
    for user impact and unintended side effects.
    """

    # Utility = 0.28R + 0.22S + 0.18Q + 0.12V - 0.12U - 0.08C.
    # R=resource relief, S=stability improvement, Q=security confidence,
    # V=reversibility, U=user disruption, C=collateral cost.
    UTILITY_WEIGHTS = {
        "resource_relief": 0.28,
        "stability_improvement": 0.22,
        "security_confidence": 0.18,
        "reversibility": 0.12,
        "user_disruption": 0.12,
        "collateral_cost": 0.08,
    }

    def __init__(self, agent_name: str, target_pid: int, process_name: str, action: str,
                 health_gain: Optional[float] = None, disruption_cost: Optional[float] = None,
                 rationale: str = "", resource_relief: float = 0.0,
                 stability_improvement: float = 0.0, security_confidence: float = 0.0,
                 reversibility: float = 0.0, user_disruption: float = 0.0,
                 collateral_cost: float = 0.0):
        self.agent_name = agent_name
        self.target_pid = target_pid
        self.process_name = process_name
        self.action = action  # e.g., SUSPEND, LOWER_PRIORITY, CLAMP_AFFINITY
        self.resource_relief = self._normalize(resource_relief)
        self.stability_improvement = self._normalize(stability_improvement)
        self.security_confidence = self._normalize(security_confidence)
        self.reversibility = self._normalize(reversibility)
        self.user_disruption = self._normalize(user_disruption)
        self.collateral_cost = self._normalize(collateral_cost)
        weights = self.UTILITY_WEIGHTS
        self.net_utility = (
            weights["resource_relief"] * self.resource_relief
            + weights["stability_improvement"] * self.stability_improvement
            + weights["security_confidence"] * self.security_confidence
            + weights["reversibility"] * self.reversibility
            - weights["user_disruption"] * self.user_disruption
            - weights["collateral_cost"] * self.collateral_cost
        )
        # Legacy consumers still receive these fields, but they are derived
        # summaries rather than independently chosen fixed scores.
        positive_weight = sum(weights[key] for key in (
            "resource_relief", "stability_improvement", "security_confidence", "reversibility"
        ))
        negative_weight = weights["user_disruption"] + weights["collateral_cost"]
        self.health_gain = self._normalize((
            weights["resource_relief"] * self.resource_relief
            + weights["stability_improvement"] * self.stability_improvement
            + weights["security_confidence"] * self.security_confidence
            + weights["reversibility"] * self.reversibility
        ) / positive_weight) if health_gain is None else self._normalize(health_gain)
        self.disruption_cost = self._normalize((
            weights["user_disruption"] * self.user_disruption
            + weights["collateral_cost"] * self.collateral_cost
        ) / negative_weight) if disruption_cost is None else self._normalize(disruption_cost)
        self.rationale = rationale
        self.timestamp = time.time()

    @staticmethod
    def _normalize(value: float) -> float:
        return max(0.0, min(100.0, float(value or 0.0)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "target_pid": self.target_pid,
            "process_name": self.process_name,
            "action": self.action,
            "health_gain": self.health_gain,
            "disruption_cost": self.disruption_cost,
            "resource_relief": self.resource_relief,
            "stability_improvement": self.stability_improvement,
            "security_confidence": self.security_confidence,
            "reversibility": self.reversibility,
            "user_disruption": self.user_disruption,
            "collateral_cost": self.collateral_cost,
            "net_utility": round(self.net_utility, 2),
            "rationale": self.rationale,
            "timestamp": self.timestamp
        }

class BaseAgent:
    def __init__(self, name: str, domain: str):
        self.name = name
        self.domain = domain

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        """Override in subclass to analyze telemetry and generate proposals."""
        raise NotImplementedError

    @staticmethod
    def process_user_disruption(process: Dict[str, Any], action_scale: float = 1.0) -> float:
        """Use daemon context when available, with a conservative fallback."""
        score = process.get("user_disruption_score")
        if score is None:
            score = 1.0 if process.get("is_foreground") else (0.2 if process.get("is_background") else 0.5)
        return max(0.0, min(100.0, float(score) * 100.0 * action_scale))

    @staticmethod
    def process_collateral_cost(process: Dict[str, Any], action: str) -> float:
        """Estimate side effects from action strength and protected categories."""
        action_cost = {"LOWER_PRIORITY": 20.0, "CLAMP_AFFINITY": 35.0,
                   "SUSPEND": 55.0}.get(action, 30.0)
        category_cost = {"system": 40.0, "foreground_app": 20.0,
                         "development_tool": 10.0, "browser": 8.0}.get(
                             process.get("process_category"), 0.0)
        return min(100.0, action_cost + category_cost)
