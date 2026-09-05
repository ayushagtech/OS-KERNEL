import time
import os
import sys
import logging
from typing import Dict, Any, List

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

logger = logging.getLogger("GuardianDaemon")

class GuardianDaemon:
    """
    Agentic OS Kernel Guardian Daemon.
    Continuously monitors system health, triggers multi-agent negotiation,
    and executes self-healing non-destructive control primitives.
    """
    def __init__(self):
        self.memory_agent = MemoryAgent()
        self.cpu_agent = CPUAgent()
        self.io_agent = IOAgent()
        self.network_agent = NetworkAgent()
        self.security_agent = SecurityAgent()
        self.arbiter = DecisionArbiterAgent()

        self.history_logs = []
        self.total_heals = 0
        self.prevented_crashes = 0

    def collect_telemetry(self) -> Dict[str, Any]:
        """Gathers system metrics and active process list."""
        if psutil:
            mem = psutil.virtual_memory()
            cpu_pct = psutil.cpu_percent(interval=None)
            per_cpu = psutil.cpu_percent(percpu=True)
            io_counters = psutil.disk_io_counters()
            net_counters = psutil.net_io_counters()

            # Process list sampling
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    p_info = p.info
                    p_info['is_background'] = not (p_info['name'].endswith(".exe") and ("chrome" in p_info['name'].lower() or "code" in p_info['name'].lower() or "idea" in p_info['name'].lower()))
                    procs.append(p_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Sort top processes by CPU and RAM
            top_procs = sorted(procs, key=lambda x: (x.get('cpu_percent', 0) or 0) + (x.get('memory_percent', 0) or 0), reverse=True)[:15]

            return {
                "timestamp": time.time(),
                "memory": {
                    "total_gb": round(mem.total / (1024**3), 2),
                    "used_gb": round(mem.used / (1024**3), 2),
                    "percent": mem.percent,
                    "available_gb": round(mem.available / (1024**3), 2)
                },
                "cpu": {
                    "total_percent": cpu_pct,
                    "cores": len(per_cpu),
                    "per_core": per_cpu
                },
                "io": {
                    "read_bytes": io_counters.read_bytes if io_counters else 0,
                    "write_bytes": io_counters.write_bytes if io_counters else 0,
                    "is_busy": False
                },
                "network": {
                    "bytes_sent": net_counters.bytes_sent if net_counters else 0,
                    "bytes_recv": net_counters.bytes_recv if net_counters else 0,
                    "is_high": False
                },
                "processes": top_procs
            }
        else:
            # Fallback mock telemetry if psutil is missing
            return {
                "timestamp": time.time(),
                "memory": {"total_gb": 16.0, "used_gb": 8.0, "percent": 50.0, "available_gb": 8.0},
                "cpu": {"total_percent": 25.0, "cores": 8, "per_core": [25.0]*8},
                "io": {"read_bytes": 1000, "write_bytes": 2000, "is_busy": False},
                "network": {"bytes_sent": 500, "bytes_recv": 1200, "is_high": False},
                "processes": [
                    {"pid": 101, "name": "systemd", "cpu_percent": 1.0, "memory_percent": 0.5, "is_background": True},
                    {"pid": 204, "name": "browser_tab", "cpu_percent": 15.0, "memory_percent": 12.0, "is_background": False}
                ]
            }

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

        if arbitration_result.get("decision_made"):
            self.total_heals += 1
            self.prevented_crashes += 1

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
            "agent_proposals": [p.to_dict() for p in all_proposals],
            "arbitration": arbitration_result,
            "stats": {
                "total_heals": self.total_heals,
                "prevented_crashes": self.prevented_crashes,
                "status": "PROTECTED"
            },
            "history": self.history_logs[:10]
        }

guardian_daemon = GuardianDaemon()
