"""Deterministic cross-resource bids, credits, debts, and plan utility."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.process_identity import ProcessIdentity

RESOURCE_DOMAINS = {"CPU", "MEMORY", "SWAP", "IO", "NETWORK", "SECURITY"}


@dataclass(frozen=True)
class ResourceBid:
    agent_id: str
    process_identity: Optional[ProcessIdentity]
    resource_domain: str
    target_action: str
    resource_requested: Dict[str, float]
    resource_offered: Dict[str, float]
    resource_units: Dict[str, str]
    expected_relief: float
    estimated_cost: float
    user_disruption: float
    security_impact: float
    reversibility: float
    confidence: float
    duration_seconds: float
    reason: str
    telemetry_timestamp: float
    process_name: str = "Unknown"

    def __post_init__(self):
        if self.resource_domain not in RESOURCE_DOMAINS:
            raise ValueError(f"Unknown resource domain: {self.resource_domain}")
        for value in (self.expected_relief, self.estimated_cost, self.user_disruption,
                      self.security_impact, self.reversibility, self.confidence):
            if not 0.0 <= value <= 1.0:
                raise ValueError("Normalized bid values must be in the range 0..1")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        if self.telemetry_timestamp <= 0:
            raise ValueError("telemetry_timestamp must be positive")

    @classmethod
    def from_proposal(cls, proposal: Any, process: Dict[str, Any],
                      telemetry_timestamp: float) -> "ResourceBid":
        domain = {
            "CPU Agent": "CPU", "Memory Agent": "MEMORY",
            "File System (I/O) Agent": "IO", "Network Agent": "NETWORK",
            "Security Agent": "SECURITY",
        }.get(proposal.agent_name, "SECURITY")
        identity = ProcessIdentity.from_mapping(process.get("process_identity"))
        return cls(
            agent_id=proposal.agent_name,
            process_identity=identity,
            resource_domain=domain,
            target_action=proposal.action,
            resource_requested={domain: 1.0},
            resource_offered={domain: proposal.resource_relief / 100.0},
            resource_units={"requested": "normalized_pressure", "offered": "normalized_pressure"},
            expected_relief=min(1.0, proposal.resource_relief / 100.0),
            estimated_cost=min(1.0, proposal.collateral_cost / 100.0),
            user_disruption=min(1.0, proposal.user_disruption / 100.0),
            security_impact=min(1.0, proposal.security_confidence / 100.0),
            reversibility=min(1.0, proposal.reversibility / 100.0),
            confidence=min(1.0, max(0.0, proposal.net_utility / 100.0 + 0.5)),
            duration_seconds=30.0,
            reason=proposal.rationale,
            telemetry_timestamp=telemetry_timestamp,
            process_name=proposal.process_name,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "process_identity": self.process_identity.to_dict() if self.process_identity else None,
            "resource_domain": self.resource_domain,
            "target_action": self.target_action,
            "resource_requested": self.resource_requested,
            "resource_offered": self.resource_offered,
            "resource_units": self.resource_units,
            "expected_relief": self.expected_relief,
            "estimated_cost": self.estimated_cost,
            "user_disruption": self.user_disruption,
            "security_impact": self.security_impact,
            "reversibility": self.reversibility,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
            "reason": self.reason,
            "telemetry_timestamp": self.telemetry_timestamp,
            "process_name": self.process_name,
        }


@dataclass(frozen=True)
class CandidatePlan:
    bids: Tuple[ResourceBid, ...]
    required_relief: float
    relief: float
    intervention_cost: float
    collateral_cost: float
    user_disruption: float
    stability_gain: float
    security_gain: float
    reversibility_bonus: float
    historical_adjustment: float
    utility: float
    sufficient: bool
    conflicts: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actions": [bid.target_action for bid in self.bids],
            "agents": [bid.agent_id for bid in self.bids],
            "process_identities": [bid.process_identity.to_dict() if bid.process_identity else None for bid in self.bids],
            "required_relief": round(self.required_relief, 4),
            "resource_relief": round(self.relief, 4),
            "intervention_cost": round(self.intervention_cost, 4),
            "collateral_resource_cost": round(self.collateral_cost, 4),
            "disruption_cost": round(self.user_disruption, 4),
            "stability_gain": round(self.stability_gain, 4),
            "security_gain": round(self.security_gain, 4),
            "reversibility_bonus": round(self.reversibility_bonus, 4),
            "historical_adjustment": round(self.historical_adjustment, 4),
            "utility_score": round(self.utility, 4),
            "sufficient": self.sufficient,
            "conflicts": list(self.conflicts),
        }


@dataclass(frozen=True)
class UtilityWeights:
    expected_resource_relief: float = 0.30
    stability_gain: float = 0.18
    security_gain: float = 0.12
    reversibility_bonus: float = 0.10
    historical_effectiveness: float = 0.05
    user_disruption: float = 0.12
    collateral_resource_cost: float = 0.08
    intervention_cost: float = 0.05


def detect_conflicts(bids: Iterable[ResourceBid]) -> List[str]:
    bids = list(bids)
    conflicts = []
    seen_identity_actions = {}
    for bid in bids:
        key = bid.process_identity
        if key and key in seen_identity_actions and seen_identity_actions[key] != bid.target_action:
            conflicts.append(f"conflicting actions for process {key.pid}")
        if key:
            seen_identity_actions[key] = bid.target_action
    cpu_actions = {bid.target_action for bid in bids if bid.resource_domain == "CPU"}
    if len(cpu_actions) > 1:
        conflicts.append("conflicting CPU controls")
    return sorted(set(conflicts))


def build_candidate_plan(bids: Iterable[ResourceBid], required_relief: float,
                         historical_adjustment: float = 0.0,
                         weights: UtilityWeights = UtilityWeights()) -> CandidatePlan:
    bids = tuple(bids)
    conflicts = tuple(detect_conflicts(bids))
    relief = min(1.0, sum(bid.expected_relief for bid in bids))
    intervention_cost = min(1.0, sum(bid.estimated_cost for bid in bids))
    collateral_cost = intervention_cost
    user_disruption = min(1.0, sum(bid.user_disruption for bid in bids))
    stability_gain = relief
    security_gain = max((bid.security_impact for bid in bids), default=0.0)
    reversibility_bonus = min((bid.reversibility for bid in bids), default=0.0)
    utility = (
        weights.expected_resource_relief * relief
        + weights.stability_gain * stability_gain
        + weights.security_gain * security_gain
        + weights.reversibility_bonus * reversibility_bonus
        + weights.historical_effectiveness * historical_adjustment
        - weights.user_disruption * user_disruption
        - weights.collateral_resource_cost * collateral_cost
        - weights.intervention_cost * intervention_cost
    )
    return CandidatePlan(
        bids=bids, required_relief=required_relief, relief=relief,
        intervention_cost=intervention_cost, collateral_cost=collateral_cost,
        user_disruption=user_disruption, stability_gain=stability_gain,
        security_gain=security_gain, reversibility_bonus=reversibility_bonus,
        historical_adjustment=historical_adjustment, utility=utility,
        sufficient=not conflicts and relief >= required_relief,
        conflicts=conflicts,
    )
