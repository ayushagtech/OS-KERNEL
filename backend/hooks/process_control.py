import sys
import logging
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None

from backend.process_identity import ProcessIdentity
from backend.telemetry import TelemetrySnapshot
from backend.control_interface import create_control_adapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProcessControl")


class ProcessControlHooks:
    """Non-destructive, best-effort process controls and restoration helpers."""

    adapter = create_control_adapter()

    @staticmethod
    def _error(pid: int, action: str, error: Exception, identity: Optional[ProcessIdentity] = None) -> dict:
        return {"status": "error", "pid": pid, "action": action,
                "error_type": type(error).__name__, "message": str(error),
                "process_identity": identity.to_dict() if identity else None}

    @staticmethod
    def _resolve_process(pid: int, expected_identity: Optional[ProcessIdentity] = None):
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError(f"Invalid PID: {pid}")
        if psutil is None:
            raise RuntimeError("psutil is required to verify process identity")
        process = psutil.Process(pid)
        current_identity = ProcessIdentity.from_process(process)
        if expected_identity and current_identity != expected_identity:
            raise RuntimeError(
                f"Process identity mismatch: expected {expected_identity.to_dict()}, "
                f"found {current_identity.to_dict()}"
            )
        return process, current_identity

    @staticmethod
    def _success(pid: int, action: str, message: str, identity: ProcessIdentity,
                 restore_state: Optional[dict] = None) -> dict:
        return {"status": "success", "pid": pid, "action": action, "message": message,
                "process_identity": identity.to_dict(),
                "restore_state": {**(restore_state or {}), "process_identity": identity.to_dict()}}

    @staticmethod
    def suspend_process(pid: int, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Freeze a process; the returned state can be restored with RESUME."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.suspend(identity).to_dict()

    @staticmethod
    def resume_process(pid: int, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Resume a suspended process (cgroup unfreeze/SIGCONT equivalent)."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.resume(identity).to_dict()

    @staticmethod
    def lower_priority(pid: int, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Lower priority and retain the exact previous priority for restoration."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.lower_priority(identity).to_dict()

    @staticmethod
    def clamp_affinity(pid: int, cpus=None, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Clamp CPU affinity while retaining the prior affinity for restoration."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.clamp_affinity(identity, [0] if cpus is None else cpus).to_dict()

    @staticmethod
    def restore_priority(pid: int, priority, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Restore priority captured before guardian intervention."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.restore_priority(identity, {"priority": priority}).to_dict()

    @staticmethod
    def restore_affinity(pid: int, affinity: list, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Restore CPU affinity captured before guardian intervention."""
        identity = process_identity or ProcessIdentity(pid, -1.0)
        return ProcessControlHooks.adapter.restore_affinity(identity, {"affinity": affinity}).to_dict()

    @staticmethod
    def restore_process_state(pid: int, state: dict, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Restore any state returned by a prior guardian action."""
        identity = process_identity or ProcessIdentity.from_mapping(state.get("process_identity"))
        results = []
        if state.get("suspended"):
            results.append(ProcessControlHooks.resume_process(pid, identity))
        if "priority" in state:
            results.append(ProcessControlHooks.restore_priority(pid, state["priority"], identity))
        if "affinity" in state:
            results.append(ProcessControlHooks.restore_affinity(pid, state["affinity"], identity))
        if not results:
            return {"status": "skipped", "pid": pid, "action": "RESTORE", "message": "No restorable state"}
        status = "success" if all(result.get("status") == "success" for result in results) else "error"
        return {"status": status, "pid": pid, "action": "RESTORE", "results": results,
            "process_identity": identity.to_dict() if identity else None}

    @staticmethod
    def observe_process(pid: int, process_identity: Optional[ProcessIdentity] = None) -> dict:
        """Return a best-effort post-action observation without changing state."""
        try:
            if not psutil:
                return {"status": "unavailable", "pid": pid, "message": "psutil not available"}
            proc, identity = ProcessControlHooks._resolve_process(pid, process_identity)
            return {"status": "success", "pid": pid, "process_identity": identity.to_dict(),
                    "cpu_percent": proc.cpu_percent(interval=None),
                    "memory_percent": proc.memory_percent(), "status_detail": proc.status()}
        except Exception as e:
            return {"status": "unavailable", "pid": pid, "error_type": type(e).__name__,
                    "message": str(e), "process_identity": process_identity.to_dict() if process_identity else None}

    @staticmethod
    def observe_system() -> dict:
        """Capture a lightweight post-action resource snapshot without control."""
        try:
            if not psutil:
                return {"status": "unavailable", "message": "psutil not available"}
            snapshot = TelemetrySnapshot.capture(psutil)
            if snapshot is None:
                return {"status": "unavailable", "message": "psutil not available"}
            values = snapshot.to_internal_dict()
            return {"status": "success", **values,
                    "memory_percent": (values["memory_used_bytes"] / values["memory_total_bytes"] * 100
                                       if values["memory_total_bytes"] else 0.0)}
        except Exception as e:
            return {"status": "unavailable", "error_type": type(e).__name__, "message": str(e)}
