from typing import Dict, Any, List, Optional
import logging
from backend.agents.base_agent import Proposal
from backend.hooks.process_control import ProcessControlHooks

logger = logging.getLogger("DecisionArbiter")

class DecisionArbiterAgent:
    """
    Decision Arbiter Agent - The Patentable Consensus Core.
    Evaluates bids from domain agents using the closed-loop Utility Function:
    Utility = ΔSystem Health - ΔUser Disruption
    Selects and executes the least disruptive, highest utility mitigation.
    """
    def __init__(self):
        self.name = "Decision Arbiter Agent"

    def arbitrate(self, proposals: List[Proposal], telemetry: Dict[str, Any]) -> Dict[str, Any]:
        if not proposals:
            return {
                "decision_made": False,
                "reason": "No anomalies or agent proposals active.",
                "winning_proposal": None,
                "all_proposals": []
            }

        # Filter out negative utility proposals
        valid_proposals = [p for p in proposals if p.net_utility > 0]

        if not valid_proposals:
            return {
                "decision_made": False,
                "reason": "All proposals resulted in negative net utility.",
                "winning_proposal": None,
                "all_proposals": [p.to_dict() for p in proposals]
            }

        # Rank proposals by net utility descending
        sorted_proposals = sorted(valid_proposals, key=lambda p: p.net_utility, reverse=True)
        winner = sorted_proposals[0]

        # Execute non-destructive control hook based on winner's action
        execution_result = {}
        action = winner.action
        pid = winner.target_pid

        if action == "SUSPEND":
            execution_result = ProcessControlHooks.suspend_process(pid)
        elif action == "RESUME":
            execution_result = ProcessControlHooks.resume_process(pid)
        elif action == "LOWER_PRIORITY":
            execution_result = ProcessControlHooks.lower_priority(pid)
        elif action == "CLAMP_AFFINITY":
            execution_result = ProcessControlHooks.clamp_affinity(pid, [0])
        elif action == "ZRAM_COMPRESS":
            execution_result = ProcessControlHooks.simulate_memory_compression(pid)
        else:
            execution_result = {"status": "skipped", "message": f"Unknown action {action}"}

        logger.info(f"[ARBITER CONSENSUS] Executed {action} on PID={pid} ({winner.process_name}). Net Utility: {winner.net_utility}")

        return {
            "decision_made": True,
            "winning_proposal": winner.to_dict(),
            "execution_result": execution_result,
            "all_proposals": [p.to_dict() for p in proposals]
        }
