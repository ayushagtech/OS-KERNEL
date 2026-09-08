from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class IOAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="File System (I/O) Agent", domain="Disk & Queue Latency")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        io_data = telemetry.get("io", {})
        io_pressure = io_data.get("pressure")
        io_busy = io_pressure is not None and io_pressure >= 0.60
        processes = telemetry.get("processes", [])

        if io_busy:
            # Find processes with high I/O activity
            for proc in processes[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                if proc.get("is_background", True) and not proc.get("is_foreground"):
                    process_load = min(100.0, (proc.get("cpu_percent", 0) or 0) +
                                       (proc.get("memory_percent", 0) or 0) * 2.0)
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        resource_relief=45.0 + 0.25 * process_load,
                        stability_improvement=55.0 + 0.15 * process_load,
                        security_confidence=0.0,
                        reversibility=95.0,
                        user_disruption=self.process_user_disruption(proc, action_scale=0.45),
                        collateral_cost=self.process_collateral_cost(proc, "LOWER_PRIORITY"),
                        rationale=f"Disk queue pressure is reported; lower I/O scheduling priority for non-foreground task {name}."
                    ))

        return proposals
