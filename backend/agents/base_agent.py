from typing import Dict, Any, List, Optional
import time

class Proposal:
    def __init__(self, agent_name: str, target_pid: int, process_name: str, action: str, 
                 health_gain: float, disruption_cost: float, rationale: str):
        self.agent_name = agent_name
        self.target_pid = target_pid
        self.process_name = process_name
        self.action = action  # e.g., SUSPEND, LOWER_PRIORITY, ZRAM_COMPRESS, CLAMP_AFFINITY
        self.health_gain = health_gain  # Expected system health increase (0.0 to 100.0)
        self.disruption_cost = disruption_cost  # Expected user disruption penalty (0.0 to 100.0)
        self.net_utility = health_gain - disruption_cost
        self.rationale = rationale
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "target_pid": self.target_pid,
            "process_name": self.process_name,
            "action": self.action,
            "health_gain": self.health_gain,
            "disruption_cost": self.disruption_cost,
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
