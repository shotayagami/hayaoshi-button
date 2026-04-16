let playerColors = [
    "#e63946", "#457b9d", "#2a9d8f", "#e9c46a",
    "#f4a261", "#264653", "#6a4c93", "#1982c4"
];

let ws = null;
let history = [];
let pendingJudgments = [];  // Accumulate judgments within a round
let judgeCooldownUntil = 0;  // Timestamp: disable judge buttons until this time
let state = {
    game_state: "idle",
    players: [],
    press_order: [],
    round: 1,
    points_correct: 10,
    points_incorrect: -5,
    answerer_id: -1,
    answerer_idx: 0,
    num_players: 8,
};

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        ws.send(JSON.stringify({ type: "register", client_type: "admin" }));
        document.getElementById("wsStatus").textContent = "接続中";
        document.getElementById("wsStatus").className = "ws-status ws-connected";
    };
    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleMessage(msg);
    };
    ws.onclose = () => {
        document.getElementById("wsStatus").textContent = "切断中";
        document.getElementById("wsStatus").className = "ws-status ws-disconnected";
        setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
}

function handleMessage(msg) {
    switch (msg.type) {
        case "state":
            state = msg;
            if (msg.colors) playerColors = msg.colors;
            renderAll();
            break;
        case "press":
            state.press_order.push(msg);
            state.game_state = "judging";
            if (msg.is_first) {
                state.answerer_id = msg.player_id;
                state.answerer_idx = 0;
            }
            stopAdminBgm();
            if (shouldPlayLocal()) playAdminSound(`p${msg.player_id + 1}`);
            renderPressOrder();
            renderPlayers();
            renderGameState();
            updateJudgeButtons();
            break;
        case "judgment":
            {
                const pressIdx = state.press_order.findIndex(pr => pr.player_id === msg.player_id);
                msg.order = pressIdx >= 0 ? pressIdx + 1 : 0;
            }
            pendingJudgments.push(msg);
            if (msg.result === "correct") {
                state.game_state = "showing_result";
                finalizeHistory();
            } else {
                // Server holds judgment for ~3s before advancing; block UI too
                judgeCooldownUntil = Date.now() + 3200;
                setTimeout(updateJudgeButtons, 3300);
            }
            state.answerer_id = msg.player_id;
            const p = state.players.find(pl => pl.id === msg.player_id);
            if (p) p.score = msg.new_score;
            if (shouldPlayLocal()) playAdminSound(msg.result);
            renderAll();
            break;
        case "batch_result":
            state.game_state = "showing_result";
            state.answerer_id = -1;
            msg.results.forEach(r => {
                const pl = state.players.find(p => p.id === r.player_id);
                if (pl) pl.score = r.new_score;
            });
            recordBatchHistory(msg.results);
            if (shouldPlayLocal()) {
                playAdminSound(msg.sound === "correct" ? "batch_correct" : "incorrect");
            }
            renderAll();
            break;
        case "next_answerer":
            state.answerer_id = msg.player_id;
            state.answerer_idx = msg.answerer_idx;
            renderPressOrder();
            renderPlayers();
            break;
        case "no_answerer":
            if (msg.revival) {
                // Revival: round continues, don't finalize yet
                state.game_state = "armed";
                state.answerer_id = -1;
                state.press_order = [];
                state.answerer_idx = 0;
            } else {
                state.game_state = "showing_result";
                state.answerer_id = -1;
                finalizeHistory();
            }
            renderAll();
            break;
        case "reset":
            // Record through or pending results
            if (state.round > 0 && !history.find(h => h.round === state.round)) {
                if (pendingJudgments.length > 0) {
                    finalizeHistory();
                } else if (state.press_order.length === 0) {
                    recordThrough();
                }
            }
            pendingJudgments = [];
            state.game_state = msg.game_state;
            state.press_order = [];
            state.answerer_id = -1;
            state.answerer_idx = 0;
            stopAdminBgm();
            updateCountdownButton(-1);
            renderAll();
            break;
        case "player_update":
            const player = state.players.find(pl => pl.id === msg.player_id);
            if (player) {
                player.name = msg.name;
                player.score = msg.score;
            }
            renderPlayers();
            break;
        case "colors_update":
            playerColors = msg.colors;
            renderPlayers();
            break;
        case "jingle":
            if (shouldPlayLocal()) playAdminSound("jingle");
            break;
        case "show_reset_dialog":
            toggleResetDialog();
            break;
        case "countdown":
            if (shouldPlayLocal()) playAdminBgm("countdown");
            updateCountdownButton(msg.value || 10);
            break;
        case "countdown_tick":
            updateCountdownButton(msg.value);
            if (msg.value <= 0) {
                fadeOutAdminBgm(200);
                if (shouldPlayLocal()) playAdminSound("countdown_end");
                updateCountdownButton(0);
            }
            break;
    }
}

