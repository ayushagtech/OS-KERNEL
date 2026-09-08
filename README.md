# AGENTIC OS KERNEL GUARDIAN
> Autonomous Self-Healing Operating System Daemon & Multi-Agent Resource Barter Framework

---

## 🌟 Overview
**Agentic OS Kernel Guardian** supplements rigid operating system heuristics with a **Decentralized Multi-Agent Negotiation Ecosystem**.

When system resource contention occurs, 5 domain-specific agents (Memory, CPU, I/O, Network, Security) submit proposals. The **Decision Arbiter Agent** evaluates proposals using a global utility objective function ($Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$) and executes available non-destructive controls (process freezing, priority shifting, and CPU affinity clamping). zRAM compression is currently unavailable and is not selected.

---

## 🚀 Quick Start (Running the Dashboard & Daemon)

### 1. Requirements
- Python 3.8+
- Windows or Linux OS

### 2. Launch the System
Run the launcher script in your terminal:
```bash
python run_guardian.py
```
This script will automatically:
1. Verify required Python packages (`psutil`, `fastapi`, `uvicorn`, `websockets`).
2. Start the FastAPI backend and WebSocket telemetry server on `http://127.0.0.1:5000`.
3. Open the **Interactive Web Dashboard** in your default browser.

---

## 📁 Repository Structure
```
OS PROJECT/
├── backend/
│   ├── main.py                # FastAPI server + WebSocket endpoint
│   ├── daemon.py              # Guardian Daemon orchestration
│   ├── agents/                # Multi-Agent Ecosystem (Memory, CPU, I/O, Net, Sec, Arbiter)
│   ├── hooks/                 # Non-destructive process control primitives
│   └── simulator/             # Synthetic workload stress generator
├── frontend/
│   ├── index.html             # Modern Glassmorphism Web Dashboard
│   ├── styles.css             # Dark-mode styling and animations
│   └── app.js                 # WebSocket client and dashboard logic
├── docs/
│   ├── PATENT_SPECIFICATION.md # Official Patent Specification Draft
│   └── PROJECT_REPORT.md      # VIT Academic Project Report (BCSE303P)
├── requirements.txt           # Dependency specifications
└── run_guardian.py            # Easy 1-click system launcher
```

---

## 🔬 Demonstration & Faculty Evaluation Guide
1. Launch `run_guardian.py` and open the Web Dashboard at `http://127.0.0.1:5000`.
2. Scroll to the **Stress Test & Demonstration Studio** panel.
3. Click **"Trigger Memory Leak (+500MB)"** or **"Trigger CPU Spike (30s)"**.
4. Observe the **Multi-Agent Barter Protocol Console**:
   - Watch the Memory/CPU Agent assert state.
   - Watch collaborative bidding between domain agents.
   - Observe the Arbiter executing an available non-destructive control and reporting measured feedback.

---

## 📜 Patent Information
Detailed patent specification documents including field of invention, prior art defects, detailed architecture description, state machine flowcharts, and 5 claims are located in [`docs/PATENT_SPECIFICATION.md`](file:///c:/Users/AYUSH/OneDrive/Desktop/OS%20PROJECT/docs/PATENT_SPECIFICATION.md).

## Correctness Notes
- Per-process intervention state and process trend samples are keyed by PID plus creation time.
- Bounded pressure and feedback histories are global telemetry histories; they do not apply state to a process.
- The bounded event log contains process IDs for reporting only and is never used as an intervention registry.
- All arbiter-selectable mitigation stages have registered executors. zRAM compression is registered as unavailable and is filtered before scoring.

## Telemetry Model
- CPU pressure is the sustained exponential moving average of normalized utilization; the EMA uses 70% prior value and 30% current value.
- Memory pressure is `0.60 * utilization + 0.25 * unavailable-memory fraction + 0.15 * swap utilization`, clamped to 0..1.
- I/O and network pressure are the maximum measured read/write or send/receive rate divided by configurable extreme-rate thresholds, clamped to 0..1.
- Counter rates use monotonic elapsed time. The first sample, a counter reset, and an interval below 1 ms produce unavailable rates.
- CPU samples use a 250 ms interval. Per-process CPU, memory, I/O, thread count, status, and identity are sampled at most once per second and safely skipped when a process disappears.

## Control Safety
- The arbiter routes actions through `SafetyGovernor`, which validates creation-time identity, critical/foreground protection, capabilities, confidence, cooldowns, failure limits, simultaneous-intervention limits, duration limits, and CPU-reduction limits.
- Linux uses direct psutil-backed OS controls for priority, affinity, and suspend/resume when permissions allow. Linux cgroup v2 availability and writability are reported explicitly; the daemon does not modify the host root cgroup or claim cgroup enforcement when unavailable.
- Windows uses psutil-backed controls only. macOS/other platforms use the generic psutil adapter and report the actual capability result; unsupported operations fail structurally.
- Every successful supported action stores an original-state restoration token. Restoration is idempotent and reports `restoration_failure` when the adapter cannot restore or verify it.

## Cross-Resource Bidding
- Agents emit normalized `ResourceBid` records with explicit resource domains, requested/offered normalized units, expected relief, intervention cost, disruption, confidence, duration in seconds, and telemetry timestamp.
- The arbiter computes relief debt from overall pressure, creates single-bid and compatible two-bid candidate plans, detects same-process and same-domain conflicts, and selects the least disruptive sufficient plan before utility tie-breakers.
- Utility is `0.30 relief + 0.18 stability + 0.12 security + 0.10 reversibility + 0.05 history - 0.12 disruption - 0.08 collateral cost - 0.05 intervention cost`; every term is normalized to 0..1.
- Selected plans are still executed only through `SafetyGovernor`; the API exposes `resource_bids`, `candidate_plans`, `selected_plan`, and `barter` explanation data.

## Pressure Early Warning
- `backend/pressure_predictor.py` maintains bounded histories for CPU, memory, swap, I/O, and network pressure using monotonic sample time.
- Each resource uses least-squares linear slope, recent average, variance, directional consistency, sample count, recency, and residual stability.
- Threshold time is `(threshold - current_pressure) / positive_slope` only when the slope is positive; otherwise it is unavailable.
- Confidence is a bounded combination of sample sufficiency, directional consistency, fit stability, and recency. Prediction requires at least five samples, pressure at least 0.60, confidence at least 0.65, consistent positive trend, and a crossing within 900 seconds.
- A prediction is an early-warning estimate only. It does not predict crashes or guarantee a future event. Predictive proposals still pass through the arbiter and Safety Governor.
