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

            signature_match = any(kw in name for kw in suspicious_keywords)
            category_match = proc.get("process_category") == "suspicious"
            reported_suspicion = proc.get("security_suspicion", 0)
            is_suspicious = signature_match or category_match or reported_suspicion >= 0.7

            if is_suspicious:
                # Signature/category evidence determines confidence.  High CPU
                # alone is deliberately not treated as malicious behavior.
                suspicion = max(
                    90.0 if signature_match else 0.0,
                    75.0 if category_match else 0.0,
                    min(100.0, float(reported_suspicion or 0) * 100.0),
                )
                process_load = min(100.0, cpu_pct + mem_pct * 2.0)
                proposals.append(Proposal(
                    agent_name=self.name,
                    target_pid=pid,
                    process_name=proc.get("name"),
                    action="SUSPEND",
                    resource_relief=0.50 * process_load,
                    stability_improvement=25.0 + 0.35 * process_load,
                    security_confidence=suspicion,
                    reversibility=70.0,
                    user_disruption=self.process_user_disruption(proc),
                    collateral_cost=self.process_collateral_cost(proc, "SUSPEND"),
                    rationale=f"Suspicion evidence for {proc.get('name')} is {suspicion:.0f}/100; suspend reversibly for review (CPU {cpu_pct:.1f}%, RAM {mem_pct:.1f}%)."
                ))

        return proposals
