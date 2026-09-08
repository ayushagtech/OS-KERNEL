import time
import os
import sys
import logging
from typing import Dict, Any, List, Optional

try:
    import psutil
except ImportError:
    psutil = None

from backend.agents.memory_agent import MemoryAgent
from backend.agents.cpu_agent import CPUAgent
from backend.agents.io_agent import IOAgent
from backend.agents.network_agent import NetworkAgent
from backend.agents.security_agent import SecurityAgent
from backend.agents.arbiter_agent import DecisionArbiterAgent
from backend.process_identity import ProcessIdentity
from backend.telemetry import (PROCESS_SAMPLE_INTERVAL, ResourceStateVector,
                                TelemetrySnapshot, TelemetryThresholds,
                                collect_process_telemetry)
from backend.pressure_predictor import PressurePredictor

logger = logging.getLogger("GuardianDaemon")

class GuardianDaemon:
    """
    Agentic OS Kernel Guardian Daemon.
    Continuously monitors system health, triggers multi-agent negotiation,
    and executes self-healing non-destructive control primitives.
    """
    def __init__(self, telemetry_thresholds: TelemetryThresholds | None = None):
        self.memory_agent = MemoryAgent()
        self.cpu_agent = CPUAgent()
        self.io_agent = IOAgent()
        self.network_agent = NetworkAgent()
        self.security_agent = SecurityAgent()
        self.arbiter = DecisionArbiterAgent()

        self.history_logs = []
        self.total_heals = 0
        self.successful_mitigations = 0
        # Kept in memory only: enough history for a direction-of-change hint,
        # without turning telemetry collection into a profiler.
        self._process_samples: Dict[ProcessIdentity, Dict[str, float]] = {}
        # Lightweight telemetry-derived history for deterministic pressure
        # prediction. This is a heuristic time-series window, not ML.
        self._pressure_predictor = PressurePredictor(
            ("cpu", "memory", "swap", "io", "network")
        )
        # A compact Guardian-level mirror of completed feedback observations.
        # The arbiter owns effectiveness statistics; this preserves recent
        # decision context without retaining unbounded telemetry.
        self._decision_experience_history: List[Dict[str, Any]] = []
        self._decision_experience_limit = 60
        self._last_experience_timestamp = None
        self._telemetry_thresholds = telemetry_thresholds or TelemetryThresholds()
        self._telemetry_previous: TelemetrySnapshot | None = None
        self._cpu_pressure_ema: float | None = None
        self._process_cache: List[Dict[str, Any]] = []
        self._last_process_sample_monotonic = 0.0

    def _record_decision_experience(self, arbitration: Dict[str, Any]) -> None:
        observation = arbitration.get("learning", {}).get("last_observation")
        if not observation or observation.get("timestamp") == self._last_experience_timestamp:
            return
        self._decision_experience_history.append(observation)
        if len(self._decision_experience_history) > self._decision_experience_limit:
            self._decision_experience_history.pop(0)
        self._last_experience_timestamp = observation.get("timestamp")

    def _record_pressure_sample(self, timestamp: float, pressures: Dict[str, Optional[float]]) -> Dict[str, Dict[str, object]]:
        for resource, value in pressures.items():
            if value is not None:
                self._pressure_predictor.add_sample(resource, timestamp, value)
        predictions = self._pressure_predictor.predict_all({
            "cpu": 0.90, "memory": 0.90, "swap": 0.80, "io": 0.80, "network": 0.80,
        }, now=timestamp)
        memory = predictions.get("memory", {})
        memory_prediction = dict(memory)
        memory_prediction.update({
            "risk": "HIGH" if memory.get("predicted_threshold_crossing") else "LOW",
            "predicted_exhaustion": False,
            "resource": "memory",
        })
        return {"memory": memory_prediction, "resources": predictions}

    @staticmethod
    def _foreground_pid():
        """Return the active window's PID when the platform exposes one."""
        if os.name != "nt":
            return None

        try:
            import ctypes

            window = ctypes.windll.user32.GetForegroundWindow()
            if not window:
                return None
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            return pid.value or None
        except (AttributeError, OSError):
            return None

    @staticmethod
    def _process_category(process: Dict[str, Any]) -> str:
        """Classify purpose conservatively; this is not a malware verdict."""
        name = (process.get("name") or "").lower()
        pid = process.get("pid")
        parent_pid = process.get("ppid")

        if name in {"xmrig", "minerd", "cpuminer", "cryptonight"}:
            return "suspicious"
        if pid in (0, 1) or parent_pid in (0, 1) or name in {
            "system", "system idle process", "init", "systemd", "launchd",
            "kernel_task", "services.exe", "svchost.exe", "wininit.exe",
        }:
            return "system"
        if any(token in name for token in ("chrome", "chromium", "firefox", "safari", "msedge", "opera")):
            return "browser"
        if any(token in name for token in ("code", "idea", "pycharm", "vim", "emacs", "eclipse", "devenv")):
            return "development_tool"
        return "unknown"

    def _user_disruption_context(
        self, process: Dict[str, Any], foreground_pid: int | None
    ) -> None:
        """Add a lightweight, explainable user-impact context to a process."""
        pid = process.get("pid")
        is_foreground = foreground_pid is not None and pid == foreground_pid
        category = "foreground_app" if is_foreground else self._process_category(process)

        if is_foreground:
            score, reason = 1.0, "Active foreground window"
        elif category == "suspicious":
            score, reason = 0.05, "Matches a known high-risk process signature"
        elif category in {"system", "background_service"}:
            score, reason = 0.10, "System or background service"
        elif category in {"browser", "development_tool"}:
            score, reason = 0.45, "Potential user application; not the active foreground window"
        else:
            score, reason = 0.30, "No active foreground association"

        process["is_foreground"] = is_foreground
        # Retained for existing agents; unlike the old heuristic it is based on
        # observed foreground state, not a hard-coded application-name list.
        process["is_background"] = not is_foreground
        process["process_category"] = category
        process["user_disruption_score"] = score
        process["protection_reason"] = reason

        if not isinstance(pid, int):
            return
        cpu = float(process.get("cpu_percent") or 0.0)
        memory = float(process.get("memory_percent") or 0.0)
        identity = ProcessIdentity.from_mapping(process.get("process_identity"))
        previous = self._process_samples.get(identity) if identity else None
        if previous:
            process["process_cpu_trend"] = round(cpu - previous["cpu"], 2)
            process["process_memory_trend"] = round(memory - previous["memory"], 2)
        if identity:
            self._process_samples[identity] = {"cpu": cpu, "memory": memory}

    def collect_telemetry(self) -> Dict[str, Any]:
        """Gathers system metrics and active process list."""
        if psutil:
            snapshot = TelemetrySnapshot.capture(
                psutil, previous=self._telemetry_previous,
                thresholds=self._telemetry_thresholds
            )
            if snapshot is None:
                return self._unavailable_telemetry()
            self._telemetry_previous = snapshot
            raw = snapshot.to_internal_dict()
            per_cpu = snapshot.cpu_per_core
            per_core_average = snapshot.cpu_percent
            per_core_max = max(per_cpu) if per_cpu else 0.0
            cpu_pct = per_core_average

            foreground_pid = self._foreground_pid()
            if (snapshot.monotonic_timestamp - self._last_process_sample_monotonic
                    >= PROCESS_SAMPLE_INTERVAL or not self._process_cache):
                self._process_cache = collect_process_telemetry(
                    psutil, psutil.process_iter(
                        ['pid', 'ppid', 'name', 'create_time', 'cpu_percent', 'memory_percent']
                    )
                )
                self._last_process_sample_monotonic = snapshot.monotonic_timestamp
            procs = [dict(process) for process in self._process_cache]
            for process in procs:
                self._user_disruption_context(process, foreground_pid)

            # Bound state in case a long-running daemon sees many short-lived PIDs.
            active_identities = {
                ProcessIdentity.from_mapping(p.get("process_identity")) for p in procs
            }
            self._process_samples = {
                identity: sample for identity, sample in self._process_samples.items()
                if identity in active_identities
            }
            
            # Sort top processes by CPU and RAM
            top_procs = sorted(procs, key=lambda x: (x.get('cpu_percent', 0) or 0) + (x.get('memory_percent', 0) or 0), reverse=True)[:15]
            telemetry_timestamp = snapshot.timestamp
            pressure_values = [snapshot.cpu_pressure, snapshot.memory_pressure,
                               snapshot.swap_pressure, snapshot.io_pressure,
                               snapshot.network_pressure]
            available_pressures = [value for value in pressure_values if value is not None]
            if snapshot.cpu_pressure is not None:
                self._cpu_pressure_ema = (snapshot.cpu_pressure if self._cpu_pressure_ema is None
                                          else 0.70 * self._cpu_pressure_ema
                                          + 0.30 * snapshot.cpu_pressure)
            sustained_cpu_pressure = self._cpu_pressure_ema
            prediction_payload = self._record_pressure_sample(
                snapshot.monotonic_timestamp,
                {"cpu": sustained_cpu_pressure, "memory": snapshot.memory_pressure,
                 "swap": snapshot.swap_pressure, "io": snapshot.io_pressure,
                 "network": snapshot.network_pressure},
            )
            prediction = prediction_payload["memory"]
            resource_state = ResourceStateVector(
                cpu_pressure=sustained_cpu_pressure,
                memory_pressure=snapshot.memory_pressure,
                swap_pressure=snapshot.swap_pressure,
                io_pressure=snapshot.io_pressure,
                network_pressure=snapshot.network_pressure,
                overall_pressure=(sum(available_pressures) / len(available_pressures)
                                  if available_pressures else None),
                timestamp=snapshot.timestamp,
                process_count=len(procs),
                foreground_process=foreground_pid,
                critical_process_count=sum(
                    process.get("process_category") == "system" for process in procs
                ),
                telemetry_confidence=len(available_pressures) / len(pressure_values),
            )

            return {
                "timestamp": telemetry_timestamp,
                "memory": {
                    "total_bytes": raw["memory_total_bytes"],
                    "used_bytes": raw["memory_used_bytes"],
                    "available_bytes": raw["memory_available_bytes"],
                    "total_gb": round(raw["memory_total_bytes"] / (1024**3), 2),
                    "used_gb": round(raw["memory_used_bytes"] / (1024**3), 2),
                    "available_gb": round(raw["memory_available_bytes"] / (1024**3), 2),
                    "percent": raw["memory_used_bytes"] / raw["memory_total_bytes"] * 100
                    if raw["memory_total_bytes"] else 0.0,
                    "swap_used_bytes": raw["swap_used_bytes"],
                    "swap_total_bytes": raw["swap_total_bytes"],
                    "swap_percent": snapshot.swap_percent
                },
                "swap": {
                    "total_bytes": raw["swap_total_bytes"],
                    "used_bytes": raw["swap_used_bytes"],
                    "percent": snapshot.swap_percent,
                    "pressure": snapshot.swap_pressure
                },
                "cpu": {
                    "total_percent": cpu_pct,
                    "cores": len(per_cpu),
                    "per_core": per_cpu,
                    "per_core_average": per_core_average,
                    "per_core_max": per_core_max,
                    "sample_timestamp": telemetry_timestamp,
                    "load_average": list(snapshot.load_average) if snapshot.load_average else None,
                    "pressure": snapshot.cpu_pressure
                },
                "io": {
                    "read_bytes": raw["disk_read_bytes"],
                    "write_bytes": raw["disk_write_bytes"],
                    "read_bytes_per_sec": raw["disk_read_bytes_per_sec"],
                    "write_bytes_per_sec": raw["disk_write_bytes_per_sec"],
                    "read_ops_per_sec": raw["disk_read_ops_per_sec"],
                    "write_ops_per_sec": raw["disk_write_ops_per_sec"],
                    "pressure": snapshot.io_pressure,
                    "is_busy": snapshot.io_pressure is not None and snapshot.io_pressure >= 0.60
                },
                "network": {
                    "bytes_sent": raw["network_bytes_sent"],
                    "bytes_recv": raw["network_bytes_recv"],
                    "bytes_sent_per_sec": raw["network_bytes_sent_per_sec"],
                    "bytes_recv_per_sec": raw["network_bytes_recv_per_sec"],
                    "packets_sent_per_sec": raw["network_packets_sent_per_sec"],
                    "packets_recv_per_sec": raw["network_packets_recv_per_sec"],
                    "pressure": snapshot.network_pressure,
                    "is_high": snapshot.network_pressure is not None and snapshot.network_pressure >= 0.60
                },
                "processes": top_procs,
                "prediction": prediction,
                "predictions": prediction_payload["resources"],
                "resource_state": resource_state.to_dict(),
                "telemetry_available": True
            }
        else:
            return self._unavailable_telemetry()

    @staticmethod
    def _unavailable_telemetry() -> Dict[str, Any]:
        """Expose unavailable measurements instead of fabricating system values."""
        return {"timestamp": time.time(), "telemetry_available": False,
            "memory": {"total_bytes": None, "used_bytes": None, "available_bytes": None,
                    "total_gb": None, "used_gb": None, "available_gb": None,
                    "percent": None, "swap_used_bytes": None, "swap_total_bytes": None,
                    "swap_percent": None},
            "cpu": {"total_percent": None, "cores": None, "per_core": [],
                "per_core_average": None, "per_core_max": None, "pressure": None},
            "io": {"read_bytes": None, "write_bytes": None, "read_bytes_per_sec": None,
                   "write_bytes_per_sec": None, "read_ops_per_sec": None,
                   "write_ops_per_sec": None, "pressure": None, "is_busy": False},
            "network": {"bytes_sent": None, "bytes_recv": None, "bytes_sent_per_sec": None,
                    "bytes_recv_per_sec": None, "packets_sent_per_sec": None,
                    "packets_recv_per_sec": None, "pressure": None, "is_high": False},
            "resource_state": ResourceStateVector(
                cpu_pressure=None, memory_pressure=None, swap_pressure=None,
                io_pressure=None, network_pressure=None, overall_pressure=None,
                timestamp=time.time(), telemetry_confidence=0.0
            ).to_dict(),
            "prediction": {"risk": "LOW", "resource": "memory", "predicted_exhaustion": False,
                       "seconds_to_threshold": None, "confidence": 0.0,
                       "reason": "psutil is unavailable; telemetry is unavailable."},
            "predictions": {},
            "processes": []}

    def run_cycle(self) -> Dict[str, Any]:
        telemetry = self.collect_telemetry()

        # Step 1: State Assertion & Collaborative Bidding across domain agents
        all_proposals = []
        all_proposals.extend(self.memory_agent.evaluate(telemetry))
        all_proposals.extend(self.cpu_agent.evaluate(telemetry))
        all_proposals.extend(self.io_agent.evaluate(telemetry))
        all_proposals.extend(self.network_agent.evaluate(telemetry))
        all_proposals.extend(self.security_agent.evaluate(telemetry))

        # Step 2: Consensus Optimization by Decision Arbiter
        arbitration_result = self.arbiter.arbitrate(all_proposals, telemetry)
        self._record_decision_experience(arbitration_result)

        if arbitration_result.get("decision_made"):
            self.total_heals += 1
            self.successful_mitigations += 1

            log_entry = {
                "timestamp": telemetry["timestamp"],
                "winner": arbitration_result["winning_proposal"],
                "execution": arbitration_result["execution_result"]
            }
            self.history_logs.insert(0, log_entry)
            if len(self.history_logs) > 50:
                self.history_logs.pop()

        return {
            "telemetry": telemetry,
            "resource_state": telemetry.get("resource_state", {}),
            "control_capabilities": self.arbiter.safety_governor.adapter.capabilities(),
            "agent_proposals": [p.to_dict() for p in all_proposals],
            "arbitration": arbitration_result,
            "stats": {
                "total_heals": self.total_heals,
                "successful_mitigations": self.successful_mitigations,
                "status": "PROTECTED"
            },
            "history": self.history_logs[:10],
            "experience": {
                "observations": len(self._decision_experience_history),
                "recent_decisions": self._decision_experience_history[-10:],
                "adaptive_memory": self.arbiter.adaptive_memory.action_summary(),
                "method": "bounded deterministic decayed outcome statistics"
            }
        }

guardian_daemon = GuardianDaemon()
