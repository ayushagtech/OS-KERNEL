import unittest
from unittest.mock import patch

from backend.control_interface import ControlResult
from backend.process_identity import ProcessIdentity
from backend.safety_governor import GovernorLimits, SafetyGovernor


class MockAdapter:
    def __init__(self, available=True, fail_apply=False, fail_restore=False):
        self.available = available
        self.fail_apply = fail_apply
        self.fail_restore = fail_restore
        self.calls = []

    def capabilities(self):
        return {"available": self.available}

    def _result(self, action, identity, token=None, failure=False):
        self.calls.append(action)
        if failure:
            return ControlResult(False, action, identity, "mock", error="mock failure", error_type="MockFailure")
        return ControlResult(True, action, identity, "mock", reversible=token is not None,
                             restoration_token=token, message="mock success")

    def lower_priority(self, identity):
        return self._result("LOWER_PRIORITY", identity, {"priority": 0}, self.fail_apply)

    def restore_priority(self, identity, token):
        return self._result("RESTORE_PRIORITY", identity, failure=self.fail_restore)

    def clamp_affinity(self, identity, cpus):
        return self._result("CLAMP_AFFINITY", identity, {"affinity": [0, 1]}, self.fail_apply)

    def restore_affinity(self, identity, token):
        return self._result("RESTORE_AFFINITY", identity, failure=self.fail_restore)

    def suspend(self, identity):
        return self._result("SUSPEND", identity, {"suspended": True}, self.fail_apply)

    def resume(self, identity):
        return self._result("RESUME", identity, failure=self.fail_restore)


class SafetyGovernorTests(unittest.TestCase):
    identity = ProcessIdentity(1234, 10.0)
    process = {"pid": 1234, "is_foreground": False, "user_disruption_score": 0.2,
               "process_category": "unknown"}

    def make_governor(self, adapter=None, limits=None):
        governor = SafetyGovernor(adapter or MockAdapter(), limits=limits)
        governor._current_identity = lambda identity: identity
        return governor

    def test_critical_process_is_rejected(self):
        governor = self.make_governor()
        result = governor.apply(self.identity, "LOWER_PRIORITY", {**self.process, "process_category": "system"},
                                {}, "test", {}, 1.0)
        self.assertEqual(result["error_type"], "CriticalProcess")
        self.assertFalse(governor.adapter.calls)

    def test_foreground_and_low_confidence_are_rejected(self):
        governor = self.make_governor()
        foreground = governor.apply(self.identity, "LOWER_PRIORITY", {**self.process, "is_foreground": True},
                                    {}, "test", {}, 1.0)
        low_confidence = governor.apply(self.identity, "LOWER_PRIORITY", self.process,
                                        {}, "test", {}, 0.1)
        self.assertEqual(foreground["error_type"], "ForegroundProcess")
        self.assertEqual(low_confidence["error_type"], "LowConfidence")

    def test_unsupported_platform_and_identity_mismatch_are_rejected(self):
        unsupported = self.make_governor(MockAdapter(available=False))
        result = unsupported.apply(self.identity, "LOWER_PRIORITY", self.process, {}, "test", {}, 1.0)
        self.assertEqual(result["error_type"], "UnsupportedPlatform")
        governor = SafetyGovernor(MockAdapter())
        governor._current_identity = lambda identity: (_ for _ in ()).throw(RuntimeError("Process identity mismatch"))
        result = governor.apply(self.identity, "LOWER_PRIORITY", self.process, {}, "test", {}, 1.0)
        self.assertEqual(result["error_type"], "RuntimeError")

    def test_successful_intervention_and_restoration(self):
        adapter = MockAdapter()
        governor = self.make_governor(adapter)
        applied = governor.apply(self.identity, "LOWER_PRIORITY", self.process,
                                 {"resource_state": {"overall_pressure": 0.8}}, "test", {"benefit": 1}, 1.0)
        self.assertEqual(applied["status"], "success")
        restored = governor.restore(self.identity)
        self.assertTrue(restored["restoration_success"])
        double_restore = governor.restore(self.identity)
        self.assertTrue(double_restore["success"])
        self.assertEqual(adapter.calls, ["LOWER_PRIORITY", "RESTORE_PRIORITY"])

    def test_timeout_restores_intervention(self):
        clock = [100.0]
        adapter = MockAdapter()
        governor = self.make_governor(adapter, GovernorLimits(max_duration_seconds=5))
        with patch("backend.safety_governor.time.monotonic", side_effect=lambda: clock[0]):
            governor.apply(self.identity, "SUSPEND", self.process, {}, "test", {}, 1.0)
            clock[0] = 106.0
            results = governor.restore_expired()
        self.assertEqual(results[0]["restoration_success"], True)
        self.assertIn("RESUME", adapter.calls)

    def test_cooldown_and_simultaneous_limits(self):
        adapter = MockAdapter()
        limits = GovernorLimits(max_simultaneous_interventions=1, cooldown_seconds=30)
        governor = self.make_governor(adapter, limits)
        first = governor.apply(self.identity, "SUSPEND", self.process, {}, "test", {}, 1.0)
        second_identity = ProcessIdentity(1235, 10.0)
        second = governor.apply(second_identity, "SUSPEND", {**self.process, "pid": 1235}, {}, "test", {}, 1.0)
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["error_type"], "InterventionLimit")
        governor.restore(self.identity)
        cooldown = governor.apply(self.identity, "SUSPEND", self.process, {}, "test", {}, 1.0)
        self.assertEqual(cooldown["error_type"], "Cooldown")

    def test_failed_control_and_failed_restoration_are_reported(self):
        apply_governor = self.make_governor(MockAdapter(fail_apply=True))
        failed_apply = apply_governor.apply(self.identity, "SUSPEND", self.process, {}, "test", {}, 1.0)
        self.assertEqual(failed_apply["error_type"], "MockFailure")
        restore_governor = self.make_governor(MockAdapter(fail_restore=True))
        restore_governor.apply(self.identity, "LOWER_PRIORITY", self.process, {}, "test", {}, 1.0)
        failed_restore = restore_governor.restore(self.identity)
        self.assertFalse(failed_restore["restoration_success"])
        self.assertEqual(restore_governor.registry.completed[-1].status, "restoration_failure")


if __name__ == "__main__":
    unittest.main()
