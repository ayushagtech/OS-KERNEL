import unittest

from backend.process_identity import ProcessIdentity
from backend.safety_governor import (InterventionState, GovernorLimits,
                                     SafetyGovernor)
from tests.test_safety_governor import MockAdapter


class InterventionLifecycleTests(unittest.TestCase):
    identity = ProcessIdentity(501, 10.0)
    process = {"pid": 501, "is_foreground": False,
               "user_disruption_score": 0.1, "process_category": "unknown"}

    def governor(self, adapter=None):
        governor = SafetyGovernor(
            adapter or MockAdapter(),
            GovernorLimits(recovery_consecutive_samples=2),
        )
        governor._current_identity = lambda identity: identity
        return governor

    def test_legal_lifecycle_transitions(self):
        lifecycle = InterventionState("id", self.identity, "CPU", "LOWER_PRIORITY",
                                      1.0, "DETECTED", {})
        for state in ("PROPOSED", "BID_SELECTED", "SAFETY_CHECKED", "APPLIED",
                      "MONITORED", "RECOVERED", "RESTORED", "VERIFIED", "RECORDED"):
            lifecycle.transition(state)
        self.assertEqual(lifecycle.current_state, "RECORDED")

    def test_invalid_transition_is_rejected(self):
        lifecycle = InterventionState("id", self.identity, "CPU", "LOWER_PRIORITY",
                                      1.0, "RESTORED", {})
        with self.assertRaises(ValueError):
            lifecycle.transition("APPLIED")

    def test_apply_monitor_recover_restore_verify_record(self):
        governor = self.governor()
        applied = governor.apply(self.identity, "LOWER_PRIORITY", self.process,
                                 {"resource_state": {"overall_pressure": 0.8}},
                                 "test", {"expected_relief": 0.5}, 1.0, "CPU")
        self.assertEqual(applied["lifecycle"]["current_state"], "APPLIED")
        monitored = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.6}})
        self.assertEqual(monitored["lifecycle"]["current_state"], "MONITORED")
        recovered = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.4}})
        self.assertFalse(recovered["recovered"])
        recovered = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.3}})
        self.assertTrue(recovered["recovered"])
        restored = governor.restore(self.identity)
        self.assertTrue(restored["restoration_success"])
        self.assertEqual(restored["lifecycle"]["current_state"], "RECORDED")
        self.assertEqual(restored["lifecycle"]["resource_domain"], "CPU")

    def test_failed_apply_reaches_failed(self):
        governor = self.governor(MockAdapter(fail_apply=True))
        result = governor.apply(self.identity, "SUSPEND", self.process, {}, "test", {}, 1.0)
        self.assertEqual(result["lifecycle"]["current_state"], "FAILED")
        self.assertEqual(result["status"], "error")

    def test_failed_restoration_reaches_restoration_failed(self):
        adapter = MockAdapter(fail_restore=True)
        governor = self.governor(adapter)
        governor.apply(self.identity, "LOWER_PRIORITY", self.process, {}, "test", {}, 1.0)
        result = governor.restore(self.identity)
        self.assertEqual(result["lifecycle"]["current_state"], "RESTORATION_FAILED")
        self.assertFalse(result["restoration_success"])

    def test_recovery_requires_consecutive_samples(self):
        governor = self.governor()
        governor.apply(self.identity, "LOWER_PRIORITY", self.process,
                       {"resource_state": {"overall_pressure": 0.8}}, "test", {}, 1.0)
        first = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.4}})
        second = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.7}})
        third = governor.monitor(self.identity, {"resource_state": {"overall_pressure": 0.4}})
        self.assertFalse(first["recovered"])
        self.assertFalse(second["recovered"])
        self.assertFalse(third["recovered"])


if __name__ == "__main__":
    unittest.main()
