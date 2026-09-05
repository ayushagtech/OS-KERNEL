from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class IOAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="File System (I/O) Agent", domain="Disk & Queue Latency")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        io_busy = telemetry.get("io", {}).get("is_busy", False)
        processes = telemetry.get("processes", [])

        if io_busy:
            # Find processes with high I/O activity
            for proc in processes[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                if proc.get("is_background", True):
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        health_gain=20.0,
                        disruption_cost=5.0,
                        rationale=f"High Disk Queue Latency. Shift background I/O indexing for {name} to idle class."
                    ))

        return proposals
