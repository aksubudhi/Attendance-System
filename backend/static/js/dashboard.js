let ws = null;
let stats = {
    entry: { faces: 0, recognized: 0 },
    exit: { faces: 0, recognized: 0 }
};

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    ws.onopen = function() {
        updateStatus('connected', 'System Connected');
    };
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.type === 'frame') {
            handleFrame(data);
        } else if (data.type === 'attendance') {
            handleAttendance(data);
        }
    };
    
    ws.onclose = function() {
        updateStatus('disconnected', 'System Disconnected');
        document.querySelectorAll('.btn').forEach(btn => btn.classList.remove('active'));
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
}

function updateStatus(status, text) {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    
    statusDot.className = `status-dot ${status}`;
    statusText.textContent = text;
}

function handleFrame(data) {
    const feedImg = document.getElementById(data.camera + '-feed');
    feedImg.src = 'data:image/jpeg;base64,' + data.image;
    
    stats[data.camera].faces = data.faces_count || 0;
    updateStatsDisplay(data.camera);
}

function updateStatsDisplay(camera) {
    document.getElementById(`${camera}-faces`).textContent = stats[camera].faces;
    document.getElementById(`${camera}-recognized`).textContent = stats[camera].recognized;
}

function handleAttendance(data) {
    const camera = data.event_type === 'IN' ? 'entry' : 'exit';
    stats[camera].recognized++;
    updateStatsDisplay(camera);
    
    addAttendanceEntry(data);
}

function addAttendanceEntry(data) {
    const log = document.getElementById('attendance-log');
    
    const emptyState = log.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    
    const entry = document.createElement('div');
    entry.className = `log-entry entry-${data.event_type.toLowerCase()}`;
    
    const time = new Date(data.timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    const confidencePercent = (data.confidence * 100).toFixed(1);
    
    entry.innerHTML = `
        <div class="log-details">
            <strong>${data.name || 'Unknown'}</strong>
            <div class="log-meta">
                <span>ID: ${data.emp_id}</span>
                <span>•</span>
                <span>${data.event_type}</span>
                <span>•</span>
                <span class="confidence-badge">${confidencePercent}%</span>
            </div>
        </div>
        <div class="log-time">${time}</div>
    `;
    
    log.insertBefore(entry, log.firstChild);
    
    while (log.children.length > 15) {
        log.removeChild(log.lastChild);
    }
    
    entry.style.opacity = '0';
    entry.style.transform = 'translateX(-20px)';
    setTimeout(() => {
        entry.style.transition = 'all 0.3s ease';
        entry.style.opacity = '1';
        entry.style.transform = 'translateX(0)';
    }, 10);
}

function startSystem() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({action: 'start'}));
        document.getElementById('start-btn').classList.add('active');
        document.getElementById('stop-btn').classList.remove('active');
    }
}

function stopSystem() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({action: 'stop'}));
        document.getElementById('stop-btn').classList.add('active');
        document.getElementById('start-btn').classList.remove('active');
        
        document.getElementById('entry-feed').src = '';
        document.getElementById('exit-feed').src = '';
        
        stats = {
            entry: { faces: 0, recognized: 0 },
            exit: { faces: 0, recognized: 0 }
        };
        updateStatsDisplay('entry');
        updateStatsDisplay('exit');
    }
}

window.onload = connectWebSocket;
