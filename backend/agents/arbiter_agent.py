from typing import Dict, Any, List, Optional
from itertools import combinations
import logging
import time

from backend.agents.base_agent import Proposal
from backend.hooks.process_control import ProcessControlHooks
from backend.action_registry import MITIGATION_STAGES, is_executable
from backend.process_identity import ProcessIdentity
from backend.control_interface import create_control_adapter
from backend.safety_governor import SafetyGovernor
from backend.bidding import (CandidatePlan, ResourceBid, UtilityWeights,
                              build_candidate_plan, detect_conflicts)
from backend.adaptive_memory import (MAX_HISTORY_ADJUSTMENT,
                                      AdaptiveMitigationMemory,
                                      build_state_signature)

logger = logging.getLogger("DecisionArbiter")


class DecisionArbiterAgent:
    """Deterministic bargaining with a bounded, staged feedback controller."""

    COOLDOWN_SECONDS = 5.0
    OBSERVATION_DELAY_SECONDS = 0.15
    MAX_NEGOTIATION_ROUNDS = 3
    EXPERIENCE_HISTORY_LIMIT = 60
    STAGES = MITIGATION_STAGES
    ACTION_SAFETY_ORDER = {action: index for index, action in enumerate(STAGES)}

    def __init__(self, experience_path: Optional[str] = None):
        self.name = "Decision Arbiter Agent"
        self._pid_state: Dict[ProcessIdentity, Dict[str, Any]] = {}
        self._experience_history: List[Dict[str, Any]] = []
        self.safety_governor = SafetyGovernor(create_control_adapter())
        self.adaptive_memory = AdaptiveMitigationMemory(path=experience_path)

    @staticmethod
    def _process_context(telemetry: Dict[str, Any], pid: int) -> Dict[str, Any]:
        return next((process for process in telemetry.get("processes", [])
                     if process.get("pid") == pid), {})

    @staticmethod
    def _user_disruption(process: Dict[str, Any]) -> float:
        return float(process.get("user_disruption_score", 0.5) or 0.0)

    def _is_critical(self, telemetry: Dict[str, Any], proposals: List[Proposal]) -> bool:
        agents = {proposal.agent_name for proposal in proposals}
        return any((
            "CPU Agent" in agents and (telemetry.get("cpu", {}).get("total_percent", 0) or 0) >= 85.0,
            "Memory Agent" in agents and (telemetry.get("memory", {}).get("percent", 0) or 0) >= 90.0,
            "File System (I/O) Agent" in agents and bool(telemetry.get("io", {}).get("is_busy", False)),
            "Network Agent" in agents and bool(telemetry.get("network", {}).get("is_high", False)),
            "Security Agent" in agents,
        ))

    @staticmethod
    def _serializable_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in plan.items() if key != "proposals"}

    @staticmethod
    def _resource_pattern(telemetry: Dict[str, Any], proposals: List[Proposal]) -> str:
        """Create a compact, explainable resource-condition key."""
        parts = []
        memory_percent = float(telemetry.get("memory", {}).get("percent", 0) or 0)
        cpu_percent = float(telemetry.get("cpu", {}).get("total_percent", 0) or 0)
        prediction = telemetry.get("prediction", {})
        if memory_percent >= 90.0:
            parts.append("memory_critical")
        elif memory_percent >= 80.0:
            parts.append("memory_high")
        elif prediction.get("resource") == "memory" and prediction.get("risk") in {"HIGH", "CRITICAL"}:
            parts.append(f"memory_predicted_{str(prediction.get('risk')).lower()}")
        if cpu_percent >= 85.0:
            parts.append("cpu_critical")
        elif cpu_percent >= 75.0:
            parts.append("cpu_high")
        if not parts:
            agent_domains = sorted({proposal.agent_name.split()[0].lower() for proposal in proposals})
            parts.append("_".join(agent_domains) if agent_domains else "general_pressure")
        return "+".join(parts[:2])

    def _experience_adjustment(self, telemetry: Dict[str, Any], process: Dict[str, Any],
                               action: str) -> Dict[str, float]:
        stats = self.adaptive_memory.stats(build_state_signature(telemetry, process), action)
        selected = stats["selected"]
        return {"adjustment": float(stats["adjustment"]),
                "count": float(selected["count"]),
                "confidence": min(0.85, float(selected["count"]) / 10.0)}

    def _record_experience(self, telemetry: Dict[str, Any], process: Dict[str, Any], action: str,
                           baseline: Dict[str, Any], feedback: Dict[str, Any], proposals: List[Proposal],
                           recovery_time: float, escalation_required: bool,
                           execution: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        after = feedback.get("final_resource_state", {}).get("after", {})
        cpu_gain = max(0.0, baseline["cpu_percent"] - float(after.get("cpu_percent", baseline["cpu_percent"]) or 0))
        memory_gain = max(0.0, baseline["memory_percent"] - float(after.get("memory_percent", baseline["memory_percent"]) or 0))
        available_gain = max(0, int(after.get("available_bytes", baseline["available_bytes"]) or 0) - baseline["available_bytes"])
        relevant_gains = []
        agents = {proposal.agent_name for proposal in proposals}
        if "CPU Agent" in agents:
            relevant_gains.append(min(100.0, cpu_gain * 20.0))
        if "Memory Agent" in agents:
            relevant_gains.append(min(100.0, max(memory_gain * 100.0, available_gain / (64 * 1024 * 1024) * 100.0)))
        improvement_score = round(max(relevant_gains) if relevant_gains else 0.0, 2)
        execution = execution or {}
        signature = build_state_signature(telemetry, process)
        expected_relief = max((proposal.resource_relief for proposal in proposals), default=0.0) / 100.0
        adaptive_record = self.adaptive_memory.record(
            state_signature=signature,
            process_identity=process.get("process_identity"),
            action=action,
            telemetry_before=baseline,
            telemetry_after=after,
            expected_relief=expected_relief,
            actual_relief=improvement_score / 100.0,
            user_disruption=self._user_disruption(process),
            duration_seconds=recovery_time,
            restoration_result={"status": "pending", "restoration_success": False},
            escalation_required=escalation_required,
            failed=execution.get("status") != "success",
            safety_outcome={"status": execution.get("status"),
                            "error_type": execution.get("error_type")},
            collateral_cost=max((proposal.collateral_cost for proposal in proposals), default=0.0) / 100.0,
            stability_improvement=1.0 if feedback.get("improvement_observed") else 0.0,
        )
        observation = {
            **adaptive_record,
            "resource_pattern": self._resource_pattern(telemetry, proposals),
            "selected_action": action,
            "improvement_score": improvement_score,
            "resource_improvement": {"observed": feedback.get("improvement_observed", False),
                                     "cpu_delta_percent": round(cpu_gain, 2),
                                     "memory_delta_percent": round(memory_gain, 2),
                                     "available_bytes_delta": available_gain},
            "recovery_time_seconds": round(recovery_time, 3),
        }
        self._experience_history.append(observation)
        if len(self._experience_history) > self.EXPERIENCE_HISTORY_LIMIT:
            self._experience_history.pop(0)
        return observation

    def _learning_payload(self) -> Dict[str, Any]:
        preferred = self.adaptive_memory.action_summary()
        preferred.sort(key=lambda item: (-item["historical_adjustment"], -item["count"], item["action"]))
        return {"observations": len(self.adaptive_memory.records), "preferred_actions": preferred[:5],
                "confidence": round(min(0.85, len(self._experience_history) / 10.0), 2),
            "experience_count": len(self.adaptive_memory.records),
                "last_observation": self._experience_history[-1] if self._experience_history else None,
            "method": "bounded deterministic decayed outcome statistics",
            "effectiveness_formula": "0.45 relief + 0.20 stability + 0.15 restoration - 0.10 disruption - 0.05 collateral - 0.20 failure - 0.05 escalation"}

    def _action_candidates(self, pid: int, proposals: List[Proposal], telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run the existing bounded factor/agreement negotiation per action."""
        by_action: Dict[str, List[Proposal]] = {}
        for proposal in proposals:
            by_action.setdefault(proposal.action, []).append(proposal)
        candidates = []
        for action, action_proposals in by_action.items():
            count = len(action_proposals)
            domains = {proposal.agent_name for proposal in action_proposals}
            factors = {name: sum(getattr(proposal, name, 0.0) for proposal in action_proposals) / count
                       for name in Proposal.UTILITY_WEIGHTS}
            weights = Proposal.UTILITY_WEIGHTS
            score = (weights["resource_relief"] * factors["resource_relief"]
                     + weights["stability_improvement"] * factors["stability_improvement"]
                     + weights["security_confidence"] * factors["security_confidence"]
                     + weights["reversibility"] * factors["reversibility"]
                     - weights["user_disruption"] * factors["user_disruption"]
                     - weights["collateral_cost"] * factors["collateral_cost"])
            agreement = min(12.0, 4.0 * (count - 1))
            diversity = min(8.0, 2.0 * (len(domains) - 1))
            pattern = self._resource_pattern(telemetry, action_proposals)
            process = self._process_context(telemetry, pid)
            experience = self._experience_adjustment(telemetry, process, action)
            candidates.append({"pid": pid, "action": action, "proposals": action_proposals,
                               "factors": factors, "supporting_agents": sorted(domains),
                               "agreement_bonus": agreement, "domain_diversity_bonus": diversity,
                               "experience_adjustment": round(experience["adjustment"], 2),
                               "experience_count": int(experience["count"]),
                               "experience_confidence": round(experience["confidence"], 2),
                               "combined_score": score + agreement + diversity + experience["adjustment"],
                               "round_1_score": round(score, 2),
                               "round_2_score": round(score + agreement + diversity, 2)})
        candidates.sort(key=lambda item: (-item["combined_score"], -item["factors"]["reversibility"],
                                           item["factors"]["user_disruption"], item["factors"]["collateral_cost"],
                                           self.ACTION_SAFETY_ORDER.get(item["action"], 99)))
        if candidates:
            leading = candidates[0]["combined_score"]
            close = [item for item in candidates if leading - item["combined_score"] <= 5.0]
            close.sort(key=lambda item: (self.ACTION_SAFETY_ORDER.get(item["action"], 99),
                                          -item["factors"]["reversibility"], item["factors"]["user_disruption"],
                                          -item["combined_score"]))
            winner = close[0]
            winner["round_3_resolution"] = "close scores resolved toward safer reversible action"
            candidates = [winner] + [item for item in candidates if item is not winner]
        return candidates

    @staticmethod
    def _planning_confidence(plan: Dict[str, Any]) -> float:
        """Explainable confidence from agreement, reversibility, and evidence."""
        factors = plan["factors"]
        return min(1.0, 0.30 + 0.15 * len(plan["supporting_agents"])
                   + 0.30 * factors["security_confidence"] / 100.0
                   + 0.20 * factors["reversibility"] / 100.0)

    @staticmethod
    def _required_relief(telemetry: Dict[str, Any]) -> float:
        state = telemetry.get("resource_state", {})
        overall = state.get("overall_pressure")
        if overall is None:
            return 0.0
        return max(0.0, min(1.0, (float(overall) - 0.50) / 0.50))

    def _resource_bids(self, proposals: List[Proposal], telemetry: Dict[str, Any]) -> List[ResourceBid]:
        timestamp = float(telemetry.get("timestamp", time.time()))
        bids = []
        for proposal in proposals:
            process = self._process_context(telemetry, proposal.target_pid)
            bid = ResourceBid.from_proposal(proposal, process, timestamp)
            if bid.process_identity and is_executable(bid.target_action):
                bids.append(bid)
        return bids

    def _candidate_plans(self, bids: List[ResourceBid], telemetry: Dict[str, Any]) -> List[CandidatePlan]:
        required = self._required_relief(telemetry)
        def historical(bid: ResourceBid) -> float:
            process = self._process_context(telemetry, bid.process_identity.pid)
            return self.adaptive_memory.stats(
                build_state_signature(telemetry, process), bid.target_action
            )["adjustment"] / MAX_HISTORY_ADJUSTMENT if MAX_HISTORY_ADJUSTMENT else 0.0

        plans = [build_candidate_plan([bid], required, historical_adjustment=historical(bid),
                                      weights=UtilityWeights()) for bid in bids]
        for left, right in combinations(bids, 2):
            identities = {bid.process_identity for bid in (left, right) if bid.process_identity}
            if len(identities) != 2:
                continue
            if left.resource_domain == right.resource_domain:
                continue
            plans.append(build_candidate_plan(
                [left, right], required,
                historical_adjustment=(historical(left) + historical(right)) / 2.0,
                weights=UtilityWeights()))
        return plans

    @staticmethod
    def _select_candidate_plan(plans: List[CandidatePlan]) -> Optional[CandidatePlan]:
        sufficient = [plan for plan in plans if plan.sufficient]
        pool = sufficient or [plan for plan in plans if not plan.conflicts]
        if not pool:
            return None
        # Minimum disruption is the primary tie-breaker once relief is sufficient.
        return sorted(pool, key=lambda plan: (
            plan.user_disruption if plan.sufficient else 1.0,
            -plan.utility, len(plan.bids),
            tuple(bid.target_action for bid in plan.bids),
            tuple(bid.process_identity.pid for bid in plan.bids if bid.process_identity)
        ))[0]

    @staticmethod
    def _baseline(telemetry: Dict[str, Any], process: Dict[str, Any]) -> Dict[str, Any]:
        memory = telemetry.get("memory", {})
        cpu = telemetry.get("cpu", {})
        return {"cpu_percent": float(cpu.get("total_percent", 0) or 0),
                "memory_percent": float(memory.get("percent", 0) or 0),
                "memory_total_bytes": int(memory.get("total_bytes", 0) or 0),
                "memory_used_bytes": int(memory.get("used_bytes", 0) or 0),
                "memory_available_bytes": int(memory.get("available_bytes", 0) or 0),
                "available_bytes": int(memory.get("available_bytes", 0) or 0),
                "swap_percent": float(memory.get("swap_percent", 0) or 0),
                "process_cpu_percent": float(process.get("cpu_percent", 0) or 0),
                "process_memory_percent": float(process.get("memory_percent", 0) or 0)}

    def _choose_stage(self, plan: Dict[str, Any], telemetry: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Select one stage only; later stages require later feedback cycles."""
        process = self._process_context(telemetry, plan["pid"])
        protected = process.get("process_category") == "system"
        foreground = bool(process.get("is_foreground")) or self._user_disruption(process) >= 0.70
        confidence = self._planning_confidence(plan)
        expected_relief = plan["proposals"][0].resource_relief / 100.0
        resource_domain = {"CPU Agent": "CPU", "Memory Agent": "MEMORY",
                           "File System (I/O) Agent": "IO", "Network Agent": "NETWORK",
                           "Security Agent": "SECURITY"}.get(
                               plan["proposals"][0].agent_name, "UNKNOWN")
        critical = self._is_critical(telemetry, plan["proposals"])
        rejected = []
        if protected:
            return {"action": None, "reason": "System-critical process is protected from automatic control.",
                    "rejected": [{"stage": stage, "reason": "system-critical protection"} for stage in self.STAGES]}
        if foreground:
            return {"action": None, "reason": "Highly protected foreground/user-active process requires no automatic mitigation.",
                    "rejected": [{"stage": stage, "reason": "foreground user-disruption protection"} for stage in self.STAGES]}
        if confidence < 0.50:
            return {"action": None, "reason": "Proposal confidence is insufficient for automatic control.",
                    "rejected": [{"stage": stage, "reason": "insufficient confidence"} for stage in self.STAGES]}
        if state.get("improvement_observed"):
            return {"action": None, "reason": "Previous stage showed meaningful resource improvement.", "rejected": []}

        previous = state.get("last_action")
        if previous is None:
            action = "LOWER_PRIORITY"
            reason = "Stage 1 selected: begin with reversible lower-priority mitigation."
        elif previous == "LOWER_PRIORITY":
            if not critical:
                return {"action": None, "reason": "Current telemetry is no longer critical; cascade stopped.", "rejected": []}
            if confidence < 0.65:
                return {"action": None, "reason": "Stage 2 affinity clamp lacks sufficient confidence.",
                        "rejected": [{"stage": "CLAMP_AFFINITY", "reason": "confidence below 0.65"}]}
            action = "CLAMP_AFFINITY"
            reason = "Stage 1 did not improve critical pressure; Stage 2 affinity clamp is proposed."
        elif previous == "CLAMP_AFFINITY":
            strong_evidence = (plan["factors"]["security_confidence"] >= 70.0
                               or len(plan["supporting_agents"]) >= 2)
            if not critical or confidence < 0.80 or not strong_evidence:
                return {"action": None, "reason": "Stage 3 suspension is not justified by current pressure and evidence.",
                        "rejected": [{"stage": "SUSPEND", "reason": "critical pressure or strong evidence is insufficient"}]}
            action = "SUSPEND"
            reason = "Stages 1-2 did not improve critical pressure; Stage 3 suspension has strong evidence."
        else:
            return {"action": None, "reason": "All cascade stages are complete; awaiting restoration or new evidence.", "rejected": []}
        rejected.extend({"stage": stage, "reason": "feedback required before escalation"}
                        for stage in self.STAGES[self.STAGES.index(action) + 1:])
        return {"action": action, "reason": reason, "rejected": rejected}

    def _execute(self, pid: int, action: str, process_identity: ProcessIdentity,
                 process: Dict[str, Any], telemetry: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        confidence = self._planning_confidence(plan)
        if action == "LOWER_PRIORITY":
            return self.safety_governor.apply(
                process_identity, action, process, telemetry,
                plan["proposals"][0].rationale,
                {"combined_score": plan["combined_score"], "expected_relief": expected_relief},
                confidence, resource_domain)
        if action == "CLAMP_AFFINITY":
            return self.safety_governor.apply(
                process_identity, action, process, telemetry,
                plan["proposals"][0].rationale,
                {"combined_score": plan["combined_score"], "expected_relief": expected_relief},
                confidence, resource_domain)
        if action == "SUSPEND":
            return self.safety_governor.apply(
                process_identity, action, process, telemetry,
                plan["proposals"][0].rationale,
                {"combined_score": plan["combined_score"], "expected_relief": expected_relief},
                confidence, resource_domain)
        if action == "RESUME":
            return self.safety_governor.restore(process_identity)
        return {"status": "error", "pid": pid, "action": action,
                "error_type": "UnavailableAction", "message": "Action is not executable.",
                "process_identity": process_identity.to_dict()}

    def _feedback(self, baseline: Dict[str, Any], process_pid: int, proposals: List[Proposal]) -> Dict[str, Any]:
        """Bounded post-action observation; only measured improvement counts."""
        time.sleep(self.OBSERVATION_DELAY_SECONDS)
        process_identity = ProcessIdentity.from_mapping(baseline.get("process_identity"))
        system = ProcessControlHooks.observe_system()
        process = ProcessControlHooks.observe_process(process_pid, process_identity)
        if system.get("status") != "success":
            return {"improvement_observed": False, "reason": "Post-action system observation unavailable.",
                    "final_resource_state": {"before": baseline, "after": system}, "process_observation": process}
        after = {"cpu_percent": float(system.get("cpu_percent", 0) or 0),
                 "memory_percent": float(system.get("memory_percent", 0) or 0),
                 "memory_total_bytes": int(system.get("memory_total_bytes", 0) or 0),
                 "memory_used_bytes": int(system.get("memory_used_bytes", 0) or 0),
                 "memory_available_bytes": int(system.get("memory_available_bytes", 0) or 0),
                 "available_bytes": int(system.get("memory_available_bytes", 0) or 0),
                 "swap_percent": float(system.get("swap_percent", 0) or 0)}
        monitor_result = self.safety_governor.monitor(
            process_identity,
            {"resource_state": {"overall_pressure": min(
                1.0, ((after["cpu_percent"] / 100.0) + (after["memory_percent"] / 100.0)) / 2.0
            )}},
        ) if self.safety_governor.registry.get(process_identity) else None
        agents = {proposal.agent_name for proposal in proposals}
        improvements = []
        if "CPU Agent" in agents:
            improvements.append(baseline["cpu_percent"] - after["cpu_percent"] >= 5.0)
        if "Memory Agent" in agents:
            improvements.append(baseline["memory_percent"] - after["memory_percent"] >= 0.5
                                or after["available_bytes"] - baseline["available_bytes"] >= 64 * 1024 * 1024)
        observed = any(improvements)
        return {"improvement_observed": observed,
                "reason": "Meaningful relevant resource improvement observed." if observed else "No meaningful relevant resource improvement in bounded observation window.",
                "final_resource_state": {"before": baseline, "after": after,
                                         "process_after": process},
                "process_observation": process, "lifecycle": monitor_result}

    def _cascade_payload(self, state: Dict[str, Any], considered: List[str], rejected: List[Dict[str, str]],
                         reason: str, final_state: Dict[str, Any], improved: bool) -> Dict[str, Any]:
        return {"cascade_id": state.get("cascade_id"), "stages_considered": considered,
                "stages_executed": state.get("stages_executed", []), "stages_rejected": rejected,
                "escalation_reason": reason, "final_resource_state": final_state,
                "improvement_observed": improved, "reversible_state": state.get("restore_state", {})}

    def _response(self, *, decision: bool, reason: str, plan: Dict[str, Any], candidates: List[Dict[str, Any]],
                  proposals: List[Dict[str, Any]], rounds: List[Dict[str, Any]], conflicts: List[Dict[str, Any]],
                  execution: Dict[str, Any], actions: List[Dict[str, Any]], outcome: str,
                  cascade: Dict[str, Any]) -> Dict[str, Any]:
        return {"decision_made": decision, "reason": reason,
                "winning_proposal": plan["proposals"][0].to_dict(), "execution_result": execution,
                "all_proposals": proposals, "consensus_plan": self._serializable_plan(plan),
                "rejected_alternatives": [self._serializable_plan(item) for item in candidates if item is not plan],
                "negotiation_rounds": rounds, "cross_domain_conflicts": conflicts,
                "actions_executed": actions, "final_outcome": outcome,
                "learning": self._learning_payload(), **cascade}

    def arbitrate(self, proposals: List[Proposal], telemetry: Dict[str, Any]) -> Dict[str, Any]:
        self.safety_governor.monitor_active(telemetry)
        restored_results = self.safety_governor.restore_expired()
        restored_results += self.safety_governor.restore_normalized(
            telemetry.get("resource_state", {}).get("overall_pressure")
        )
        for restored in restored_results:
            identity = restored.get("process_identity")
            action = restored.get("restored_action", "")
            if identity and action:
                self.adaptive_memory.update_restoration(identity, action, restored)
        proposal_dicts = [proposal.to_dict() for proposal in proposals]
        resource_bids = self._resource_bids(proposals, telemetry)
        candidate_plans = self._candidate_plans(resource_bids, telemetry)
        selected_resource_plan = self._select_candidate_plan(candidate_plans)
        valid = [proposal for proposal in proposals
             if proposal.net_utility > 0 and is_executable(proposal.action)]
        if not valid:
            empty = {"cascade_id": None, "stages_considered": list(self.STAGES), "stages_executed": [],
                     "stages_rejected": [], "escalation_reason": "No positive-utility proposals.",
                     "final_resource_state": {}, "improvement_observed": False, "reversible_state": {}}
            return {"decision_made": False, "reason": "No positive-utility proposals active.", "winning_proposal": None,
                    "execution_result": {}, "all_proposals": proposal_dicts, "consensus_plan": None,
                    "rejected_alternatives": [], "negotiation_rounds": [], "cross_domain_conflicts": [],
                    "actions_executed": [], "final_outcome": "no_action", "learning": self._learning_payload(),
                    "resource_bids": [bid.to_dict() for bid in resource_bids],
                    "candidate_plans": [candidate.to_dict() for candidate in candidate_plans],
                    "selected_plan": selected_resource_plan.to_dict() if selected_resource_plan else None,
                    "barter": {"credits_offered": sum(bid.expected_relief for bid in resource_bids),
                                "relief_debt": self._required_relief(telemetry),
                                "conflicts": []}, **empty}

        by_pid: Dict[int, List[Proposal]] = {}
        for proposal in valid:
            by_pid.setdefault(proposal.target_pid, []).append(proposal)
        choices, rounds, conflicts = [], [], []
        for pid, pid_proposals in by_pid.items():
            candidates = self._action_candidates(pid, pid_proposals, telemetry)
            if not candidates:
                continue
            choices.append((candidates[0], candidates))
            actions = sorted({proposal.action for proposal in pid_proposals})
            if len(actions) > 1:
                conflicts.append({"pid": pid, "actions": actions,
                                  "agents": sorted({proposal.agent_name for proposal in pid_proposals})})
            rounds.append({"pid": pid, "rounds": self.MAX_NEGOTIATION_ROUNDS,
                           "candidates": [self._serializable_plan(item) for item in candidates]})
        choices.sort(key=lambda item: (-item[0]["combined_score"], item[0]["factors"]["user_disruption"],
                                       -item[0]["factors"]["reversibility"]))
        preferred_bid = None
        if selected_resource_plan:
            preferred_bid = selected_resource_plan.bids[0]
            matching = [item for item in choices
                        if item[0]["pid"] == preferred_bid.process_identity.pid
                        and item[0]["action"] == preferred_bid.target_action]
            if matching:
                plan, candidates = matching[0]
            else:
                plan, candidates = choices[0]
        else:
            plan, candidates = choices[0]
        now = time.time()
        process = self._process_context(telemetry, plan["pid"])
        process_identity = ProcessIdentity.from_mapping(process.get("process_identity"))
        if process_identity is None:
            reason = "Target process has no verified creation-time identity; action skipped."
            return self._response(decision=False, reason=reason, plan=plan, candidates=candidates,
                                  proposals=proposal_dicts, rounds=rounds, conflicts=conflicts,
                                  execution={"status": "error", "pid": plan["pid"],
                                             "error_type": "MissingProcessIdentity", "message": reason},
                                  actions=[], outcome="identity_unavailable",
                                  cascade=self._cascade_payload({}, list(self.STAGES), [], reason, {}, False))
        state = self._pid_state.get(process_identity, {})
        if now - state.get("last_modified", 0.0) < self.COOLDOWN_SECONDS:
            reason = "PID is in bounded feedback-controller cooldown before re-evaluation."
            cascade = self._cascade_payload(state, list(self.STAGES), [], reason,
                                             state.get("last_feedback", {}), state.get("improvement_observed", False))
            return self._response(decision=False, reason=reason, plan=plan, candidates=candidates,
                                  proposals=proposal_dicts, rounds=rounds, conflicts=conflicts,
                                  execution={"status": "skipped", "message": reason}, actions=[], outcome="cooldown", cascade=cascade)

        stage = self._choose_stage(plan, telemetry, state)
        if preferred_bid and not state.get("last_action") and preferred_bid.target_action in self.STAGES:
            stage = {"action": preferred_bid.target_action,
                     "reason": f"Selected barter plan offers sufficient relief with {preferred_bid.target_action}.",
                     "rejected": [stage_name for stage_name in self.STAGES
                                  if stage_name != preferred_bid.target_action]}
        if not stage["action"]:
            cascade = self._cascade_payload(state, list(self.STAGES), stage["rejected"], stage["reason"],
                                             state.get("last_feedback", {}), state.get("improvement_observed", False))
            return self._response(decision=False, reason=stage["reason"], plan=plan, candidates=candidates,
                                  proposals=proposal_dicts, rounds=rounds, conflicts=conflicts,
                                  execution={"status": "skipped", "message": stage["reason"]}, actions=[],
                                  outcome="safety_stop", cascade=cascade)

        baseline = self._baseline(telemetry, process)
        baseline["process_identity"] = process_identity.to_dict()
        action_started = time.monotonic()
        execution = self._execute(plan["pid"], stage["action"], process_identity,
                                  process, telemetry, plan)
        plan_executions = [execution]
        if execution.get("status") == "success" and selected_resource_plan:
            selected_actions = {(bid.process_identity.pid, bid.target_action)
                                for bid in selected_resource_plan.bids if bid.process_identity}
            primary_key = (plan["pid"], stage["action"])
            for bid in selected_resource_plan.bids:
                if not bid.process_identity or (bid.process_identity.pid, bid.target_action) == primary_key:
                    continue
                secondary_process = self._process_context(telemetry, bid.process_identity.pid)
                secondary_proposal = next((proposal for proposal in proposals
                                           if proposal.target_pid == bid.process_identity.pid
                                           and proposal.action == bid.target_action), None)
                if not secondary_proposal:
                    continue
                secondary_plan = {"proposals": [secondary_proposal], "combined_score": selected_resource_plan.utility * 100,
                                  "factors": plan["factors"], "supporting_agents": [bid.agent_id]}
                secondary_result = self._execute(bid.process_identity.pid, bid.target_action,
                                                 bid.process_identity, secondary_process, telemetry, secondary_plan)
                plan_executions.append(secondary_result)
        feedback = {"improvement_observed": False, "reason": "Action failed; no feedback escalation.",
                    "final_resource_state": {"before": baseline}, "process_observation": {}}
        if all(result.get("status") == "success" for result in plan_executions):
            feedback = self._feedback(baseline, plan["pid"], plan["proposals"])
            prior = state.get("stages_executed", [])
            state = {"cascade_id": state.get("cascade_id") or f"{plan['pid']}-{int(now * 1000)}",
                     "last_action": stage["action"], "last_modified": now,
                     "stages_executed": prior + [stage["action"]],
                     "restore_state": {**state.get("restore_state", {}), **execution.get("restore_state", {})},
                     "improvement_observed": feedback["improvement_observed"],
                     "last_feedback": feedback["final_resource_state"]}
            self._pid_state[process_identity] = state
        execution_outcome = execution
        if len(plan_executions) > 1 and not all(item.get("status") == "success" for item in plan_executions):
            execution_outcome = next((item for item in plan_executions
                                      if item.get("status") != "success"), execution)
        self._record_experience(
            telemetry, process, stage["action"], baseline, feedback, plan["proposals"],
            time.monotonic() - action_started,
            escalation_required=not feedback["improvement_observed"] and stage["action"] != self.STAGES[-1],
            execution=execution_outcome,
        )
        action_record = {"pid": plan["pid"], "action": stage["action"], "reason": stage["reason"],
                 "result": execution, "observation": feedback.get("process_observation", {}),
                 "lifecycle": feedback.get("lifecycle", execution.get("lifecycle"))}
        reason = f"{stage['reason']} {feedback['reason']}"
        cascade = self._cascade_payload(state, list(self.STAGES), stage["rejected"], reason,
                                         feedback["final_resource_state"], feedback["improvement_observed"])
        improved = all(result.get("status") == "success" for result in plan_executions) and feedback["improvement_observed"]
        logger.info("[ARBITER CASCADE] PID=%s stage=%s improved=%s", plan["pid"], stage["action"], improved)
        response = self._response(decision=improved, reason=reason, plan=plan, candidates=candidates,
                              proposals=proposal_dicts, rounds=rounds, conflicts=conflicts,
                              execution=execution, actions=[action_record],
                              outcome="improved" if improved else ("stage_applied_pending_feedback" if execution.get("status") == "success" else "action_failed"),
                              cascade=cascade)
        response["resource_bids"] = [bid.to_dict() for bid in resource_bids]
        response["candidate_plans"] = [candidate.to_dict() for candidate in candidate_plans]
        response["selected_plan"] = selected_resource_plan.to_dict() if selected_resource_plan else None
        response["barter"] = {"credits_offered": round(sum(bid.expected_relief for bid in resource_bids), 4),
                       "relief_debt": round(self._required_relief(telemetry), 4),
                       "conflicts": list(selected_resource_plan.conflicts) if selected_resource_plan else []}
        response["plan_executions"] = plan_executions
        return response
