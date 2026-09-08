from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class NetworkAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Network Agent", domain="Socket & Traffic Control")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        network_data = telemetry.get("network", {})
        network_pressure = network_data.get("pressure")
        net_high = network_pressure is not None and network_pressure >= 0.60
        processes = telemetry.get("processes", [])

        if net_high:
            for proc in processes[:3]:
                if proc.get("is_background", True) and not proc.get("is_foreground"):
                    pid = proc.get("pid")
                    name = proc.get("name", "Unknown")
                    process_load = min(100.0, (proc.get("cpu_percent", 0) or 0) +
                                       (proc.get("memory_percent", 0) or 0) * 2.0)
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        resource_relief=40.0 + 0.20 * process_load,
                        stability_improvement=50.0 + 0.15 * process_load,
                        security_confidence=0.0,
                        reversibility=95.0,
                        user_disruption=self.process_user_disruption(proc, action_scale=0.40),
                        collateral_cost=self.process_collateral_cost(proc, "LOWER_PRIORITY"),
                        rationale=f"Network saturation is reported; reduce scheduling priority for non-foreground task {name}."
                    ))

        return proposals
