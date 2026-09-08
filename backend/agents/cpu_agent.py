from typing import Dict, Any, List
from backend.agents.base_agent import BaseAgent, Proposal

class CPUAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="CPU Agent", domain="CPU Scheduling & Priority")

    def evaluate(self, telemetry: Dict[str, Any]) -> List[Proposal]:
        proposals = []
        cpu_percent = telemetry.get("cpu", {}).get("total_percent", 0) or 0.0
        resource_state = telemetry.get("resource_state", {})
        cpu_pressure = resource_state.get("cpu_pressure")
        if cpu_pressure is None:
            cpu_pressure = telemetry.get("cpu", {}).get("pressure")
        if cpu_pressure is None:
            cpu_pressure = cpu_percent / 100.0
        processes = telemetry.get("processes", [])
        prediction = telemetry.get("prediction", {})
        prediction_risk = prediction.get("risk", "LOW")
        prediction_confidence = float(prediction.get("confidence", 0.0) or 0.0)
        predictive_pressure = (
            prediction.get("resource") == "memory"
            and prediction_risk in {"HIGH", "CRITICAL"}
            and prediction_confidence > 0.0
        )

        if cpu_pressure > 0.75:
            system_pressure = min(100.0, (cpu_pressure - 0.75) * 400.0)
            # Find high CPU processes
            sorted_procs = sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                cpu_pct = proc.get("cpu_percent", 0)
                is_background = proc.get("is_background", True)

                if cpu_pct > 20.0:
                    process_pressure = min(100.0, cpu_pct)
                    # Proposal 1: Lower priority (nice +10)
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="LOWER_PRIORITY",
                        resource_relief=0.55 * system_pressure + 0.45 * process_pressure,
                        stability_improvement=0.65 * system_pressure + 0.25 * process_pressure,
                        security_confidence=0.0,
                        reversibility=95.0,
                        user_disruption=self.process_user_disruption(proc, action_scale=0.45),
                        collateral_cost=self.process_collateral_cost(proc, "LOWER_PRIORITY"),
                        rationale=f"CPU pressure is {cpu_percent:.1f}%; lower scheduling priority for {name} (PID {pid})."
                    ))

                    # Proposal 2: Clamp CPU Affinity
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="CLAMP_AFFINITY",
                        resource_relief=0.50 * system_pressure + 0.50 * process_pressure,
                        stability_improvement=0.60 * system_pressure + 0.30 * process_pressure,
                        security_confidence=0.0,
                        reversibility=80.0,
                        user_disruption=self.process_user_disruption(proc, action_scale=0.70),
                        collateral_cost=self.process_collateral_cost(proc, "CLAMP_AFFINITY"),
                        rationale=f"CPU pressure is {cpu_percent:.1f}% ({name} uses {cpu_pct:.1f}%); constrain its CPU affinity."
                    ))

                    # Proposal 3: Suspend if heavy background load
                    if is_background and not proc.get("is_foreground") and cpu_pct > 50.0:
                        proposals.append(Proposal(
                            agent_name=self.name,
                            target_pid=pid,
                            process_name=name,
                            action="SUSPEND",
                            resource_relief=0.40 * system_pressure + 0.60 * process_pressure,
                            stability_improvement=0.55 * system_pressure + 0.35 * process_pressure,
                            security_confidence=0.0,
                            reversibility=70.0,
                            user_disruption=self.process_user_disruption(proc),
                            collateral_cost=self.process_collateral_cost(proc, "SUSPEND"),
                            rationale=f"Sustained non-foreground CPU load ({cpu_pct:.1f}%) from {name}; suspend as a reversible last resort."
                        ))

        # Preventive path: reduce competing CPU scheduling load while the
        # daemon predicts memory-resource pressure, before CPU is reactive.
        if predictive_pressure and cpu_percent <= 75.0:
            severity = {"HIGH": 70.0, "CRITICAL": 90.0}[prediction_risk] * prediction_confidence
            horizon = prediction.get("seconds_to_threshold")
            horizon_text = "no precise horizon" if horizon is None else f"~{horizon:.0f}s to threshold"
            sorted_procs = sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)
            for proc in sorted_procs[:3]:
                pid = proc.get("pid")
                name = proc.get("name", "Unknown")
                cpu_pct = proc.get("cpu_percent", 0)
                if cpu_pct <= 10.0:
                    continue
                process_pressure = min(100.0, cpu_pct)
                proposals.append(Proposal(
                    agent_name=self.name,
                    target_pid=pid,
                    process_name=name,
                    action="LOWER_PRIORITY",
                    resource_relief=0.40 * severity + 0.35 * process_pressure,
                    stability_improvement=0.50 * severity + 0.25 * process_pressure,
                    security_confidence=0.0,
                    reversibility=95.0,
                    user_disruption=self.process_user_disruption(proc, action_scale=0.35),
                    collateral_cost=self.process_collateral_cost(proc, "LOWER_PRIORITY"),
                    rationale=(f"Preventive action: predicted {prediction_risk} memory-resource pressure "
                               f"(confidence {prediction_confidence:.2f}, {horizon_text}); lower scheduling priority "
                               f"for {name} (PID {pid}) before CPU becomes reactive.")
                ))
                # Affinity is only a high-confidence critical preventive bid,
                # never an automatic action, and excludes foreground work.
                if (prediction_risk == "CRITICAL" and prediction_confidence >= 0.75
                        and proc.get("is_background", True) and not proc.get("is_foreground")):
                    proposals.append(Proposal(
                        agent_name=self.name,
                        target_pid=pid,
                        process_name=name,
                        action="CLAMP_AFFINITY",
                        resource_relief=0.45 * severity + 0.40 * process_pressure,
                        stability_improvement=0.55 * severity + 0.25 * process_pressure,
                        security_confidence=0.0,
                        reversibility=80.0,
                        user_disruption=self.process_user_disruption(proc, action_scale=0.65),
                        collateral_cost=self.process_collateral_cost(proc, "CLAMP_AFFINITY"),
                        rationale=(f"Preventive action: high-confidence CRITICAL predicted memory-resource pressure "
                                   f"(confidence {prediction_confidence:.2f}, {horizon_text}); propose reversible CPU "
                                   f"affinity clamp for non-foreground task {name} (PID {pid}).")
                    ))

        return proposals
