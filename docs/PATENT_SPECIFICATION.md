# PATENT SPECIFICATION

## TITLE OF THE INVENTION
**SYSTEM AND METHOD FOR NON-DESTRUCTIVE OPERATING SYSTEM RESOURCE MANAGEMENT USING A DECENTRALIZED MULTI-AGENT BARTER PROTOCOL AND CLOSED-LOOP UTILITY OPTIMIZATION**

---

## INVENTORS
1. **AYUSH AGARWAL** (Vellore Institute of Technology)
2. **BHARGAV DEY** (Vellore Institute of Technology)

---

## FIELD OF THE INVENTION
The present invention relates generally to computer operating systems and resource scheduling architectures. More specifically, the invention relates to an autonomous, self-healing operating system daemon that replaces rigid kernel heuristics with a decentralized multi-agent resource negotiation protocol, preventing abrupt application crashes and memory thrashing through non-destructive control primitives.

---

## BACKGROUND AND PRIOR ART
Modern operating systems (e.g., Linux, Microsoft Windows, Apple macOS) manage hardware resources—such as Central Processing Unit (CPU) cycles, Random Access Memory (RAM), Disk Input/Output (I/O) bandwidth, and Network Sockets—using static, deterministic scheduling algorithms and hardcoded kernel heuristics.

While effective under steady-state operating conditions, existing operating system resource management architectures suffer from three critical technical flaws:

1. **Brute-Force Destructive Fault Resolution**: When system RAM is exhausted, emergency kernel routines (such as the Linux Out-Of-Memory / OOM killer) abruptly terminate processes using simple metric scoring (e.g., highest memory consumption). These mechanisms lack application awareness and user context, frequently terminating active integrated development environments (IDEs), web browsers with unsaved user state, or compilation tasks.
2. **Subsystem Isolation and Cross-Subsystem Blindness**: Kernel domain managers operate in isolated silos. The virtual memory manager initiates aggressive page swapping without consulting current CPU load, frequently triggering CPU thrashing where the processor spends more time executing context switches and page faults than performing productive application work.
3. **Passive Telemetry Without Autonomous Repair**: Conventional performance monitors (e.g., Task Manager, `top`, Activity Monitor) merely display visual metrics or write error logs. They lack autonomous, closed-loop control mechanisms to dynamically reconfigure process priorities or pause non-essential background tasks before system instability or panic occurs.

---

## SUMMARY OF THE INVENTION
To overcome the aforementioned limitations, the present invention discloses an **Agentic OS Kernel Guardian** framework comprising:

1. **Domain-Specific AI Subsystem Agents**: Specialized software agents representing specific system domains (Memory Agent, CPU Agent, File System/IO Agent, Network Agent, Security Agent).
2. **Multi-Agent Resource Barter Protocol**: A structured Inter-Process Communication (IPC) bidding mechanism wherein domain agents evaluate system bottlenecks, assert resource states, and submit trade-off proposals.
3. **Decision Arbiter and Closed-Loop Utility Engine**: An arbiter module that evaluates agent proposals against a global utility objective function defined as:
   $$Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$$
4. **Hierarchical Non-Destructive Control Hooks**: A cascade of non-lethal OS control primitives (process freezing/unfreezing, priority shifting, and CPU affinity clamping) executed without process termination. zRAM compression is not currently implemented.

---

## DETAILED DESCRIPTION & ARCHITECTURE

```
                                  +------------------------------------+
                                  |    Telemetry Collector (psutil)    |
                                  +-----------------+------------------+
                                                    |
                                                    v
                     +------------------------------+------------------------------+
                     |                 Domain-Specific AI Agents                  |
                     |  +----------------+  +----------------+  +---------------+  |
                     |  |  Memory Agent  |  |   CPU Agent    |  |  I/O Agent    |  |
                     |  +-------+--------+  +-------+--------+  +-------+-------+  |
                     |          |                   |                   |          |
                     |          +-------------------+-------------------+          |
                     |                              |                              |
                     |               State Assertions & Trade-off Bids             |
                     +------------------------------+------------------------------+
                                                    |
                                                    v
                                  +-----------------+------------------+
                                  |     Decision Arbiter Agent        |
                                  |   Utility = ΔHealth - ΔDisruption |
                                  +-----------------+------------------+
                                                    |
                                                    v
                                  +-----------------+------------------+
                                  |   Non-Destructive Control Hooks   |
                                  |  (Freeze, Lower Nice, Clamp CPU)  |
                                  +------------------------------------+
```

### 1. State Assertion & Collaborative Bidding
When a domain agent detects that its respective subsystem metric crosses a pre-configured anomaly threshold (e.g., RAM > 85%), it broadcasts a **State Assertion** over the local IPC bus. Neighboring agents analyze their current capacity headroom and generate trade-off **Proposals**.

### 2. Utility-Based Decision Arbitration
Each proposal calculates an expected system health gain and estimates a user disruption penalty based on whether the target process is in active foreground user focus or running in the background. The Decision Arbiter selects the winning action sequence that maximizes positive Net Utility.

### 3. Non-Destructive Execution
Decisions are mapped to fine-grained operating system primitives:
- **Process Freezing**: Halts execution threads without purging process state (`SIGSTOP` / `cgroup.freeze`), preserving unsaved user data.
- **Priority Shifting**: Demotes background process execution to idle scheduling classes (`nice +10` / `SCHED_IDLE`).
- **Affinity Clamping**: Restricts high-load background tasks to a single CPU core, keeping remaining cores responsive for active user input.

---

## PATENT CLAIMS

**We Claim:**

1. An autonomous operating system resource management system comprising:
   - A telemetry module configured to monitor real-time system resource metrics across a plurality of hardware subsystems;
   - A plurality of domain-specific software agents, each configured to monitor a specific hardware subsystem and generate resource allocation proposals upon detection of resource contention;
   - A decision arbiter module configured to calculate a net utility score for each generated proposal using a closed-loop objective function balancing system stability gains against user disruption penalties; and
   - A control execution module configured to execute non-destructive kernel control primitives based on the proposal selected by said decision arbiter.

2. The system of claim 1, wherein said closed-loop objective function is evaluated according to:
   $$Utility = \Delta \text{System Health} - \Delta \text{User Disruption}$$
   wherein proposals yielding a negative net utility score are automatically disqualified.

3. The system of claim 1, wherein said non-destructive control primitives comprise process freezing, scheduling priority demotion, and CPU core affinity restriction.

4. The system of claim 1, further comprising a security agent configured to inspect process digital signatures, execution hashes, and window focus context to differentiate legitimate application resource spikes from unauthorized crypto-mining or malware execution.

5. A method for closed-loop self-healing resource management in an operating system, the method comprising:
   - Collecting real-time telemetry representing CPU, virtual memory, disk I/O, and network bandwidth utilization;
   - Broadcasting state assertion messages over an inter-process communication bus upon detecting a metric anomaly;
   - Receiving collaborative trade-off bids from a plurality of domain-specific agents;
   - Selecting a highest-utility proposal; and
   - Applying non-destructive process throttling to a target process without invoking process termination signals.
