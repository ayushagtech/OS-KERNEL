import threading
import time
import os
import sys
import logging

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("StressSimulator")

class SyntheticWorkloadManager:
    def __init__(self):
        self.active_stressors = {}
        self.stop_events = {}

    def trigger_memory_leak(self, mb_to_allocate: int = 500, duration_sec: int = 30) -> dict:
        """Create bounded, real RAM pressure and release it after the duration."""
        if "mem_leak" in self.active_stressors and self.active_stressors["mem_leak"].is_alive():
            return {"status": "active", "message": "Memory leak stressor already running."}

        requested_mb = max(1, int(mb_to_allocate))
        duration_sec = max(1, int(duration_sec))
        if psutil:
            available_mb = max(1, int(psutil.virtual_memory().available / (1024 * 1024)))
            # Never consume more than 10% of currently available RAM, and cap
            # the demonstration workload even on machines with ample memory.
            safe_limit_mb = min(512, max(1, int(available_mb * 0.10)))
        else:
            # Conservative fallback when available-memory information is absent.
            safe_limit_mb = 128
        allocation_mb = min(requested_mb, safe_limit_mb)
        stop_evt = threading.Event()
        self.stop_events["mem_leak"] = stop_evt

        def _mem_leak_worker():
            buffers = []
            page_size = 4096
            chunk_size = 16 * 1024 * 1024
            target_bytes = allocation_mb * 1024 * 1024
            deadline = time.monotonic() + duration_sec
            allocated_bytes = 0
            logger.info("[STRESSOR] Starting %s MB memory pressure for %s seconds.", allocation_mb, duration_sec)
            try:
                while (not stop_evt.is_set() and allocated_bytes < target_bytes
                       and time.monotonic() < deadline):
                    remaining = target_bytes - allocated_bytes
                    chunk = bytearray(min(chunk_size, remaining))
                    # Writing one byte per page forces the OS to commit physical
                    # pages instead of leaving a merely reserved virtual range.
                    for offset in range(0, len(chunk), page_size):
                        chunk[offset] = 1
                    buffers.append(chunk)
                    allocated_bytes += len(chunk)
                # Keep strong references alive until the bounded stress period
                # expires, or until the existing Stop control is used.
                remaining_seconds = max(0.0, deadline - time.monotonic())
                stop_evt.wait(remaining_seconds)
            except MemoryError:
                logger.warning("[STRESSOR] Memory pressure stopped before target due to MemoryError.")
            finally:
                buffers.clear()
                logger.info("[STRESSOR] Memory pressure released after %.1f seconds.", duration_sec)

        thread = threading.Thread(target=_mem_leak_worker, daemon=True)
        thread.start()
        self.active_stressors["mem_leak"] = thread
        return {"status": "started", "type": "Memory Leak", "allocated_target_mb": allocation_mb,
                "requested_target_mb": requested_mb, "duration_sec": duration_sec}

    def trigger_cpu_spike(self, duration_sec: int = 30) -> dict:
        """Simulates high CPU load."""
        if "cpu_spike" in self.active_stressors and self.active_stressors["cpu_spike"].is_alive():
            return {"status": "active", "message": "CPU spike stressor already running."}

        stop_evt = threading.Event()
        self.stop_events["cpu_spike"] = stop_evt

        def _cpu_worker():
            logger.info("[STRESSOR] Starting CPU Spike Simulation...")
            start_t = time.time()
            while not stop_evt.is_set() and (time.time() - start_t < duration_sec):
                _ = [x**2 for x in range(5000)]
            logger.info("[STRESSOR] CPU Spike simulation finished.")

        thread = threading.Thread(target=_cpu_worker, daemon=True)
        thread.start()
        self.active_stressors["cpu_spike"] = thread
        return {"status": "started", "type": "CPU Spike", "duration_sec": duration_sec}

    def stop_stressor(self, name: str) -> dict:
        if name in self.stop_events:
            self.stop_events[name].set()
            return {"status": "stopped", "stressor": name}
        return {"status": "not_found", "stressor": name}

    def stop_all_stressors(self) -> dict:
        stopped = []
        for name, evt in self.stop_events.items():
            evt.set()
            stopped.append(name)
        return {"status": "all_stopped", "stopped": stopped}

workload_manager = SyntheticWorkloadManager()
