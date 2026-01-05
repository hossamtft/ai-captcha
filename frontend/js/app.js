const API = '';

const state = {
    temporal: { challenge: null, isHolding: false, pressTime: 0, startTime: 0, animFrame: null },
    behavioural: { challenge: null, isActive: false, trajectory: [], visited: [], startTime: 0, timerInterval: null }
};

async function api(endpoint, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return (await fetch(API + endpoint, opts)).json();
}

function showModal(success, title, msg) {
    document.getElementById('modal-icon').textContent = success ? '✓' : '✗';
    document.getElementById('modal-icon').className = 'modal-icon ' + (success ? 'success' : 'error');
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-message').textContent = msg;
    document.getElementById('result-modal').classList.add('active');
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', e => {
            e.preventDefault();
            const id = link.dataset.section;
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            if (id === 'temporal') loadTemporal();
            if (id === 'behavioural') loadBehavioural();
        });
    });

    document.querySelectorAll('.challenge-card').forEach(c => {
        c.addEventListener('click', () => document.querySelector(`[data-section="${c.dataset.challenge}"]`).click());
    });

    const btn = document.getElementById('temporal-btn');
    btn.addEventListener('mousedown', startTemporal);
    btn.addEventListener('mouseup', endTemporal);
    btn.addEventListener('mouseleave', () => { if (state.temporal.isHolding) endTemporal(); });
    btn.addEventListener('touchstart', e => { e.preventDefault(); startTemporal(); });
    btn.addEventListener('touchend', e => { e.preventDefault(); endTemporal(); });

    document.getElementById('temporal-retry').addEventListener('click', loadTemporal);
    document.getElementById('canvas-overlay').addEventListener('click', startBehavioural);
    document.getElementById('behavioural-canvas').addEventListener('mousemove', handleMove);
    document.getElementById('behavioural-retry').addEventListener('click', loadBehavioural);
    document.getElementById('modal-close').addEventListener('click', () => document.getElementById('result-modal').classList.remove('active'));
});

async function loadTemporal() {
    const c = await api('/api/challenges/temporal');
    state.temporal = { challenge: c, isHolding: false, pressTime: 0, startTime: 0, animFrame: null, visualTime: 0 };

    const zone = document.getElementById('temporal-zone');
    zone.style.left = (c.zone_start / c.total_duration * 100) + '%';
    zone.style.width = (c.zone_width / c.total_duration * 100) + '%';
    zone.classList.remove('zone-active');

    document.getElementById('temporal-indicator').style.left = '0%';
    document.getElementById('timer-text').textContent = '0.00s';
    document.getElementById('duration-label').textContent = (c.total_duration / 1000).toFixed(1) + 's';
    document.getElementById('temporal-btn').classList.remove('holding');
    document.getElementById('temporal-btn').querySelector('.btn-text').textContent = 'HOLD';
    document.getElementById('temporal-confidence-fill').style.width = '0%';
    document.getElementById('temporal-confidence-text').textContent = '--';
}

function startTemporal() {
    if (!state.temporal.challenge || state.temporal.isHolding) return;
    state.temporal.isHolding = true;
    state.temporal.pressTime = Date.now();
    state.temporal.startTime = performance.now();
    state.temporal.visualTime = 0;
    state.temporal.lastFrame = performance.now();
    document.getElementById('temporal-btn').classList.add('holding');
    document.getElementById('temporal-btn').querySelector('.btn-text').textContent = 'HOLDING...';
    animateTemporal();
}

function animateTemporal() {
    if (!state.temporal.isHolding) return;
    const c = state.temporal.challenge;
    const now = performance.now();
    const frameDelta = now - state.temporal.lastFrame;
    state.temporal.lastFrame = now;

    const realElapsed = now - state.temporal.startTime;

    let cumulativeTime = 0;
    let currentSpeed = 1;
    for (const seg of c.speed_segments) {
        if (realElapsed < cumulativeTime + seg.duration / seg.speed) {
            currentSpeed = seg.speed;
            break;
        }
        cumulativeTime += seg.duration / seg.speed;
    }

    state.temporal.visualTime += frameDelta * currentSpeed;
    const visualProgress = Math.min(state.temporal.visualTime / c.total_duration, 1);

    document.getElementById('temporal-indicator').style.left = (visualProgress * 100) + '%';
    document.getElementById('timer-text').textContent = (realElapsed / 1000).toFixed(2) + 's';

    const zone = document.getElementById('temporal-zone');
    const visualTimeMs = state.temporal.visualTime;
    const zoneEnd = c.zone_start + c.zone_width;
    if (visualTimeMs >= c.zone_start && visualTimeMs <= zoneEnd) {
        zone.classList.add('zone-active');
    } else {
        zone.classList.remove('zone-active');
    }

    if (visualProgress < 1) {
        state.temporal.animFrame = requestAnimationFrame(animateTemporal);
    } else {
        endTemporal();
    }
}

async function endTemporal() {
    if (!state.temporal.isHolding) return;
    state.temporal.isHolding = false;
    cancelAnimationFrame(state.temporal.animFrame);

    const hold = Date.now() - state.temporal.pressTime;
    document.getElementById('temporal-btn').classList.remove('holding');
    document.getElementById('temporal-btn').querySelector('.btn-text').textContent = 'HOLD';

    const r = await api('/api/challenges/temporal', 'POST', {
        challenge_id: state.temporal.challenge.challenge_id,
        press_time: 0,
        release_time: hold
    });

    // Update confidence bar with accuracy percentage
    const fill = document.getElementById('temporal-confidence-fill');
    const text = document.getElementById('temporal-confidence-text');
    const accuracy = r.accuracy || 0;
    fill.style.width = accuracy + '%';
    text.textContent = accuracy.toFixed(0) + '% Accuracy';

    showModal(r.success, r.success ? 'Perfect!' : 'Missed!', r.message);
}

