from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class NetworkAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Network Agent", domain="Socket & Traffic Control")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        net_high = telemetry.get("network", {}).get("is_high", False)
        processes = telemetry.get("processes", [])

        if net_high:
            for proc in processes[:3]:
                if proc.get("is_background", True):
                    pid = proc.get("pid")
                    name = proc.get("name", "Unknown")
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        health_gain=15.0,
                        disruption_cost=5.0,
                        rationale=f"Network bandwidth saturation. Throttle background socket buffers for {name}."
                    ))

        return proposals
