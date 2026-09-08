"""Platform-neutral process-control contracts and concrete adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import platform
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

from backend.process_identity import ProcessIdentity


@dataclass
class ControlResult:
    success: bool
    action: str
    process_identity: Optional[ProcessIdentity]
    mechanism: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    reversible: bool = False
    restoration_token: Optional[Dict[str, Any]] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "success" if self.success else "error",
            "success": self.success,
            "pid": self.process_identity.pid if self.process_identity else None,
            "action": self.action,
            "process_identity": self.process_identity.to_dict() if self.process_identity else None,
            "mechanism": self.mechanism,
            "error": self.error,
            "error_type": self.error_type,
            "reversible": self.reversible,
            "restoration_token": self.restoration_token,
            "restore_state": self.restoration_token or {},
            "message": self.message,
        }


class ControlAdapter(ABC):
    """Interface implemented by platform-specific control adapters."""

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def lower_priority(self, identity: ProcessIdentity) -> ControlResult:
        raise NotImplementedError

    @abstractmethod
    def restore_priority(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        raise NotImplementedError

    @abstractmethod
    def clamp_affinity(self, identity: ProcessIdentity, cpus: list[int]) -> ControlResult:
        raise NotImplementedError

    @abstractmethod
    def restore_affinity(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        raise NotImplementedError

    @abstractmethod
    def suspend(self, identity: ProcessIdentity) -> ControlResult:
        raise NotImplementedError

    @abstractmethod
    def resume(self, identity: ProcessIdentity) -> ControlResult:
        raise NotImplementedError

    def throttle_io(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        return ControlResult(False, "THROTTLE_IO", identity, self.__class__.__name__,
                             error="I/O throttling is unavailable on this adapter",
                             error_type="UnsupportedAction")

    def control_memory(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        return ControlResult(False, "CONTROL_MEMORY", identity, self.__class__.__name__,
                             error="Memory control is unavailable on this adapter",
                             error_type="UnsupportedAction")


class PsutilControlAdapter(ControlAdapter):
    """Direct psutil controls used only where the platform exposes them."""

    mechanism = "psutil"

    def _process(self, identity: ProcessIdentity):
        if psutil is None:
            raise RuntimeError("psutil is required")
        process = psutil.Process(identity.pid)
        if not identity.matches_process(process):
            raise RuntimeError("Process identity mismatch")
        return process

    def _result(self, action: str, identity: ProcessIdentity, fn, token=None) -> ControlResult:
        try:
            fn()
            return ControlResult(True, action, identity, self.mechanism,
                                 reversible=token is not None, restoration_token=token,
                                 message=f"{action} applied using {self.mechanism}")
        except Exception as error:
            return ControlResult(False, action, identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def lower_priority(self, identity: ProcessIdentity) -> ControlResult:
        try:
            process = self._process(identity)
            original = process.nice()
            target = (psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt"
                      else min(original + 10, 19))
            result = self._result("LOWER_PRIORITY", identity, lambda: process.nice(target),
                                  {"priority": original})
            return result
        except Exception as error:
            return ControlResult(False, "LOWER_PRIORITY", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def restore_priority(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        try:
            process = self._process(identity)
            def restore():
                process.nice(token["priority"])
                if process.nice() != token["priority"]:
                    raise RuntimeError("Priority restoration verification failed")
            return self._result("RESTORE_PRIORITY", identity, restore)
        except Exception as error:
            return ControlResult(False, "RESTORE_PRIORITY", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def clamp_affinity(self, identity: ProcessIdentity, cpus: list[int]) -> ControlResult:
        try:
            process = self._process(identity)
            original = process.cpu_affinity()
            return self._result("CLAMP_AFFINITY", identity,
                                lambda: process.cpu_affinity(cpus), {"affinity": original})
        except Exception as error:
            return ControlResult(False, "CLAMP_AFFINITY", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def affinity_reduction(self, identity: ProcessIdentity, target_cpus: list[int]) -> Optional[float]:
        try:
            current = self._process(identity).cpu_affinity()
            return max(0.0, 1.0 - len(target_cpus) / len(current)) if current else None
        except Exception:
            return None

    def restore_affinity(self, identity: ProcessIdentity, token: Dict[str, Any]) -> ControlResult:
        try:
            process = self._process(identity)
            def restore():
                process.cpu_affinity(token["affinity"])
                if process.cpu_affinity() != token["affinity"]:
                    raise RuntimeError("Affinity restoration verification failed")
            return self._result("RESTORE_AFFINITY", identity, restore)
        except Exception as error:
            return ControlResult(False, "RESTORE_AFFINITY", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def suspend(self, identity: ProcessIdentity) -> ControlResult:
        try:
            process = self._process(identity)
            return self._result("SUSPEND", identity, process.suspend, {"suspended": True})
        except Exception as error:
            return ControlResult(False, "SUSPEND", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def resume(self, identity: ProcessIdentity) -> ControlResult:
        try:
            process = self._process(identity)
            return self._result("RESUME", identity, process.resume)
        except Exception as error:
            return ControlResult(False, "RESUME", identity, self.mechanism,
                                 error=str(error), error_type=type(error).__name__)

    def capabilities(self) -> Dict[str, Any]:
        return {"platform": platform.system(), "mechanism": self.mechanism,
                "available": psutil is not None,
                "cgroups_v2": False,
                "privileged": False}


class LinuxControlAdapter(PsutilControlAdapter):
    """Linux adapter; cgroup v2 is detected but never assumed or faked."""

    mechanism = "linux-psutil"

    def capabilities(self) -> Dict[str, Any]:
        cgroup_root = "/sys/fs/cgroup"
        cgroup_v2 = os.path.exists(os.path.join(cgroup_root, "cgroup.controllers"))
        guardian_path = os.path.join(cgroup_root, "guardian")
        return {"platform": "Linux", "mechanism": self.mechanism,
                "available": psutil is not None, "cgroups_v2": cgroup_v2,
                "guardian_cgroup_path": guardian_path,
                "guardian_cgroup_writable": os.access(cgroup_root, os.W_OK),
                "privileged": getattr(os, "geteuid", lambda: 1)() == 0}


class WindowsControlAdapter(PsutilControlAdapter):
    """Windows adapter using psutil; no simulated cgroup support."""

    mechanism = "windows-psutil"


def create_control_adapter() -> ControlAdapter:
    if platform.system() == "Linux":
        return LinuxControlAdapter()
    if platform.system() == "Windows":
        return WindowsControlAdapter()
    return PsutilControlAdapter()