async function loadBehavioural() {
    if (state.behavioural.timerInterval) clearInterval(state.behavioural.timerInterval);
    const c = await api('/api/challenges/behavioural');
    state.behavioural = { challenge: c, isActive: false, trajectory: [], visited: new Array(c.waypoints.length).fill(false), startTime: 0, timerInterval: null };

    document.getElementById('canvas-overlay').classList.remove('hidden');
    document.getElementById('waypoints-total').textContent = c.waypoints.length;
    document.getElementById('waypoints-visited').textContent = '0';
    document.getElementById('time-elapsed').textContent = '0.0';
    document.getElementById('time-limit').textContent = (c.time_limit / 1000).toFixed(0);
    document.getElementById('confidence-fill').style.width = '0%';
    document.getElementById('confidence-text').textContent = '--% Human';
    drawBehavioural();
}

function startBehavioural() {
    const c = state.behavioural.challenge;
    state.behavioural.isActive = true;
    state.behavioural.trajectory = [];
    state.behavioural.startTime = Date.now();
    document.getElementById('canvas-overlay').classList.add('hidden');

    state.behavioural.timerInterval = setInterval(() => {
        const elapsed = (Date.now() - state.behavioural.startTime) / 1000;
        document.getElementById('time-elapsed').textContent = elapsed.toFixed(1);
        // Time limit disabled for testing
        // if (elapsed * 1000 >= c.time_limit) {
        //     submitBehavioural();
        // }
    }, 100);
}

function handleMove(e) {
    if (!state.behavioural.isActive || !state.behavioural.challenge) return;
    const canvas = document.getElementById('behavioural-canvas');
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (canvas.width / rect.width);
    const y = (e.clientY - rect.top) * (canvas.height / rect.height);
    const t = Date.now() - state.behavioural.startTime;

    state.behavioural.trajectory.push({ x, y, t });

    const c = state.behavioural.challenge;
    // Allow collecting waypoints in any order
    c.waypoints.forEach((wp, i) => {
        if (!state.behavioural.visited[i] && Math.sqrt((x - wp.x) ** 2 + (y - wp.y) ** 2) <= 28) {
            state.behavioural.visited[i] = true;
            document.getElementById('waypoints-visited').textContent = state.behavioural.visited.filter(v => v).length;
        }
    });

    drawBehavioural();

    if (state.behavioural.visited.every(v => v)) {
        submitBehavioural();
    }
}

function drawBehavioural() {
    const canvas = document.getElementById('behavioural-canvas');
    const ctx = canvas.getContext('2d');
    const c = state.behavioural.challenge;
    if (!c) return;

    ctx.fillStyle = '#0d0d15';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < canvas.width; i += 30) {
        ctx.strokeStyle = 'rgba(255,255,255,0.03)';
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i, canvas.height);
        ctx.stroke();
    }
    for (let i = 0; i < canvas.height; i += 30) {
        ctx.beginPath();
        ctx.moveTo(0, i);
        ctx.lineTo(canvas.width, i);
        ctx.stroke();
    }

    if (state.behavioural.trajectory.length > 1) {
        const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
        gradient.addColorStop(0, '#00ff88');
        gradient.addColorStop(1, '#00ccff');
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        ctx.moveTo(state.behavioural.trajectory[0].x, state.behavioural.trajectory[0].y);
        state.behavioural.trajectory.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.stroke();

        ctx.shadowColor = '#00ff88';
        ctx.shadowBlur = 10;
        const last = state.behavioural.trajectory[state.behavioural.trajectory.length - 1];
        ctx.beginPath();
        ctx.arc(last.x, last.y, 6, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.shadowBlur = 0;
    }

    // All unvisited waypoints look the same since order doesn't matter
    c.waypoints.forEach((wp, i) => {
        const visited = state.behavioural.visited[i];

        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 28, 0, Math.PI * 2);
        if (visited) {
            ctx.fillStyle = 'rgba(0,255,136,0.3)';
            ctx.strokeStyle = '#00ff88';
        } else {
            ctx.fillStyle = 'rgba(255,170,0,0.2)';
            ctx.strokeStyle = '#ffaa00';
        }
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 10, 0, Math.PI * 2);
        ctx.fillStyle = visited ? '#00ff88' : '#ffaa00';
        ctx.fill();

        ctx.fillStyle = '#0a0a0f';
        ctx.font = 'bold 12px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(i + 1, wp.x, wp.y);
    });
}

async function submitBehavioural() {
    if (!state.behavioural.isActive) return;
    state.behavioural.isActive = false;
    clearInterval(state.behavioural.timerInterval);

    const r = await api('/api/challenges/behavioural', 'POST', {
        challenge_id: state.behavioural.challenge.challenge_id,
        trajectory: state.behavioural.trajectory
    });

    document.getElementById('confidence-display').classList.add('show');
    document.getElementById('confidence-fill').style.width = (r.confidence || 0) + '%';
    document.getElementById('confidence-text').textContent = (r.confidence || 0) + '% Human';

    showModal(r.success, r.success ? 'Verified!' : 'Failed', r.message);
}
