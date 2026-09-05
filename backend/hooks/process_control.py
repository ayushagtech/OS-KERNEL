import os
import sys
import logging
import subprocess

try:
    import psutil
except ImportError:
    psutil = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProcessControl")

class ProcessControlHooks:
    """
    Non-Destructive Control Hooks for Agentic OS Kernel Guardian.
    Provides OS-level process manipulation primitives without abrupt SIGKILL termination.
    Supports Windows (Win32 API/psutil) and Linux (cgroups v2/procfs/psutil).
    """

    @staticmethod
    def suspend_process(pid: int) -> dict:
        """Freezes a process in memory (equivalent to cgroup.freeze / SIGSTOP)."""
        try:
            if psutil:
                proc = psutil.Process(pid)
                proc.suspend()
                logger.info(f"[HOOK] Suspended process PID={pid} ({proc.name()})")
                return {"status": "success", "pid": pid, "action": "SUSPEND", "message": f"Suspended PID {pid}"}
            elif sys.platform == "win32":
                # PowerShell fallback on Windows
                cmd = f"Powershell -Command \"(Get-Process -Id {pid}).Suspend()\""
                subprocess.run(cmd, shell=True, check=True)
                return {"status": "success", "pid": pid, "action": "SUSPEND", "message": f"Suspended PID {pid} via Win32"}
            else:
                os.kill(pid, 19) # SIGSTOP
                return {"status": "success", "pid": pid, "action": "SUSPEND", "message": f"Suspended PID {pid} via SIGSTOP"}
        except Exception as e:
            logger.error(f"[HOOK FAILED] Could not suspend PID={pid}: {e}")
            return {"status": "error", "pid": pid, "action": "SUSPEND", "message": str(e)}

    @staticmethod
    def resume_process(pid: int) -> dict:
        """Resumes a suspended process (equivalent to cgroup.unfreeze / SIGCONT)."""
        try:
            if psutil:
                proc = psutil.Process(pid)
                proc.resume()
                logger.info(f"[HOOK] Resumed process PID={pid} ({proc.name()})")
                return {"status": "success", "pid": pid, "action": "RESUME", "message": f"Resumed PID {pid}"}
            elif sys.platform == "win32":
                cmd = f"Powershell -Command \"(Get-Process -Id {pid}).Resume()\""
                subprocess.run(cmd, shell=True, check=True)
                return {"status": "success", "pid": pid, "action": "RESUME", "message": f"Resumed PID {pid} via Win32"}
            else:
                os.kill(pid, 18) # SIGCONT
                return {"status": "success", "pid": pid, "action": "RESUME", "message": f"Resumed PID {pid} via SIGCONT"}
        except Exception as e:
            logger.error(f"[HOOK FAILED] Could not resume PID={pid}: {e}")
            return {"status": "error", "pid": pid, "action": "RESUME", "message": str(e)}

    @staticmethod
    def lower_priority(pid: int) -> dict:
        """Shifts scheduling priority to idle/below-normal (sched_setattr / nice +10)."""
        try:
            if psutil:
                proc = psutil.Process(pid)
                if sys.platform == "win32":
                    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                else:
                    current_nice = proc.nice()
                    proc.nice(min(current_nice + 10, 19))
                logger.info(f"[HOOK] Throttled priority PID={pid} ({proc.name()})")
                return {"status": "success", "pid": pid, "action": "LOWER_PRIORITY", "message": f"Lowered priority PID {pid}"}
            else:
                return {"status": "error", "pid": pid, "message": "psutil not available for priority adjustment"}
        except Exception as e:
            logger.error(f"[HOOK FAILED] Could not lower priority PID={pid}: {e}")
            return {"status": "error", "pid": pid, "action": "LOWER_PRIORITY", "message": str(e)}

    @staticmethod
    def clamp_affinity(pid: int, cpus: list = [0]) -> dict:
        """Restricts process execution to specific CPU cores (cgroups.cpuset)."""
        try:
            if psutil:
                proc = psutil.Process(pid)
                proc.cpu_affinity(cpus)
                logger.info(f"[HOOK] Clamped CPU affinity for PID={pid} to Cores {cpus}")
                return {"status": "success", "pid": pid, "action": "CLAMP_AFFINITY", "message": f"Clamped PID {pid} to cores {cpus}"}
            else:
                return {"status": "error", "pid": pid, "message": "psutil not available for affinity clamp"}
        except Exception as e:
            logger.error(f"[HOOK FAILED] Could not clamp affinity PID={pid}: {e}")
            return {"status": "error", "pid": pid, "action": "CLAMP_AFFINITY", "message": str(e)}

    @staticmethod
    def simulate_memory_compression(pid: int) -> dict:
        """Simulates zRAM memory page compression on demand for a process."""
        try:
            name = "Process"
            if psutil:
                try:
                    name = psutil.Process(pid).name()
                except Exception:
                    pass
            logger.info(f"[HOOK] Compressed cold memory pages for PID={pid} ({name})")
            return {"status": "success", "pid": pid, "action": "ZRAM_COMPRESS", "message": f"Compressed memory pages for PID {pid}"}
        except Exception as e:
            return {"status": "error", "pid": pid, "action": "ZRAM_COMPRESS", "message": str(e)}