function renderAll() {
    renderGameState();
    renderPlayers();
    renderPressOrder();
    renderSettings();
    updateJudgeButtons();
    renderHistory();
}

function renderGameState() {
    const el = document.getElementById("gameState");
    const labels = {
        idle: "IDLE", armed: "ARMED",
        judging: "JUDGING", showing_result: "RESULT"
    };
    el.textContent = labels[state.game_state] || state.game_state;
    el.className = `status-indicator status-${state.game_state}`;
    document.getElementById("roundNum").textContent = state.round;
    const roundInput = document.getElementById("roundInput");
    if (roundInput && document.activeElement !== roundInput) {
        roundInput.value = state.round;
    }
}

function renderPlayers() {
    const tbody = document.getElementById("playerRows");
    tbody.innerHTML = "";
    const numToShow = state.players.length;
    state.players.forEach((p, i) => {
        const tr = document.createElement("tr");
        tr.id = `player-row-${p.id}`;

        const isAnswerer = p.id === state.answerer_id;
        const answererIdx = state.answerer_idx || 0;
        // Find last (most recent) entry for this player
        let lastIdx = -1;
        for (let j = state.press_order.length - 1; j >= 0; j--) {
            if (state.press_order[j].player_id === p.id) { lastIdx = j; break; }
        }
        const isWaiting = lastIdx > answererIdx;
        const isAnswered = lastIdx >= 0 && lastIdx < answererIdx;

        if (isAnswerer) tr.className = "player-first";
        else if (isWaiting) tr.className = "player-pressed";

        const penalty = p.penalty || 0;
        let statusText = "-";
        if (penalty > 0) statusText = `${penalty}問休み`;
        else if (isAnswerer && state.game_state === "showing_result") statusText = "正解!";
        else if (isAnswerer) statusText = "回答中";
        else if (state.game_state === "showing_result") statusText = isWaiting ? "-" : (isAnswered ? "済" : "-");
        else if (isWaiting) {
            const queuePos = lastIdx - answererIdx;
            statusText = `${queuePos}番目`;
        }
        else if (isAnswered) statusText = "済";

        const color = playerColors[i] || "#666";
        tr.innerHTML = `
            <td><span class="player-num" style="background:${color};color:${textColorFor(color)}">${i + 1}</span></td>
            <td><input type="color" value="${color}" onchange="setColor(${i}, this.value)" style="width:30px;height:24px;border:none;padding:0;cursor:pointer"></td>
            <td><input type="text" value="${escapeHtml(p.name)}" onchange="setName(${p.id}, this.value)"></td>
            <td>
                <div class="score-controls">
                    <button class="btn-minus" onclick="adjustScore(${p.id}, -1)">-</button>
                    <span class="score-value">${p.score}</span>
                    <button class="btn-plus" onclick="adjustScore(${p.id}, 1)">+</button>
                </div>
            </td>
            <td>${statusText}</td>
            ${state.batch_mode ? `<td>
                <div class="batch-judge-cell">
                    <label class="batch-judge-label"><input type="checkbox" class="batch-check-correct batch-judge-check" data-pid="${p.id}">正</label>
                    <label class="batch-judge-label"><input type="checkbox" class="batch-check-noanswer batch-judge-check" data-pid="${p.id}">無</label>
                </div>
            </td>` : ''}
        `;
        tbody.appendChild(tr);
    });
}

function renderPressOrder() {
    const el = document.getElementById("pressOrder");
    if (state.press_order.length === 0) {
        el.innerHTML = '<span class="press-empty">待機中...</span>';
        return;
    }
    const firstTs = state.press_order[0].timestamp_us;
    el.innerHTML = state.press_order.map((pr, i) => {
        const player = state.players.find(p => p.id === pr.player_id);
        const name = player ? player.name : `P${pr.player_id + 1}`;
        const diff = i === 0 ? "" : ` (+${((pr.timestamp_us - firstTs) / 1000000).toFixed(3)}秒)`;
        const cls = i === 0 ? "press-first" : "press-other";
        return `<span class="press-item ${cls}">${i + 1}位: ${escapeHtml(name)}${diff}</span>`;
    }).join("");
}

