"""Stable process identity helpers built from PID and creation time."""

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float

    @classmethod
    def from_process(cls, process: Any) -> "ProcessIdentity":
        return cls(pid=int(process.pid), create_time=float(process.create_time()))

    @classmethod
    def from_mapping(cls, value: Optional[Dict[str, Any]]) -> Optional["ProcessIdentity"]:
        if not value or value.get("pid") is None or value.get("create_time") is None:
            return None
        return cls(pid=int(value["pid"]), create_time=float(value["create_time"]))

    def matches_process(self, process: Any) -> bool:
        try:
            return (int(process.pid) == self.pid
                    and math.isclose(float(process.create_time()), self.create_time,
                                     rel_tol=0.0, abs_tol=1e-6))
        except (AttributeError, TypeError, ValueError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {"pid": self.pid, "create_time": self.create_time}
