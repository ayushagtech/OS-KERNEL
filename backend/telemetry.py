"""Measured cross-resource telemetry and explainable pressure scores."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import time

from backend.process_identity import ProcessIdentity

CPU_SAMPLE_INTERVAL = 0.25
PROCESS_SAMPLE_INTERVAL = 1.0
MIN_RATE_INTERVAL = 0.001


def calculate_rate(current: Optional[int], previous: Optional[int], elapsed: float) -> Optional[float]:
    """Calculate a non-negative counter rate, or None when it is not reliable."""
    if current is None or previous is None or elapsed < MIN_RATE_INTERVAL:
        return None
    delta = current - previous
    return None if delta < 0 else delta / elapsed


def threshold_pressure(value: Optional[float], threshold: float) -> Optional[float]:
    """Normalize a measured value against a configured extreme threshold."""
    if value is None or threshold <= 0:
        return None
    return max(0.0, min(1.0, value / threshold))


@dataclass(frozen=True)
class TelemetryThresholds:
    """Configurable extreme-rate thresholds used only for normalization."""
    io_read_bytes_per_sec: float = 50 * 1024 * 1024
    io_write_bytes_per_sec: float = 50 * 1024 * 1024
    network_bytes_per_sec: float = 10 * 1024 * 1024
    network_packets_per_sec: float = 10_000


@dataclass(frozen=True)
class ResourceStateVector:
    cpu_pressure: Optional[float]
    memory_pressure: Optional[float]
    swap_pressure: Optional[float]
    io_pressure: Optional[float]
    network_pressure: Optional[float]
    overall_pressure: Optional[float]
    timestamp: float
    process_count: Optional[int] = None
    foreground_process: Optional[int] = None
    critical_process_count: Optional[int] = None
    telemetry_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class TelemetrySnapshot:
    """One point-in-time snapshot with raw counters, rates, and pressures."""
    timestamp: float
    monotonic_timestamp: float
    cpu_percent: float
    cpu_per_core: tuple
    load_average: Optional[tuple]
    memory_total_bytes: int
    memory_used_bytes: int
    memory_available_bytes: int
    swap_total_bytes: int
    swap_used_bytes: int
    swap_percent: Optional[float]
    disk_read_bytes: Optional[int]
    disk_write_bytes: Optional[int]
    disk_read_ops: Optional[int]
    disk_write_ops: Optional[int]
    network_bytes_sent: Optional[int]
    network_bytes_recv: Optional[int]
    network_packets_sent: Optional[int]
    network_packets_recv: Optional[int]
    disk_read_bytes_per_sec: Optional[float]
    disk_write_bytes_per_sec: Optional[float]
    disk_read_ops_per_sec: Optional[float]
    disk_write_ops_per_sec: Optional[float]
    network_bytes_sent_per_sec: Optional[float]
    network_bytes_recv_per_sec: Optional[float]
    network_packets_sent_per_sec: Optional[float]
    network_packets_recv_per_sec: Optional[float]
    cpu_pressure: Optional[float]
    memory_pressure: Optional[float]
    swap_pressure: Optional[float]
    io_pressure: Optional[float]
    network_pressure: Optional[float]

    @classmethod
    def capture(cls, psutil_module: Any, previous: Optional["TelemetrySnapshot"] = None,
                cpu_interval: float = CPU_SAMPLE_INTERVAL,
                thresholds: TelemetryThresholds = TelemetryThresholds()) -> Optional["TelemetrySnapshot"]:
        if psutil_module is None:
            return None
        memory = psutil_module.virtual_memory()
        swap = psutil_module.swap_memory()
        per_core = tuple(float(value) for value in psutil_module.cpu_percent(
            interval=cpu_interval, percpu=True
        ))
        disk = psutil_module.disk_io_counters()
        network = psutil_module.net_io_counters()
        now = time.monotonic()
        wall_time = time.time()
        elapsed = now - previous.monotonic_timestamp if previous else 0.0

        def counter(source: Any, name: str) -> Optional[int]:
            value = getattr(source, name, None) if source else None
            return int(value) if value is not None else None

        disk_read = counter(disk, "read_bytes")
        disk_write = counter(disk, "write_bytes")
        disk_read_ops = counter(disk, "read_count")
        disk_write_ops = counter(disk, "write_count")
        net_sent = counter(network, "bytes_sent")
        net_recv = counter(network, "bytes_recv")
        packets_sent = counter(network, "packets_sent")
        packets_recv = counter(network, "packets_recv")
        read_rate = calculate_rate(disk_read, previous.disk_read_bytes if previous else None, elapsed)
        write_rate = calculate_rate(disk_write, previous.disk_write_bytes if previous else None, elapsed)
        read_ops_rate = calculate_rate(disk_read_ops, previous.disk_read_ops if previous else None, elapsed)
        write_ops_rate = calculate_rate(disk_write_ops, previous.disk_write_ops if previous else None, elapsed)
        sent_rate = calculate_rate(net_sent, previous.network_bytes_sent if previous else None, elapsed)
        recv_rate = calculate_rate(net_recv, previous.network_bytes_recv if previous else None, elapsed)
        sent_packets_rate = calculate_rate(packets_sent, previous.network_packets_sent if previous else None, elapsed)
        recv_packets_rate = calculate_rate(packets_recv, previous.network_packets_recv if previous else None, elapsed)

        cpu_percent = sum(per_core) / len(per_core) if per_core else 0.0
        memory_percent = memory.used / memory.total * 100.0 if memory.total else None
        swap_percent = getattr(swap, "percent", None)
        memory_pressure = None if memory_percent is None else max(
            0.0, min(1.0, 0.60 * memory_percent / 100.0
                     + 0.25 * (1.0 - memory.available / memory.total)
                     + 0.15 * (float(swap_percent or 0.0) / 100.0)))
        swap_pressure = threshold_pressure(float(swap_percent), 100.0) if swap_percent is not None else None
        io_parts = [threshold_pressure(read_rate, thresholds.io_read_bytes_per_sec),
                    threshold_pressure(write_rate, thresholds.io_write_bytes_per_sec)]
        io_pressure = max((part for part in io_parts if part is not None), default=None)
        network_parts = [threshold_pressure(sent_rate, thresholds.network_bytes_per_sec),
                         threshold_pressure(recv_rate, thresholds.network_bytes_per_sec),
                         threshold_pressure(sent_packets_rate, thresholds.network_packets_per_sec),
                         threshold_pressure(recv_packets_rate, thresholds.network_packets_per_sec)]
        network_pressure = max((part for part in network_parts if part is not None), default=None)
        cpu_pressure = threshold_pressure(cpu_percent, 100.0)
        pressures = [cpu_pressure, memory_pressure, swap_pressure, io_pressure, network_pressure]
        available_pressures = [value for value in pressures if value is not None]
        try:
            load_average = tuple(float(value) for value in psutil_module.getloadavg())
        except (AttributeError, OSError):
            load_average = None
        return cls(
            timestamp=wall_time, monotonic_timestamp=now, cpu_percent=cpu_percent,
            cpu_per_core=per_core, load_average=load_average,
            memory_total_bytes=int(memory.total), memory_used_bytes=int(memory.used),
            memory_available_bytes=int(memory.available), swap_total_bytes=int(getattr(swap, "total", 0) or 0),
            swap_used_bytes=int(getattr(swap, "used", 0) or 0),
            swap_percent=float(swap_percent) if swap_percent is not None else None,
            disk_read_bytes=disk_read, disk_write_bytes=disk_write,
            disk_read_ops=disk_read_ops, disk_write_ops=disk_write_ops,
            network_bytes_sent=net_sent, network_bytes_recv=net_recv,
            network_packets_sent=packets_sent, network_packets_recv=packets_recv,
            disk_read_bytes_per_sec=read_rate, disk_write_bytes_per_sec=write_rate,
            disk_read_ops_per_sec=read_ops_rate, disk_write_ops_per_sec=write_ops_rate,
            network_bytes_sent_per_sec=sent_rate, network_bytes_recv_per_sec=recv_rate,
            network_packets_sent_per_sec=sent_packets_rate,
            network_packets_recv_per_sec=recv_packets_rate,
            cpu_pressure=cpu_pressure, memory_pressure=memory_pressure,
            swap_pressure=swap_pressure, io_pressure=io_pressure,
            network_pressure=network_pressure,
        )

    def to_internal_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


ResourceTelemetrySnapshot = TelemetrySnapshot


def collect_process_telemetry(psutil_module: Any, process_iter: Iterable[Any]) -> List[Dict[str, Any]]:
    """Collect safe per-process data; races are expected and skipped explicitly."""
    processes = []
    for process in process_iter:
        try:
            info = dict(process.info)
            identity = ProcessIdentity.from_process(process)
            info["process_identity"] = identity.to_dict()
            info["status"] = process.status()
            info["thread_count"] = process.num_threads()
            io = process.io_counters()
            info["io_read_bytes"] = getattr(io, "read_bytes", None)
            info["io_write_bytes"] = getattr(io, "write_bytes", None)
            processes.append(info)
        except (psutil_module.NoSuchProcess, psutil_module.AccessDenied,
                psutil_module.ZombieProcess, OSError):
            continue
    return processes
