import unittest
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from backend.action_registry import ACTION_REGISTRY, is_executable
from backend.agents.arbiter_agent import DecisionArbiterAgent
from backend.agents.memory_agent import MemoryAgent
from backend.hooks import process_control
from backend.hooks.process_control import ProcessControlHooks
from backend.process_identity import ProcessIdentity
from backend.telemetry import (CPU_SAMPLE_INTERVAL, ResourceStateVector,
                                TelemetrySnapshot, calculate_rate,
                                collect_process_telemetry)


class FakeProcess:
    def __init__(self, pid=42, create_time=100.0):
        self.pid = pid
        self._create_time = create_time
        self.priority = 0

    def create_time(self):
        return self._create_time

    def name(self):
        return "worker"

    def nice(self, value=None):
        if value is not None:
            self.priority = value
        return self.priority

    def suspend(self):
        return None

    def resume(self):
        return None

    def cpu_affinity(self, value=None):
        return [0] if value is None else None

    def cpu_percent(self, interval=None):
        return 1.0

    def memory_percent(self):
        return 1.0

    def status(self):
        return "running"


class GuardianHardeningTests(unittest.TestCase):
    def test_rate_calculation_handles_first_reset_and_zero_elapsed(self):
        self.assertIsNone(calculate_rate(100, None, 1.0))
        self.assertEqual(calculate_rate(300, 100, 2.0), 100.0)
        self.assertIsNone(calculate_rate(50, 100, 2.0))
        self.assertIsNone(calculate_rate(300, 100, 0.0))

    def test_snapshot_derives_io_network_and_resource_pressures(self):
        class CounterPsutil:
            NoSuchProcess = psutil.NoSuchProcess
            AccessDenied = psutil.AccessDenied
            ZombieProcess = psutil.ZombieProcess

            def __init__(self):
                self.sample = 0

            def virtual_memory(self):
                return SimpleNamespace(total=100, used=90, available=10)

            def swap_memory(self):
                return SimpleNamespace(total=100, used=50, percent=50)

            def cpu_percent(self, interval, percpu):
                return [90.0]

            def disk_io_counters(self):
                self.sample += 1
                value = 0 if self.sample == 1 else 100 * 1024 * 1024
                return SimpleNamespace(read_bytes=value, write_bytes=value,
                                       read_count=value // 1024, write_count=value // 1024)

            def net_io_counters(self):
                value = 0 if self.sample == 1 else 20 * 1024 * 1024
                return SimpleNamespace(bytes_sent=value, bytes_recv=value,
                                       packets_sent=value // 1024, packets_recv=value // 1024)

            def getloadavg(self):
                return (1.0, 0.5, 0.2)

        fake = CounterPsutil()
        with patch("backend.telemetry.time.monotonic", side_effect=[10.0, 12.0]):
            first = TelemetrySnapshot.capture(fake)
            second = TelemetrySnapshot.capture(fake, previous=first)
        self.assertIsNone(first.disk_read_bytes_per_sec)
        self.assertEqual(second.disk_read_bytes_per_sec, 50 * 1024 * 1024)
        self.assertEqual(second.network_bytes_sent_per_sec, 10 * 1024 * 1024)
        self.assertGreater(second.cpu_pressure, 0.0)
        self.assertGreater(second.memory_pressure, 0.0)
        self.assertEqual(second.swap_pressure, 0.5)
        self.assertEqual(second.io_pressure, 1.0)
        self.assertEqual(second.network_pressure, 1.0)

    def test_resource_state_vector_is_serializable(self):
        state = ResourceStateVector(0.1, 0.2, 0.3, None, 0.5, 0.25, 10.0,
                                    process_count=3, telemetry_confidence=0.8)
        payload = state.to_dict()
        self.assertEqual(payload["io_pressure"], None)
        self.assertEqual(payload["process_count"], 3)

    def test_process_disappearing_during_collection_is_skipped(self):
        class DisappearingProcess:
            @property
            def info(self):
                raise psutil.NoSuchProcess(42)

        class PsutilErrors:
            NoSuchProcess = psutil.NoSuchProcess
            AccessDenied = psutil.AccessDenied
            ZombieProcess = psutil.ZombieProcess

        self.assertEqual(collect_process_telemetry(PsutilErrors(), [DisappearingProcess()]), [])

    def test_pid_reuse_is_a_different_identity(self):
        first = ProcessIdentity.from_process(FakeProcess(5000, 10.0))
        replacement = FakeProcess(5000, 20.0)
        self.assertNotEqual(first, ProcessIdentity.from_process(replacement))
        self.assertFalse(first.matches_process(replacement))

    def test_identity_mismatch_blocks_intervention(self):
        expected = ProcessIdentity(42, 10.0)
        with patch.object(process_control.psutil, "Process", return_value=FakeProcess(42, 20.0)):
            result = ProcessControlHooks.lower_priority(42, expected)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(result["process_identity"], expected.to_dict())

    def test_disappearing_process_before_intervention_is_structured(self):
        with patch.object(process_control.psutil, "Process", side_effect=psutil.NoSuchProcess(42)):
            result = ProcessControlHooks.lower_priority(42, ProcessIdentity(42, 10.0))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "NoSuchProcess")
        self.assertEqual(result["pid"], 42)

    def test_disappearing_process_before_restoration_is_structured(self):
        identity = ProcessIdentity(42, 10.0)
        with patch.object(process_control.psutil, "Process", side_effect=psutil.NoSuchProcess(42)):
            result = ProcessControlHooks.restore_process_state(
                42, {"priority": 0, "process_identity": identity.to_dict()}
            )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["results"][0]["error_type"], "NoSuchProcess")

    def test_memory_baseline_keeps_raw_precision(self):
        telemetry = {"memory": {
            "total_bytes": 8_589_934_593,
            "used_bytes": 4_123_456_789,
            "available_bytes": 4_466_477_804,
            "percent": 48.0,
        }, "cpu": {"total_percent": 12.5}}
        baseline = DecisionArbiterAgent._baseline(telemetry, {})
        self.assertEqual(baseline["memory_available_bytes"], 4_466_477_804)
        self.assertNotEqual(baseline["memory_available_bytes"], round(4_466_477_804 / (1024 ** 3), 2) * 1024 ** 3)

    def test_snapshot_uses_one_shared_cpu_sampling_method(self):
        calls = []
        fake_psutil = SimpleNamespace(
            virtual_memory=lambda: SimpleNamespace(total=1000, used=400, available=600),
            swap_memory=lambda: SimpleNamespace(used=10, percent=1.0),
            cpu_percent=lambda interval, percpu: calls.append((interval, percpu)) or [10.0, 20.0],
            disk_io_counters=lambda: SimpleNamespace(read_bytes=1, write_bytes=2),
            net_io_counters=lambda: SimpleNamespace(bytes_sent=3, bytes_recv=4),
        )
        snapshot = TelemetrySnapshot.capture(fake_psutil)
        self.assertEqual(snapshot.cpu_percent, 15.0)
        self.assertEqual(calls, [(CPU_SAMPLE_INTERVAL, True)])
        self.assertEqual(snapshot.memory_available_bytes, 600)

    def test_all_arbiter_stages_are_executable(self):
        for action in DecisionArbiterAgent.STAGES:
            self.assertTrue(is_executable(action), action)
            self.assertTrue(ACTION_REGISTRY[action]["executor"])

    def test_zram_is_unavailable_and_not_proposed(self):
        self.assertFalse(is_executable("ZRAM_COMPRESS"))
        process = {"pid": 42, "name": "worker", "memory_percent": 20.0,
                   "is_background": True, "is_foreground": False}
        proposals = MemoryAgent().evaluate({
            "memory": {"percent": 95.0}, "processes": [process],
            "prediction": {},
        })
        self.assertNotIn("ZRAM_COMPRESS", {proposal.action for proposal in proposals})
        result = ProcessControlHooks._error(42, "ZRAM_COMPRESS", RuntimeError("unavailable"), ProcessIdentity(42, 1.0))
        self.assertEqual(result["status"], "error")

    def test_daemon_metric_name_does_not_claim_prevented_crashes(self):
        from backend.daemon import GuardianDaemon
        daemon = GuardianDaemon()
        self.assertFalse(hasattr(daemon, "prevented_crashes"))
        self.assertEqual(daemon.successful_mitigations, 0)


if __name__ == "__main__":
    unittest.main()