function renderSettings() {
    document.getElementById("pointsCorrect").value = state.points_correct;
    document.getElementById("pointsIncorrect").value = state.points_incorrect;
    document.getElementById("numPlayers").value = state.players.length;
    document.getElementById("revival").checked = !!state.revival;
    document.getElementById("maxAccepts").value = state.max_accepts || 0;
    document.getElementById("jingleAutoArm").checked = !!state.jingle_auto_arm;
    document.getElementById("countdownAutoStop").checked = !!state.countdown_auto_stop;
    document.getElementById("penaltyRounds").value = state.penalty_rounds || 0;
    document.getElementById("batchMode").checked = !!state.batch_mode;
    renderBatchPoints();
    document.getElementById("batchUseOrder").checked = !!state.batch_use_order;
    if (state.batch_incorrect !== undefined) {
        const bi = document.getElementById("batchIncorrect");
        if (document.activeElement !== bi) bi.value = state.batch_incorrect;
    }
    if (state.batch_noanswer !== undefined) {
        const bn = document.getElementById("batchNoanswer");
        if (document.activeElement !== bn) bn.value = state.batch_noanswer;
    }
    // Show/hide batch settings
    document.getElementById("batchSettings").classList.toggle("hidden", !state.batch_mode);
    document.getElementById("batchOrderSettings").classList.toggle("hidden", !state.batch_use_order);
    document.getElementById("batchColHeader").classList.toggle("hidden", !state.batch_mode);
}

function renderBatchPoints() {
    const container = document.getElementById("batchPointsContainer");
    const n = state.players.length;
    const points = state.batch_points || [];
    // Rebuild if player count changed
    if (container.children.length !== n) {
        container.innerHTML = "";
        for (let i = 0; i < n; i++) {
            const wrap = document.createElement("span");
            wrap.className = "batch-rank";
            wrap.innerHTML = `<span class="batch-rank-label">${i + 1}着</span><input type="number" class="batch-rank-input" data-rank="${i}" onchange="sendSettings()">`;
            container.appendChild(wrap);
        }
    }
    // Update values (skip if user is editing)
    for (let i = 0; i < n; i++) {
        const input = container.querySelector(`[data-rank="${i}"]`);
        if (input && document.activeElement !== input) {
            const fallback = points.length > 0 ? points[points.length - 1] : 0;
            input.value = points[i] !== undefined ? points[i] : fallback;
        }
    }
}

function updateJudgeButtons() {
    const inCooldown = Date.now() < judgeCooldownUntil;
    const canJudge = state.game_state === "judging" && !inCooldown;
    const batchReady = state.batch_mode && state.game_state === "armed";
    document.getElementById("btnCorrect").disabled = !(canJudge || batchReady);
    document.getElementById("btnIncorrect").disabled = !(canJudge || batchReady);
}

// Actions
function sendJingle() {
    ws && ws.send(JSON.stringify({ type: "jingle" }));
}

function sendCountdown() {
    ws && ws.send(JSON.stringify({ type: "countdown" }));
}

function sendArm() {
    ws && ws.send(JSON.stringify({ type: "arm" }));
}

function sendStop() {
    ws && ws.send(JSON.stringify({ type: "stop" }));
}

function sendReset() {
    ws && ws.send(JSON.stringify({ type: "reset" }));
}

function showResetDialog() {
    document.getElementById("resetDialog").classList.add("show");
    document.getElementById("roundInput").value = state.round;
}

function hideResetDialog() {
    document.getElementById("resetDialog").classList.remove("show");
}

function toggleResetDialog() {
    const dlg = document.getElementById("resetDialog");
    if (dlg.classList.contains("show")) {
        hideResetDialog();
    } else {
        showResetDialog();
    }
}

function doReset() {
    sendReset();
    hideResetDialog();
}

function doResetPenalty() {
    ws && ws.send(JSON.stringify({ type: "clear_penalty" }));
    hideResetDialog();
}

function doResetScore() {
    ws && ws.send(JSON.stringify({ type: "reset_scores" }));
    hideResetDialog();
}

function doResetRound() {
    ws && ws.send(JSON.stringify({ type: "reset_round" }));
    hideResetDialog();
}

function adjustRound(delta) {
    const input = document.getElementById("roundInput");
    const current = parseInt(input.value);
    const base = isNaN(current) ? (state.round || 0) : current;
    const newVal = Math.max(0, base + delta);
    input.value = newVal;
    ws && ws.send(JSON.stringify({ type: "set_round", value: newVal }));
}

