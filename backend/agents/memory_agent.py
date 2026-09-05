from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Memory Agent", domain="RAM & Page Management")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        ram_percent = telemetry.get("memory", {}).get("percent", 0)
        processes = telemetry.get("processes", [])

        if ram_percent > 80.0:
            # Find high RAM consuming processes
            sorted_procs = sorted(processes, key=lambda p: p.get("memory_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                mem_pct = proc.get("memory_percent", 0)
                is_background = proc.get("is_background", True)

                if mem_pct > 10.0:
                    # Proposal 1: zRAM memory compression
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="ZRAM_COMPRESS",
                        health_gain=25.0,
                        disruption_cost=5.0,
                        rationale=f"RAM at {ram_percent:.1f}%. Compress cold memory pages for {name} (PID {pid})."
                    ))

                    # Proposal 2: Background process freeze if background process
                    if is_background:
                        proposals.append(Proposal(
                            agent_name=self.name,
                            target_pid=pid,
                            process_name=name,
                            action="SUSPEND",
                            health_gain=45.0,
                            disruption_cost=15.0,
                            rationale=f"RAM at {ram_percent:.1f}%. Temporarily suspend background task {name} (PID {pid})."
                        ))

        return proposals
