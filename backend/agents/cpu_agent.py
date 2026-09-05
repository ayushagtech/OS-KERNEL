from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class CPUAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="CPU Agent", domain="CPU Scheduling & Priority")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        cpu_percent = telemetry.get("cpu", {}).get("total_percent", 0)
        processes = telemetry.get("processes", [])

        if cpu_percent > 75.0:
            # Find high CPU processes
            sorted_procs = sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                cpu_pct = proc.get("cpu_percent", 0)
                is_background = proc.get("is_background", True)

                if cpu_pct > 20.0:
                    # Proposal 1: Lower priority (nice +10)
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        health_gain=30.0,
                        disruption_cost=10.0,
                        rationale=f"CPU at {cpu_percent:.1f}%. Shift {name} (PID {pid}) to lower priority class."
                    ))

                    # Proposal 2: Clamp CPU Affinity
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="CLAMP_AFFINITY",
                        health_gain=35.0,
                        disruption_cost=15.0,
                        rationale=f"CPU load spike ({cpu_pct:.1f}%). Restrict {name} (PID {pid}) to 1 core."
                    ))

                    # Proposal 3: Suspend if heavy background load
                    if is_background and cpu_pct > 50.0:
                        proposals.append(Proposal(
                            agent_name=self.name,
                            target_pid=pid,
                            process_name=name,
                            action="SUSPEND",
                            health_gain=55.0,
                            disruption_cost=20.0,
                            rationale=f"Rogue CPU load ({cpu_pct:.1f}%) in background process {name}. Suspend execution."
                        ))

        return proposals