function setRound(value) {
    const newVal = Math.max(0, value);
    ws && ws.send(JSON.stringify({ type: "set_round", value: newVal }));
}

function doResetAll() {
    ws && ws.send(JSON.stringify({ type: "reset_scores" }));
    ws && ws.send(JSON.stringify({ type: "clear_penalty" }));
    ws && ws.send(JSON.stringify({ type: "reset_round" }));
    history = [];
    pendingJudgments = [];
    sendReset();
    hideResetDialog();
}

function sendJudge(result) {
    if (state.batch_mode && (state.game_state === "armed" || state.game_state === "judging")) {
        const correctChecks = document.querySelectorAll(".batch-check-correct:checked");
        const noanswerChecks = document.querySelectorAll(".batch-check-noanswer:checked");
        const correctIds = Array.from(correctChecks).map(cb => parseInt(cb.dataset.pid));
        const noanswerIds = Array.from(noanswerChecks).map(cb => parseInt(cb.dataset.pid));
        ws && ws.send(JSON.stringify({
            type: "batch_judge",
            correct_ids: correctIds,
            noanswer_ids: noanswerIds,
            sound: result
        }));
        return;
    }
    ws && ws.send(JSON.stringify({ type: "judge", result }));
}

function setName(playerId, name) {
    ws && ws.send(JSON.stringify({ type: "set_name", player_id: playerId, name }));
}

function setColor(index, color) {
    playerColors[index] = color;
    ws && ws.send(JSON.stringify({ type: "set_colors", colors: playerColors }));
}

function adjustScore(playerId, delta) {
    const player = state.players.find(p => p.id === playerId);
    if (player) {
        ws && ws.send(JSON.stringify({ type: "set_score", player_id: playerId, score: player.score + delta }));
    }
}

function sendSettings() {
    const npVal = parseInt(document.getElementById("numPlayers").value);
    const pcVal = parseInt(document.getElementById("pointsCorrect").value);
    const piVal = parseInt(document.getElementById("pointsIncorrect").value);
    const np = isNaN(npVal) ? 8 : npVal;
    const pc = isNaN(pcVal) ? 10 : pcVal;
    const pi = isNaN(piVal) ? -5 : piVal;
    const rv = document.getElementById("revival").checked;
    const ma = parseInt(document.getElementById("maxAccepts").value) || 0;
    const jaa = document.getElementById("jingleAutoArm").checked;
    const cas = document.getElementById("countdownAutoStop").checked;
    const pr = parseInt(document.getElementById("penaltyRounds").value) || 0;
    const bm = document.getElementById("batchMode").checked;
    const buo = document.getElementById("batchUseOrder").checked;
    const bpInputs = document.querySelectorAll("#batchPointsContainer .batch-rank-input");
    const bp = Array.from(bpInputs).map(inp => parseInt(inp.value) || 0);
    const biVal = parseInt(document.getElementById("batchIncorrect").value);
    const bnVal = parseInt(document.getElementById("batchNoanswer").value);
    const bi = isNaN(biVal) ? -5 : biVal;
    const bn = isNaN(bnVal) ? 0 : bnVal;
    ws && ws.send(JSON.stringify({
        type: "settings", num_players: np, points_correct: pc, points_incorrect: pi,
        revival: rv, max_accepts: ma, jingle_auto_arm: jaa, countdown_auto_stop: cas, penalty_rounds: pr,
        batch_mode: bm, batch_use_order: buo, batch_points: bp,
        batch_incorrect: bi, batch_noanswer: bn
    }));
}

function onFileSelected() {
    const fileInput = document.getElementById("soundFile");
    const nameEl = document.getElementById("fileName");
    if (fileInput.files.length) {
        nameEl.textContent = fileInput.files[0].name;
        nameEl.style.color = "#eee";
    } else {
        nameEl.textContent = "未選択";
        nameEl.style.color = "#888";
    }
}

