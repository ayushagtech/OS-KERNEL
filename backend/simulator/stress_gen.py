import threading
import time
import os
import sys
import logging

logger = logging.getLogger("StressSimulator")

class SyntheticWorkloadManager:
    def __init__(self):
        self.active_stressors = {}
        self.stop_events = {}

    def trigger_memory_leak(self, mb_to_allocate: int = 500) -> dict:
        """Simulates a memory leak by allocating memory buffers in background."""
        if "mem_leak" in self.active_stressors and self.active_stressors["mem_leak"].is_alive():
            return {"status": "active", "message": "Memory leak stressor already running."}

        stop_evt = threading.Event()
        self.stop_events["mem_leak"] = stop_evt

        def _mem_leak_worker():
            buffers = []
            logger.info("[STRESSOR] Starting Memory Leak Simulation...")
            allocated = 0
            while not stop_evt.is_set() and allocated < mb_to_allocate:
                try:
                    # Allocate 20MB chunks
                    chunk = bytearray(20 * 1024 * 1024)
                    buffers.append(chunk)
                    allocated += 20
                    time.sleep(0.3)
                except MemoryError:
                    break
            logger.info("[STRESSOR] Memory Leak target reached or stopped.")
            while not stop_evt.is_set():
                time.sleep(1)
            del buffers

        thread = threading.Thread(target=_mem_leak_worker, daemon=True)
        thread.start()
        self.active_stressors["mem_leak"] = thread
        return {"status": "started", "type": "Memory Leak", "allocated_target_mb": mb_to_allocate}

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
