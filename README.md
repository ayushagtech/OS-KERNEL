# AGENTIC OS KERNEL GUARDIAN
> Autonomous Self-Healing Operating System Daemon & Multi-Agent Resource Barter Framework

---

## 🌟 Overview
**Agentic OS Kernel Guardian** replaces rigid operating system heuristics and destructive fault mechanisms (like the Linux OOM Killer) with a **Decentralized Multi-Agent Negotiation Ecosystem**. 

When system resource contention occurs, 5 domain-specific AI agents (Memory, CPU, I/O, Network, Security) barter resources over an IPC bus. The **Decision Arbiter Agent** evaluates proposals using a global utility objective function ($Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$) and executes non-destructive kernel control hooks (`cgroups v2`, process freezing, priority shifting, CPU affinity clamping) without terminating active applications or causing unsaved user data loss.

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
   - Observe the Arbiter executing non-destructive process freezing/priority shifting in **under 1.5 seconds** with **0 application crashes**.

---

## 📜 Patent Information
Detailed patent specification documents including field of invention, prior art defects, detailed architecture description, state machine flowcharts, and 5 claims are located in [`docs/PATENT_SPECIFICATION.md`](file:///c:/Users/AYUSH/OneDrive/Desktop/OS%20PROJECT/docs/PATENT_SPECIFICATION.md).
