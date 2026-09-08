import unittest

from backend.agents.base_agent import Proposal
from backend.agents.arbiter_agent import DecisionArbiterAgent
from backend.bidding import (CandidatePlan, ResourceBid, UtilityWeights,
                              build_candidate_plan, detect_conflicts)
from backend.process_identity import ProcessIdentity


class BiddingTests(unittest.TestCase):
    def bid(self, agent, domain, action, relief, cost, disruption, pid, confidence=0.9):
        return ResourceBid(
            agent_id=agent,
            process_identity=ProcessIdentity(pid, 100.0 + pid),
            resource_domain=domain,
            target_action=action,
            resource_requested={domain: 1.0},
            resource_offered={domain: relief},
            resource_units={"requested": "normalized_pressure", "offered": "normalized_pressure"},
            expected_relief=relief,
            estimated_cost=cost,
            user_disruption=disruption,
            security_impact=0.0,
            reversibility=0.9,
            confidence=confidence,
            duration_seconds=30.0,
            reason="test bid",
            telemetry_timestamp=1000.0,
        )

    def test_bid_creation_and_unit_normalization(self):
        proposal = Proposal("CPU Agent", 42, "worker", "LOWER_PRIORITY",
                            resource_relief=80, collateral_cost=20,
                            user_disruption=10, reversibility=90,
                            rationale="reduce CPU")
        bid = ResourceBid.from_proposal(
            proposal, {"process_identity": {"pid": 42, "create_time": 101.0}}, 1000.0
        )
        self.assertEqual(bid.resource_domain, "CPU")
        self.assertEqual(bid.expected_relief, 0.8)
        self.assertEqual(bid.estimated_cost, 0.2)
        self.assertEqual(bid.duration_seconds, 30.0)

    def test_utility_and_relief_debt_are_deterministic(self):
        plan = build_candidate_plan([self.bid("CPU Agent", "CPU", "LOWER_PRIORITY", .8, .2, .1, 1)], .6)
        repeat = build_candidate_plan([self.bid("CPU Agent", "CPU", "LOWER_PRIORITY", .8, .2, .1, 1)], .6)
        self.assertTrue(plan.sufficient)
        self.assertEqual(plan.utility, repeat.utility)
        self.assertGreater(plan.relief, plan.intervention_cost)

    def test_minimum_disruption_selects_smallest_sufficient_plan(self):
        gentle = self.bid("CPU Agent", "CPU", "LOWER_PRIORITY", .8, .2, .1, 1)
        severe = self.bid("Security Agent", "SECURITY", "SUSPEND", .95, .5, .8, 2)
        plans = [build_candidate_plan([bid], .7) for bid in (gentle, severe)]
        selected = DecisionArbiterAgent._select_candidate_plan(plans)
        self.assertEqual(selected.bids[0].target_action, "LOWER_PRIORITY")

    def test_multi_bid_plan_and_conflicts(self):
        cpu = self.bid("CPU Agent", "CPU", "LOWER_PRIORITY", .4, .1, .1, 1)
        io = self.bid("I/O Agent", "IO", "LOWER_PRIORITY", .4, .1, .1, 2)
        plan = build_candidate_plan([cpu, io], .7)
        self.assertTrue(plan.sufficient)
        self.assertEqual(plan.conflicts, ())
        conflict = self.bid("CPU Agent", "CPU", "CLAMP_AFFINITY", .4, .2, .2, 3)
        self.assertTrue(detect_conflicts([cpu, conflict]))

    def test_arbiter_never_executes_unsupported_bid(self):
        arbiter = DecisionArbiterAgent()
        proposal = Proposal("Memory Agent", 42, "worker", "ZRAM_COMPRESS",
                            resource_relief=90, collateral_cost=1,
                            user_disruption=1, reversibility=90,
                            rationale="unsupported")
        result = arbiter.arbitrate([proposal], {"timestamp": 1000.0, "processes": []})
        self.assertEqual(result["final_outcome"], "no_action")
        self.assertEqual(result["resource_bids"], [])


if __name__ == "__main__":
    unittest.main()
