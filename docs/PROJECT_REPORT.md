# OPERATING SYSTEMS PROJECT REPORT (BCSE303P)

## PROJECT TITLE
**AGENTIC OS KERNEL GUARDIAN: DECENTRALIZED MULTI-AGENT OS RESOURCE MANAGEMENT AND AUTONOMOUS SELF-HEALING FRAMEWORK**

---

## PROJECT METADATA
* **Institution**: Vellore Institute of Technology (VIT), Vellore
* **School**: School of Computer Science and Engineering (SCOPE)
* **Course Code & Name**: BCSE303P - Operating Systems
* **Faculty Supervisor**: Dr. Perepi Rajarajeshwari
* **Academic Term**: Fall Semester 2026-2027
* **Team Members**:
  1. **Ayush Agarwal** (Reg No: 24BCE2629)
  2. **Bhargav Dey** (Reg No: 24BCE2627)

---

## ABSTRACT
Traditional operating system resource management mechanisms rely on static scheduling heuristics and aggressive fault resolution policies (e.g., the Linux Out-Of-Memory / OOM killer). These conventional approaches suffer from subsystem isolation, cross-subsystem blindness, and destructive process termination that causes unsaved user data loss during severe resource contention. This project presents **Agentic OS Kernel Guardian**, an autonomous self-healing framework powered by a Decentralized Multi-Agent Negotiation Architecture. Operating as a lightweight daemon, the framework deploys 5 domain-specific AI agents (Memory, CPU, I/O, Network, Security) and a Decision Arbiter to dynamically barter system resources. By evaluating proposals using a closed-loop Utility Function ($Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$) and executing available non-destructive process controls (process freezing, priority shifting, and CPU affinity clamping), the system reports measured post-action feedback. Crash-prevention and recovery-rate claims require controlled experiments and are not asserted here.

---

## 1. INTRODUCTION & PROBLEM STATEMENT
Operating systems manage critical shared resources including CPU, RAM, Disk I/O, and Network sockets. Current operating system implementations suffer from three major flaws:

1. **Brute-Force Fault Resolution**: Invocations of the OOM killer terminate high-memory processes using simplistic scoring without user focus context or application state awareness.
2. **Subsystem Isolation**: Memory paging operates independently of CPU scheduling and I/O management, frequently causing CPU thrashing.
3. **Passive Metric Telemetry**: Tools such as Task Manager or `top` display performance graphs but do not autonomously take preventive action before a crash occurs.

---

## 2. PROPOSED AGENTIC ARCHITECTURE

The framework introduces a two-tier execution pipeline:

### 2.1 Multi-Agent Ecosystem
* **Memory Agent**: Monitors RAM usage and swap pressure; advocates for background process suspension. zRAM compression is not currently implemented.
* **CPU Agent**: Tracks core load and context switching; balances scheduling priorities (`nice`) and thread affinity.
* **File System (I/O) Agent**: Tracks disk queue latency; throttles background indexers.
* **Network Agent**: Tracks socket traffic; throttles non-essential background downloads.
* **Security Agent**: Differentiates legitimate application spikes from unauthorized crypto-miners or rogue background tasks.
* **Decision Arbiter Agent**: Evaluates proposals using a global utility objective function.

### 2.2 Multi-Agent Negotiation Protocol (Patentable Core)
1. **State Assertion**: A subsystem agent broadcasts an active bottleneck (e.g., Memory Agent reports 92% RAM consumption).
2. **Collaborative Bidding**: Neighboring agents submit trade-offs based on current capacity headroom.
3. **Consensus Optimization**: The Arbiter selects the action maximizing:
   $$Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$$

---

## 3. IMPLEMENTATION DETAILS

### 3.1 Technology Stack
* **Language**: Python 3.10+
* **Backend Services**: FastAPI, Uvicorn, WebSockets, `psutil`
* **Control Primitives**: OS Control Hooks (Win32 / Linux `cgroups v2`, `SIGSTOP`/`SIGCONT`, `nice` priority shift, thread affinity)
* **Frontend Dashboard**: HTML5, CSS3 Glassmorphism, JavaScript ES6, WebSockets

### 3.2 Key Modules
* `backend/daemon.py`: Orchestrates telemetry collection and agent negotiation cycles.
* `backend/agents/`: Implements domain agents and the Decision Arbiter consensus engine.
* `backend/hooks/process_control.py`: Provides non-destructive process control functions.
* `backend/simulator/stress_gen.py`: Generates synthetic memory leaks and CPU spikes for live testing.

---

## 4. EXPERIMENTAL RESULTS & DEMONSTRATION

### 4.1 Test Scenarios
1. **Scenario A (Memory Exhaustion)**: Synthetic memory leak (+500MB buffer allocation).
   * *Traditional OS Result*: OOM killer terminates active background application abruptly.
   * *Kernel Guardian Result*: Memory Agent asserts state $\rightarrow$ Arbiter may freeze a verified background task (`SIGSTOP`) $\rightarrow$ the result is reported with measured feedback. Crash prevention is not claimed without a controlled experiment.
2. **Scenario B (CPU Spike)**: Rogue high-load background process (95% CPU).
   * *Kernel Guardian Result*: CPU Agent and Security Agent may propose priority and affinity controls for a verified background process; the daemon reports whether measured feedback shows improvement. Foreground responsiveness is not asserted without a controlled experiment.

### 4.2 Performance Metrics
* Recovery time and daemon overhead require measurement in a controlled benchmark; no validated values are claimed by the current implementation.

---

## 5. CONCLUSION & PATENT POTENTIAL
The Agentic OS Kernel Guardian successfully demonstrates an intelligent, autonomous, self-healing operating system management suite. The novel Multi-Agent Barter Protocol and Non-Destructive Mitigation Cascade Engine provide a strong foundation for patent filing under intellectual property regulations.

---

## REFERENCES
1. Silberschatz, A., Galvin, P. B., & Gagne, G. (2018). *Operating System Concepts* (10th ed.). Wiley.
2. Linux Kernel Documentation. *Control Group v2 (cgroup2)*. https://www.kernel.org/doc/Documentation/cgroup-v2.txt
3. Wooldridge, M. (2009). *An Introduction to MultiAgent Systems* (2nd ed.). Wiley.
