from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Security Agent", domain="Process Authenticity & Threat Analysis")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        processes = telemetry.get("processes", [])

        suspicious_keywords = ["miner", "crypto", "stress", "leak", "rogue", "unknown_task"]

        for proc in processes:
            pid = proc.get("pid")
            name = proc.get("name", "").lower()
            cpu_pct = proc.get("cpu_percent", 0)
            mem_pct = proc.get("memory_percent", 0)

            is_suspicious = any(kw in name for kw in suspicious_keywords) or (cpu_pct > 60.0 and proc.get("is_background", True))

            if is_suspicious:
                proposals.append(Proposal(
                    agent_name=self.name,
                    target_pid=pid,
                    process_name=proc.get("name"),
                    action="SUSPEND",
                    health_gain=60.0,
                    disruption_cost=2.0, # Low disruption cost for suspicious background tasks!
                    rationale=f"Rogue signature/behavior detected in {proc.get('name')} (CPU {cpu_pct:.1f}%, RAM {mem_pct:.1f}%). Freeze task immediately."
                ))

        return proposals