async function uploadSound() {
    const target = document.getElementById("soundTarget").value;
    const fileInput = document.getElementById("soundFile");
    const statusEl = document.getElementById("uploadStatus");

    if (!fileInput.files.length) {
        statusEl.textContent = "ファイルを選択してください";
        statusEl.style.color = "#e76f51";
        return;
    }

    const file = fileInput.files[0];
    if (file.size > 200000) {
        statusEl.textContent = "ファイルが大きすぎます (200KB以下)";
        statusEl.style.color = "#e76f51";
        return;
    }

    statusEl.textContent = "アップロード中...";
    statusEl.style.color = "#888";

    try {
        const resp = await fetch(`/api/upload/${target}.mp3`, {
            method: "POST",
            body: file,
        });
        const result = await resp.json();
        if (result.status === "ok") {
            statusEl.textContent = "完了!";
            statusEl.style.color = "#2d6a4f";
        } else {
            statusEl.textContent = result.message;
            statusEl.style.color = "#e76f51";
        }
    } catch (e) {
        statusEl.textContent = "アップロード失敗";
        statusEl.style.color = "#e76f51";
    }
}

// Audio - preload for instant playback
const adminAudioCache = {};
let adminBgm = null;
const SOUND_FILES = [
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8",
    "correct", "incorrect", "jingle", "countdown", "countdown_end", "batch_correct"
];

async function preloadAdminSounds() {
    for (const name of SOUND_FILES) {
        try {
            const resp = await fetch(`sounds/${name}.mp3`);
            if (resp.ok) {
                const blob = await resp.blob();
                adminAudioCache[name] = URL.createObjectURL(blob);
            }
        } catch (e) {}
    }
    console.log(`Admin audio cache: ${Object.keys(adminAudioCache).length} files`);
}

function getAdminAudioUrl(name) {
    return adminAudioCache[name] || `sounds/${name}.mp3`;
}

function shouldPlayLocal() {
    return document.getElementById("audioAdmin").checked;
}

function shouldPlayDisplay() {
    return document.getElementById("audioDisplay").checked;
}

function shouldPlayDfplayer() {
    return document.getElementById("audioDfplayer").checked;
}

function onAudioModeChange() {
    const displayEnabled = shouldPlayDisplay();
    const dfplayerEnabled = shouldPlayDfplayer();
    ws && ws.send(JSON.stringify({
        type: "audio_mode",
        display: displayEnabled,
        dfplayer: dfplayerEnabled,
    }));
}

function unlockAdminAudio() {
    const s = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=");
    s.play().then(() => {
        document.getElementById("audioStatus").textContent = "🔊";
        preloadAdminSounds();
    }).catch(() => {
        document.getElementById("audioStatus").textContent = "🔊";
        preloadAdminSounds();
    });
}

function playAdminSound(name) {
    try {
        const s = new Audio(getAdminAudioUrl(name));
        s.play().catch(() => {});
    } catch (e) {}
}

function playAdminBgm(name) {
    stopAdminBgm();
    try {
        adminBgm = new Audio(getAdminAudioUrl(name));
        adminBgm.play().catch(() => {});
    } catch (e) {}
}

function fadeOutAdminBgm(durationMs) {
    if (!adminBgm) return;
    const bgm = adminBgm;
    const steps = 20;
    const interval = durationMs / steps;
    const volStep = bgm.volume / steps;
    let count = 0;
    const fader = setInterval(() => {
        count++;
        bgm.volume = Math.max(0, bgm.volume - volStep);
        if (count >= steps) {
            clearInterval(fader);
            bgm.pause();
            bgm.currentTime = 0;
            if (adminBgm === bgm) adminBgm = null;
        }
    }, interval);
}

function stopAdminBgm() {
    if (adminBgm) {
        adminBgm.pause();
        adminBgm.currentTime = 0;
        adminBgm = null;
    }
}

function updateCountdownButton(value) {
    const btn = document.querySelector(".btn-countdown");
    if (!btn) return;
    if (value < 0) {
        btn.textContent = "COUNTDOWN (10秒)";
    } else if (value <= 0) {
        btn.textContent = "TIME UP!";
    } else {
        btn.textContent = `COUNTDOWN (${value}秒)`;
    }
}

// History tracking
function getQuestionType() {
    if (state.batch_mode && state.batch_use_order) return "書着";
    if (state.batch_mode) return "書正";
    return "早押";
}

function recordThrough() {
    const record = { round: state.round, type: getQuestionType(), through: true, players: [] };
    state.players.forEach(p => {
        record.players.push({
            id: p.id, penalty: p.penalty || 0, pressed: false,
            results: [], delta: 0,
        });
    });
    history.push(record);
}

