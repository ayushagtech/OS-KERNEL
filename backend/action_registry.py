"""Authoritative action availability and restoration metadata."""

from typing import Any, Dict


ACTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "LOWER_PRIORITY": {
        "executor": "lower_priority",
        "restorable": True,
        "description": "Lower process scheduling priority.",
    },
    "CLAMP_AFFINITY": {
        "executor": "clamp_affinity",
        "restorable": True,
        "description": "Restrict process CPU affinity.",
    },
    "SUSPEND": {
        "executor": "suspend_process",
        "restorable": True,
        "description": "Suspend a process without terminating it.",
    },
    "RESUME": {
        "executor": "resume_process",
        "restorable": False,
        "description": "Resume a suspended process.",
    },
    "ZRAM_COMPRESS": {
        "executor": None,
        "restorable": False,
        "available": False,
        "description": "Unavailable: no real zRAM control path is implemented.",
    },
}

MITIGATION_STAGES = ("LOWER_PRIORITY", "CLAMP_AFFINITY", "SUSPEND")


def is_executable(action: str) -> bool:
    definition = ACTION_REGISTRY.get(action, {})
    return bool(definition.get("available", True) and definition.get("executor"))
