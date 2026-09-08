document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const cpuTotalPct = document.getElementById('cpu-total-pct');
    const cpuBar = document.getElementById('cpu-bar');
    const cpuPressure = document.getElementById('cpu-pressure');
    const ramUsedPct = document.getElementById('ram-used-pct');
    const ramBar = document.getElementById('ram-bar');
    const ramUsedGb = document.getElementById('ram-used-gb');
    const ramTotalGb = document.getElementById('ram-total-gb');
    const memoryPressure = document.getElementById('memory-pressure');
    const swapPressure = document.getElementById('swap-pressure');
    const ioReadBytes = document.getElementById('io-read-bytes');
    const ioWriteBytes = document.getElementById('io-write-bytes');
    const ioPressure = document.getElementById('io-pressure');
    const networkPressure = document.getElementById('network-pressure');
    const predictionSummary = document.getElementById('prediction-summary');
    const totalHealsCount = document.getElementById('total-heals-count');
    const successfulMitigationsCount = document.getElementById('successful-mitigations-count');
    const processTableBody = document.getElementById('process-table-body');
    const terminalBody = document.getElementById('negotiation-terminal');
    const pressureSummary = document.getElementById('pressure-summary');
    const activeAgentsSummary = document.getElementById('active-agents-summary');
    const consensusSummary = document.getElementById('consensus-summary');
    const selectionReason = document.getElementById('selection-reason');
    const actionSummary = document.getElementById('action-summary');
    const protectionSummary = document.getElementById('protection-summary');
    const adaptiveMemorySummary = document.getElementById('adaptive-memory-summary');
    const adaptiveMemoryDetail = document.getElementById('adaptive-memory-detail');
    const bargainingOutcome = document.getElementById('bargaining-outcome');
    const proposalBidsList = document.getElementById('proposal-bids-list');
    const negotiationList = document.getElementById('negotiation-list');
    const cascadeList = document.getElementById('cascade-list');
    const rejectedList = document.getElementById('rejected-list');
    let lastArbitrationKey = '';
    let webSocketAvailable = false;
    let fallbackPollTimer = null;

    // Stress buttons
    const btnStressMem = document.getElementById('btn-stress-mem');
    const btnStressCpu = document.getElementById('btn-stress-cpu');
    const btnStressStop = document.getElementById('btn-stress-stop');

    // Terminal Logging Helper
    function appendTerminalLog(message, type = 'info') {
        const line = document.createElement('div');
        line.className = `term-line ${type}`;
        const timeStr = new Date().toLocaleTimeString();
        line.textContent = `[${timeStr}] ${message}`;
        terminalBody.appendChild(line);
        
        // Auto scroll to bottom
        terminalBody.scrollTop = terminalBody.scrollHeight;

        // Keep last 100 lines
        while (terminalBody.childNodes.length > 100) {
            terminalBody.removeChild(terminalBody.firstChild);
        }
    }

    // Format Bytes helper
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function formatPressure(value) {
        return typeof value === 'number' && Number.isFinite(value)
            ? `${Math.round(value * 100)}%` : 'N/A';
    }

    function setListItems(container, items, fallback) {
        container.innerHTML = '';
        (items.length ? items : [fallback]).forEach(item => {
            const li = document.createElement('li');
            li.textContent = item;
            container.appendChild(li);
        });
    }

    function renderBargaining(data, tel) {
        const arb = data.arbitration || {};
        const proposals = Array.isArray(data.agent_proposals) ? data.agent_proposals : [];
        const plan = arb.consensus_plan || null;
        const selectedPlan = arb.selected_plan || null;
        const barter = arb.barter || {};
        const adaptive = Array.isArray(data.experience?.adaptive_memory)
            ? data.experience.adaptive_memory : [];
        const executed = Array.isArray(arb.actions_executed) ? arb.actions_executed : [];
        const rejected = Array.isArray(arb.rejected_alternatives) ? arb.rejected_alternatives : [];
        const conflicts = Array.isArray(arb.cross_domain_conflicts) ? arb.cross_domain_conflicts : [];
        const rounds = Array.isArray(arb.negotiation_rounds) ? arb.negotiation_rounds : [];
        const cpuPct = Math.round((tel.cpu || {}).total_percent || 0);
        const ramPct = Math.round((tel.memory || {}).percent || 0);
        const pressureFlags = [];

        if ((tel.io || {}).is_busy) pressureFlags.push('I/O busy');
        if ((tel.network || {}).is_high) pressureFlags.push('network high');
        pressureSummary.textContent = `CPU ${cpuPct}% · RAM ${ramPct}%${pressureFlags.length ? ` · ${pressureFlags.join(', ')}` : ''}`;

        const activeAgents = [...new Set(proposals.map(proposal => proposal.agent_name).filter(Boolean))];
        activeAgentsSummary.textContent = activeAgents.length
            ? `${activeAgents.length} active bidder${activeAgents.length === 1 ? '' : 's'}: ${activeAgents.join(', ')}`
            : 'All agents monitoring; no active bids';

        consensusSummary.textContent = selectedPlan
            ? `${(selectedPlan.actions || []).join(' + ') || 'Plan'} · utility ${Number(selectedPlan.utility_score || 0).toFixed(3)}`
            : plan
            ? `${plan.action || 'Action'} · PID ${plan.pid ?? 'unknown'} · score ${Number(plan.combined_score || 0).toFixed(1)}`
            : 'No plan selected';
        selectionReason.textContent = selectedPlan
            ? `Relief ${(Number(selectedPlan.resource_relief || 0) * 100).toFixed(0)}% vs debt ${(Number(barter.relief_debt || 0) * 100).toFixed(0)}%; disruption ${(Number(selectedPlan.disruption_cost || 0) * 100).toFixed(0)}%`
            : arb.reason || plan?.round_3_resolution || 'No arbitration result yet';

        const currentAction = executed[executed.length - 1] || null;
        const actionPid = currentAction?.pid ?? plan?.pid ?? arb.winning_proposal?.target_pid;
        actionSummary.textContent = currentAction
            ? `${currentAction.action || 'Action'} · PID ${currentAction.pid ?? 'unknown'}`
            : actionPid ? `Pending / guarded · PID ${actionPid}` : 'No action';
        const targetProcess = (tel.processes || []).find(process => process.pid === actionPid) || {};
        const disruption = targetProcess.user_disruption_score;
        const protection = targetProcess.protection_reason || targetProcess.process_category || 'No process context available';
        protectionSummary.textContent = `User disruption: ${disruption == null ? 'unavailable' : `${Math.round(disruption * 100)}%`} · ${protection}`;
        const bestHistory = adaptive[0];
        adaptiveMemorySummary.textContent = bestHistory
            ? `${bestHistory.action}: ${(Number(bestHistory.historical_adjustment || 0)).toFixed(2)}`
            : 'Cold start';
        adaptiveMemoryDetail.textContent = bestHistory
            ? `${bestHistory.count} outcomes · ${(Number(bestHistory.weighted_effectiveness || 0) * 100).toFixed(0)}% effective · ${(Number(bestHistory.success_rate || 0) * 100).toFixed(0)}% success`
            : 'No recorded outcomes';

        const outcome = arb.final_outcome || (arb.decision_made ? 'action_executed' : 'awaiting decision');
        const escalation = /remains critical|after LOWER_PRIORITY|after affinity/i.test(arb.reason || '') ? 'escalated' :
            (/safety|no longer critical|cooldown/i.test(outcome + (arb.reason || '')) ? 'stopped early' : 'not escalated');
        bargainingOutcome.textContent = `${outcome.replace(/_/g, ' ')} · ${escalation}`;

        setListItems(proposalBidsList, proposals.slice(0, 6).map(proposal =>
            `${proposal.agent_name || 'Agent'}: ${proposal.action || 'proposal'} · PID ${proposal.target_pid ?? '—'} · utility ${Number(proposal.net_utility || 0).toFixed(1)}`
        ), 'Awaiting proposals');
        setListItems(negotiationList, [
            ...conflicts.map(conflict => `Conflict PID ${conflict.pid}: ${(conflict.actions || []).join(' vs ') || 'competing actions'}`),
            ...rounds.map(round => `PID ${round.pid}: ${round.rounds || 0} bounded negotiation rounds`),
            ...(barter.conflicts || []).map(conflict => `Barter conflict: ${conflict}`),
        ], 'No conflicts or negotiation rounds reported');
        setListItems(cascadeList, [
            ...executed.map(step => `${step.action || 'Action'} on PID ${step.pid ?? '—'}: ${step.reason || step.result?.message || 'completed'}`),
            ...(executed.length ? [`Final observed outcome: ${currentAction?.observation?.status || outcome} · ${escalation}`] : [
                `Cascade state: ${outcome.replace(/_/g, ' ')} · ${escalation}`
            ]),
        ], 'Mitigation has not started');
        setListItems(rejectedList, rejected.slice(0, 5).map(candidate =>
            `${candidate.action || 'Alternative'} · PID ${candidate.pid ?? '—'} · disruption ${Number(candidate.factors?.user_disruption || 0).toFixed(0)}% · held for safer plan`
        ), 'No alternatives rejected');
    }

    // Render Telemetry Data
    function renderTelemetry(data) {
        if (!data || !data.telemetry) return;

        const tel = data.telemetry;
        const memory = tel.memory || {};
        const cpu = tel.cpu || {};
        const io = tel.io || {};
        const network = tel.network || {};
        const resourceState = data.resource_state || tel.resource_state || {};
        const predictions = tel.predictions || {};

        // CPU Update
        const cpuPct = Math.round(cpu.total_percent || 0);
        cpuTotalPct.textContent = `${cpuPct}%`;
        cpuBar.style.width = `${cpuPct}%`;
        cpuPressure.textContent = formatPressure(resourceState.cpu_pressure ?? cpu.pressure);

        // RAM Update
        const ramPct = Math.round(memory.percent || 0);
        ramUsedPct.textContent = `${ramPct}%`;
        ramBar.style.width = `${ramPct}%`;
        ramUsedGb.textContent = `${memory.used_gb || 0} GB`;
        ramTotalGb.textContent = `${memory.total_gb || 0} GB`;
        memoryPressure.textContent = formatPressure(resourceState.memory_pressure ?? memory.pressure);
        swapPressure.textContent = formatPressure(resourceState.swap_pressure);

        // I/O Update
        ioReadBytes.textContent = formatBytes(io.read_bytes);
        ioWriteBytes.textContent = formatBytes(io.write_bytes);
        ioPressure.textContent = formatPressure(resourceState.io_pressure ?? io.pressure);
        networkPressure.textContent = formatPressure(resourceState.network_pressure ?? network.pressure);
        const memoryPrediction = predictions.memory || data.prediction || {};
        const confidence = formatPressure(memoryPrediction.confidence);
        const horizon = typeof memoryPrediction.seconds_to_threshold === 'number'
            ? `${memoryPrediction.seconds_to_threshold.toFixed(1)}s` : 'N/A';
        predictionSummary.textContent = `Memory early warning: ${memoryPrediction.predicted_threshold_crossing ? 'possible crossing' : 'no crossing indicated'} · confidence ${confidence} · ETA ${horizon}`;

        // Stats Update
        if (data.stats) {
            totalHealsCount.textContent = data.stats.total_heals || 0;
            successfulMitigationsCount.textContent = data.stats.successful_mitigations || 0;
        }

        renderBargaining(data, tel);

        // Process Table
        const procs = tel.processes || [];
        processTableBody.innerHTML = '';
        procs.forEach(p => {
            const tr = document.createElement('tr');
            const typeBadge = p.is_background ? '<span class="badge badge-bg">Background</span>' : '<span class="badge badge-fg">Foreground Focus</span>';
            const actionBadge = '<span class="badge badge-action">Protected</span>';

            tr.innerHTML = `
                <td>${p.pid}</td>
                <td><strong>${p.name}</strong></td>
                <td>${(p.cpu_percent || 0).toFixed(1)}%</td>
                <td>${(p.memory_percent || 0).toFixed(1)}%</td>
                <td>${typeBadge}</td>
                <td>${actionBadge}</td>
            `;
            processTableBody.appendChild(tr);
        });

        // Arbitration Logging
        const arb = data.arbitration || {};
        const arbitrationKey = `${arb.final_outcome || ''}:${arb.winning_proposal?.target_pid || ''}:${arb.execution_result?.action || ''}`;
        if (arb.decision_made && arb.winning_proposal && arbitrationKey !== lastArbitrationKey) {
            const winner = arb.winning_proposal;
            appendTerminalLog(`[STATE ASSERTION] Anomaly detected by ${winner.agent_name}`, 'assertion');
            appendTerminalLog(`[COLLABORATIVE BID] Proposed ${winner.action} on ${winner.process_name} (PID ${winner.target_pid})`, 'proposal');
            appendTerminalLog(`[CONSENSUS WINNER] Executed ${winner.action} | Net Utility: +${winner.net_utility}`, 'winner');
            appendTerminalLog(`[NON-DESTRUCTIVE HOOK] Control result recorded and observed.`, 'hook');
            lastArbitrationKey = arbitrationKey;
        }
    }

    // WebSocket Stream Initialization
    function stopFallbackPolling() {
        if (fallbackPollTimer) {
            clearInterval(fallbackPollTimer);
            fallbackPollTimer = null;
        }
    }

    function startFallbackPolling() {
        if (fallbackPollTimer || webSocketAvailable) return;
        pollStatus();
        fallbackPollTimer = setInterval(pollStatus, 2000);
    }

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
        const socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            webSocketAvailable = true;
            stopFallbackPolling();
            appendTerminalLog('[WEBSOCKET CONNECTED] Real-time telemetry feed active.', 'info');
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                renderTelemetry(data);
            } catch (err) {
                console.error('Error parsing telemetry JSON:', err);
            }
        };

        socket.onclose = () => {
            webSocketAvailable = false;
            startFallbackPolling();
            appendTerminalLog('[WEBSOCKET CLOSED] Reconnecting in 3 seconds...', 'info');
            setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = (err) => {
            console.error('WebSocket Error:', err);
            socket.close();
        };
    }

    // HTTP Fallback Polling
    function pollStatus() {
        if (webSocketAvailable) return;
        fetch('/api/status')
            .then(res => res.json())
            .then(data => renderTelemetry(data))
            .catch(err => console.error('Status fetch error:', err));
    }

    // Connect WebSocket
    connectWebSocket();

    // Stress Button Event Bindings
    btnStressMem.addEventListener('click', () => {
        appendTerminalLog('[STRESS STUDIO] Triggering Synthetic Memory Leak (+500MB)...', 'assertion');
        fetch('/api/stress/memory', { method: 'POST' })
            .then(res => res.json())
            .then(res => appendTerminalLog(`[STRESSOR ACTIVE] Memory Leak triggered. Target: ${res.allocated_target_mb}MB`, 'proposal'));
    });

    btnStressCpu.addEventListener('click', () => {
        appendTerminalLog('[STRESS STUDIO] Triggering Synthetic CPU Spike (30s)...', 'assertion');
        fetch('/api/stress/cpu', { method: 'POST' })
            .then(res => res.json())
            .then(res => appendTerminalLog(`[STRESSOR ACTIVE] CPU Spike active for ${res.duration_sec}s`, 'proposal'));
    });

    btnStressStop.addEventListener('click', () => {
        appendTerminalLog('[STRESS STUDIO] Stopping all active synthetic stressors...', 'info');
        fetch('/api/stress/stop', { method: 'POST' })
            .then(res => res.json())
            .then(res => appendTerminalLog('[STRESSOR STOPPED] All synthetic stressors deactivated.', 'info'));
    });
});