function finalizeHistory() {
    if (history.find(h => h.round === state.round)) return;
    const record = { round: state.round || history.length + 1, type: getQuestionType(), through: false, players: [] };
    state.players.forEach(p => {
        // Collect ALL judgments for this player (revival can produce multiple)
        const judgments = pendingJudgments.filter(jj => jj.player_id === p.id);
        const results = judgments.map(j => ({ result: j.result, order: j.order || 0 }));
        const delta = judgments.reduce((sum, j) => sum + (j.points_delta || 0), 0);
        // Check if player pressed at all (in current or previous press_orders)
        const pressed = judgments.length > 0 || state.press_order.some(pr => pr.player_id === p.id);
        record.players.push({
            id: p.id, penalty: p.penalty || 0, pressed: pressed,
            results: results, delta: delta,
        });
    });
    history.push(record);
}

function recordBatchHistory(results) {
    const record = { round: state.round || history.length + 1, type: getQuestionType(), through: false, players: [] };
    state.players.forEach(p => {
        const r = results.find(x => x.player_id === p.id);
        const pressEntry = state.press_order.find(pr => pr.player_id === p.id);
        record.players.push({
            id: p.id, penalty: p.penalty || 0, pressed: !!pressEntry,
            results: r ? [{ result: r.result, order: r.order || 0 }] : [],
            delta: r ? r.delta : 0,
        });
    });
    history.push(record);
}

function renderHistory() {
    const head = document.getElementById("historyHead");
    const body = document.getElementById("historyBody");

    if (history.length === 0) {
        head.innerHTML = "";
        body.innerHTML = '<tr><td style="color:#666;padding:8px">履歴なし</td></tr>';
        return;
    }

    // Header: 問題 | 種別 | Player1 | Player2 | ...
    let hdr = '<tr><th>問</th><th>種別</th>';
    state.players.forEach((p, i) => {
        const color = playerColors[i] || "#666";
        hdr += `<th style="color:${color}">${escapeHtml(p.name)}</th>`;
    });
    hdr += '</tr>';
    head.innerHTML = hdr;

    // Rows
    let rows = '';
    history.forEach(rec => {
        rows += `<tr><td class="h-round">${rec.round}</td>`;
        rows += `<td class="h-round">${rec.type}</td>`;

        if (rec.through) {
            // Through: all cells show スルー
            const colspan = state.players.length;
            rows += `<td colspan="${colspan}" style="color:#666;font-style:italic;text-align:center">スルー</td>`;
        } else {
            state.players.forEach(p => {
                const ph = rec.players.find(x => x.id === p.id);
                if (!ph) { rows += '<td>-</td>'; return; }

                let cell = '';
                if (ph.results && ph.results.length > 0) {
                    // Show sequence: 1× 3○ etc.
                    const marks = ph.results.map(r => {
                        const ord = r.order > 0 ? r.order : '';
                        if (r.result === "correct") return `<span class="h-correct">${ord}○</span>`;
                        if (r.result === "noanswer") return `<span class="h-penalty">${ord}—</span>`;
                        return `<span class="h-incorrect">${ord}×</span>`;
                    }).join('');
                    const sign = ph.delta >= 0 ? '+' : '';
                    cell = `${marks} ${sign}${ph.delta}`;
                } else if (ph.penalty > 0 && !(ph.result)) {
                    cell = `<span class="h-penalty">休</span>`;
                } else if (ph.result === "correct") {
                    // Legacy single-result format
                    const orderStr = ph.order > 0 ? ph.order + '位 ' : '';
                    const sign = ph.delta >= 0 ? '+' : '';
                    cell = `<span class="h-correct">${orderStr}○ ${sign}${ph.delta}</span>`;
                } else if (ph.result === "incorrect") {
                    const orderStr = ph.order > 0 ? ph.order + '位 ' : '';
                    const sign = ph.delta >= 0 ? '+' : '';
                    cell = `<span class="h-incorrect">${orderStr}× ${sign}${ph.delta}</span>`;
                } else if (ph.pressed) {
                    cell = `押`;
                } else if (ph.order > 0) {
                    cell = `${ph.order}位`;
                } else {
                    cell = '-';
                }
                rows += `<td>${cell}</td>`;
            });
        }
        rows += '</tr>';
    });
    body.innerHTML = rows;
}

function textColorFor(bg) {
    const hex = bg.replace("#", "");
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? "#000" : "#fff";
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

connect();

// Auto-enable audio on first user interaction
document.addEventListener("click", function autoUnlock() {
    unlockAdminAudio();
    document.removeEventListener("click", autoUnlock);
}, { once: true });

// Also try immediately (may work if user already interacted with the page)
unlockAdminAudio();
