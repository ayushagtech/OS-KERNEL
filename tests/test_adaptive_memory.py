import math
import os
import tempfile
import time
import unittest

from backend.adaptive_memory import (AdaptiveMitigationMemory, StateSignature,
                                      build_state_signature)
from backend.process_identity import ProcessIdentity


class AdaptiveMemoryTests(unittest.TestCase):
    def signature(self, process_class="unknown"):
        return StateSignature("HIGH", "MEDIUM", "LOW", "LOW", "LOW",
                              process_class, False, "LOW", "HIGH_CPU", "NORMAL_MEMORY")

    def record(self, memory, action="LOWER_PRIORITY", timestamp=None,
               relief=0.95, failed=False, restoration=True):
        timestamp = time.time() if timestamp is None else timestamp
        return memory.record(
            state_signature=self.signature(),
            process_identity=ProcessIdentity(10, 1.0).to_dict(),
            action=action,
            telemetry_before={"resource_state": {"cpu_pressure": 0.8}},
            telemetry_after={"resource_state": {"cpu_pressure": 0.2}},
            expected_relief=0.8,
            actual_relief=relief,
            user_disruption=0.1,
            duration_seconds=1.0,
            restoration_result={"restoration_success": restoration},
            escalation_required=False,
            failed=failed,
            safety_outcome={"status": "error" if failed else "success"},
            timestamp=timestamp,
        )

    def test_identical_state_action_lookup_is_repeatable(self):
        memory = AdaptiveMitigationMemory(path="")
        self.record(memory)
        first = memory.stats(self.signature(), "LOWER_PRIORITY")
        second = memory.stats(self.signature(), "LOWER_PRIORITY")
        self.assertEqual(first, second)

    def test_cold_start_has_no_historical_adjustment(self):
        memory = AdaptiveMitigationMemory(path="")
        stats = memory.stats(self.signature(), "SUSPEND")
        self.assertEqual(stats["adjustment"], 0.0)
        self.assertEqual(stats["selected"]["count"], 0)

    def test_successful_action_gets_bounded_historical_adjustment(self):
        memory = AdaptiveMitigationMemory(path="")
        for index in range(20):
            self.record(memory, timestamp=time.time() + index)
        stats = memory.stats(self.signature(), "LOWER_PRIORITY")
        self.assertGreater(stats["adjustment"], 0.0)
        self.assertLessEqual(abs(stats["adjustment"]), 2.5)

    def test_failed_action_is_penalized(self):
        memory = AdaptiveMitigationMemory(path="")
        for index in range(5):
            self.record(memory, timestamp=time.time() + index, relief=0.0, failed=True, restoration=False)
        stats = memory.stats(self.signature(), "LOWER_PRIORITY")
        self.assertLess(stats["selected"]["weighted_effectiveness"], 0.5)
        self.assertLess(stats["adjustment"], 0.0)

    def test_decay_reduces_old_record_influence(self):
        memory = AdaptiveMitigationMemory(path=None, half_life_seconds=10.0)
        self.record(memory, timestamp=time.time() - 100.0)
        old = memory.stats(self.signature(), "LOWER_PRIORITY")["selected"]["weighted_effectiveness"]
        self.record(memory, timestamp=time.time(), relief=0.0, failed=True, restoration=False)
        current = memory.stats(self.signature(), "LOWER_PRIORITY")["selected"]["weighted_effectiveness"]
        self.assertNotEqual(old, current)

    def test_corrupt_nan_and_infinite_records_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "memory.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"version": 1, "records": [{"state_signature": {}, "action": "X", "timestamp": 1, "effectiveness": NaN}, 7]}')
            memory = AdaptiveMitigationMemory(path=path)
            self.assertEqual(memory.records, [])
            record = self.record(memory)
            self.assertTrue(math.isfinite(record["effectiveness"]))

    def test_persistence_uses_versioned_bounded_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "memory.json")
            memory = AdaptiveMitigationMemory(path=path, limit=2)
            self.record(memory, timestamp=100.0)
            self.record(memory, timestamp=101.0)
            self.record(memory, timestamp=102.0)
            loaded = AdaptiveMitigationMemory(path=path, limit=2)
            self.assertEqual(len(loaded.records), 2)

    def test_process_specific_and_general_statistics_are_separate(self):
        memory = AdaptiveMitigationMemory(path="")
        self.record(memory)
        other = self.signature(process_class="browser")
        stats = memory.stats(other, "LOWER_PRIORITY")
        self.assertEqual(stats["specific"]["count"], 0)
        self.assertEqual(stats["general"]["count"], 1)

    def test_safety_rejection_remains_independent_of_history(self):
        from backend.safety_governor import SafetyGovernor
        from tests.test_safety_governor import MockAdapter
        governor = SafetyGovernor(MockAdapter())
        governor._current_identity = lambda identity: identity
        result = governor.apply(
            ProcessIdentity(10, 1.0), "LOWER_PRIORITY",
            {"process_category": "system", "is_foreground": False}, {}, "test", {}, 1.0
        )
        self.assertEqual(result["error_type"], "CriticalProcess")


if __name__ == "__main__":
    unittest.main()
