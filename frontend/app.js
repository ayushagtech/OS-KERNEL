document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const cpuTotalPct = document.getElementById('cpu-total-pct');
    const cpuBar = document.getElementById('cpu-bar');
    const ramUsedPct = document.getElementById('ram-used-pct');
    const ramBar = document.getElementById('ram-bar');
    const ramUsedGb = document.getElementById('ram-used-gb');
    const ramTotalGb = document.getElementById('ram-total-gb');
    const ioReadBytes = document.getElementById('io-read-bytes');
    const ioWriteBytes = document.getElementById('io-write-bytes');
    const totalHealsCount = document.getElementById('total-heals-count');
    const crashesPreventedCount = document.getElementById('crashes-prevented-count');
    const processTableBody = document.getElementById('process-table-body');
    const terminalBody = document.getElementById('negotiation-terminal');

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
        if (!bytes || bytes === 0) return '0 KB/s';
        const k = 1024;
        const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    // Render Telemetry Data
    function renderTelemetry(data) {
        if (!data || !data.telemetry) return;

        const tel = data.telemetry;
        const memory = tel.memory || {};
        const cpu = tel.cpu || {};
        const io = tel.io || {};

        // CPU Update
        const cpuPct = Math.round(cpu.total_percent || 0);
        cpuTotalPct.textContent = `${cpuPct}%`;
        cpuBar.style.width = `${cpuPct}%`;

        // RAM Update
        const ramPct = Math.round(memory.percent || 0);
        ramUsedPct.textContent = `${ramPct}%`;
        ramBar.style.width = `${ramPct}%`;
        ramUsedGb.textContent = `${memory.used_gb || 0} GB`;
        ramTotalGb.textContent = `${memory.total_gb || 0} GB`;

        // I/O Update
        ioReadBytes.textContent = formatBytes(io.read_bytes);
        ioWriteBytes.textContent = formatBytes(io.write_bytes);

        // Stats Update
        if (data.stats) {
            totalHealsCount.textContent = data.stats.total_heals || 0;
            crashesPreventedCount.textContent = data.stats.prevented_crashes || 0;
        }

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
        if (arb.decision_made && arb.winning_proposal) {
            const winner = arb.winning_proposal;
            appendTerminalLog(`[STATE ASSERTION] Anomaly detected by ${winner.agent_name}`, 'assertion');
            appendTerminalLog(`[COLLABORATIVE BID] Proposed ${winner.action} on ${winner.process_name} (PID ${winner.target_pid})`, 'proposal');
            appendTerminalLog(`[CONSENSUS WINNER] Executed ${winner.action} | Net Utility: +${winner.net_utility}`, 'winner');
            appendTerminalLog(`[NON-DESTRUCTIVE HOOK] Process state adjusted without crash.`, 'hook');
        }
    }

    // WebSocket Stream Initialization
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
        const socket = new WebSocket(wsUrl);

        socket.onopen = () => {
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
        fetch('/api/status')
            .then(res => res.json())
            .then(data => renderTelemetry(data))
            .catch(err => console.error('Status fetch error:', err));
    }

    // Connect WebSocket
    connectWebSocket();
    setInterval(pollStatus, 2000);

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
