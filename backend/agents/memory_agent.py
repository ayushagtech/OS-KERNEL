from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Memory Agent", domain="RAM & Page Management")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        ram_percent = telemetry.get("memory", {}).get("percent", 0) or 0.0
        resource_state = telemetry.get("resource_state", {})
        memory_pressure = resource_state.get("memory_pressure")
        swap_pressure = resource_state.get("swap_pressure") or 0.0
        if memory_pressure is None:
            memory_pressure = telemetry.get("memory", {}).get("pressure")
        if memory_pressure is None:
            memory_pressure = ram_percent / 100.0
        processes = telemetry.get("processes", [])
        prediction = telemetry.get("prediction", {})
        prediction_risk = prediction.get("risk", "LOW")
        prediction_confidence = float(prediction.get("confidence", 0.0) or 0.0)
        predictive_pressure = (
            prediction.get("resource") == "memory"
            and prediction_risk in {"HIGH", "CRITICAL"}
            and prediction_confidence > 0.0
        )

        if memory_pressure > 0.80 or swap_pressure > 0.50:
            pressure = min(100.0, max((memory_pressure - 0.80) * 500.0,
                                      (swap_pressure - 0.50) * 200.0))
            # Find high RAM consuming processes
            sorted_procs = sorted(processes, key=lambda p: p.get("memory_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                mem_pct = proc.get("memory_percent", 0)
                is_background = proc.get("is_background", True)

                if mem_pct > 10.0:
                    process_pressure = min(100.0, mem_pct * 5.0)
                    # Avoid pausing foreground work even when the platform lacks
                    # a reliable foreground-window signal.
                    if is_background and not proc.get("is_foreground"):
                        proposals.append(Proposal(
                            agent_name=self.name,
                            target_pid=pid,
                            process_name=name,
                            action="SUSPEND",
                            resource_relief=0.70 * pressure + 0.30 * process_pressure,
                            stability_improvement=0.65 * pressure + 0.25 * process_pressure,
                            security_confidence=0.0,
                            reversibility=70.0,
                            user_disruption=self.process_user_disruption(proc),
                            collateral_cost=self.process_collateral_cost(proc, "SUSPEND"),
                            rationale=f"RAM pressure is {ram_percent:.1f}%; temporarily suspend non-foreground task {name} (PID {pid})."
                        ))

        # Preventive path: pressure is predicted to approach, but RAM has not
        # reached the existing reactive threshold. These are heuristic bids
        # based on daemon telemetry, not ML predictions or direct actions.
        if predictive_pressure and ram_percent <= 80.0:
            severity = {"HIGH": 70.0, "CRITICAL": 90.0}[prediction_risk] * prediction_confidence
            horizon = prediction.get("seconds_to_threshold")
            horizon_text = "no precise horizon" if horizon is None else f"~{horizon:.0f}s to threshold"
            sorted_procs = sorted(processes, key=lambda p: p.get("memory_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                mem_pct = proc.get("memory_percent", 0)
                if mem_pct <= 5.0:
                    continue
                process_pressure = min(100.0, mem_pct * 5.0)
                # Scheduling adjustment is preferred before stronger memory
                # intervention, and foreground work retains its high cost.
                proposals.append(Proposal(
                    agent_name=self.name,
                    target_pid=pid,
                    process_name=name,
                    action="LOWER_PRIORITY",
                    resource_relief=0.45 * severity + 0.30 * process_pressure,
                    stability_improvement=0.55 * severity + 0.20 * process_pressure,
                    security_confidence=0.0,
                    reversibility=95.0,
                    user_disruption=self.process_user_disruption(proc, action_scale=0.35),
                    collateral_cost=self.process_collateral_cost(proc, "LOWER_PRIORITY"),
                    rationale=(f"Preventive action: memory pressure is predicted {prediction_risk} "
                               f"(confidence {prediction_confidence:.2f}, {horizon_text}); lower priority for {name} "
                               f"(PID {pid}) before RAM reaches the reactive threshold.")
                ))
        return proposals
