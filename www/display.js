let PLAYER_COLORS = [
    "#e63946", "#457b9d", "#2a9d8f", "#e9c46a",
    "#f4a261", "#264653", "#6a4c93", "#1982c4"
];

let ws = null;
let state = {
    game_state: "idle",
    players: [],
    press_order: [],
    round: 1,
    answerer_id: -1,
};

let resultTimeout = null;
let countdownValue = 0;
let displayAudioEnabled = false;  // default off, controlled by admin audio_mode

// Sound - preload into browser memory for instant playback
const audioCache = {};
let currentBgm = null;
const SOUND_FILES = [
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8",
    "correct", "incorrect", "jingle", "countdown", "countdown_end", "batch_correct"
];

async function preloadSounds() {
    for (const name of SOUND_FILES) {
        try {
            const resp = await fetch(`sounds/${name}.mp3`);
            if (resp.ok) {
                const blob = await resp.blob();
                audioCache[name] = URL.createObjectURL(blob);
                console.log(`Preloaded: ${name}`);
            }
        } catch (e) {}
    }
    console.log(`Audio cache: ${Object.keys(audioCache).length} files`);
}

function getAudioUrl(name) {
    return audioCache[name] || `sounds/${name}.mp3`;
}

function playSound(name) {
    if (!displayAudioEnabled) return;
    try {
        const s = new Audio(getAudioUrl(name));
        s.play().catch(() => {});
    } catch (e) {}
}

function playBgm(name) {
    if (!displayAudioEnabled) return;
    stopBgm();
    try {
        currentBgm = new Audio(getAudioUrl(name));
        currentBgm.play().catch(() => {});
    } catch (e) {}
}

function stopBgm() {
    if (currentBgm) {
        currentBgm.pause();
        currentBgm.currentTime = 0;
        currentBgm = null;
    }
}

function fadeOutBgm(durationMs) {
    if (!currentBgm) return;
    const bgm = currentBgm;
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
            if (currentBgm === bgm) currentBgm = null;
        }
    }, interval);
}

function playPlayerSound(playerId) {
    if (!displayAudioEnabled) return;
    try {
        const s = new Audio(getAudioUrl(`p${playerId + 1}`));
        s.play().catch(() => {});
    } catch (e) {}
}

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        ws.send(JSON.stringify({ type: "register", client_type: "display" }));
    };
    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleMessage(msg);
    };
    ws.onclose = () => setTimeout(connect, 2000);
    ws.onerror = () => ws.close();
}

function handleMessage(msg) {
    switch (msg.type) {
        case "state":
            state = msg;
            if (msg.colors) PLAYER_COLORS = msg.colors;
            renderAll();
            break;
        case "colors_update":
            PLAYER_COLORS = msg.colors;
            renderAll();
            break;
        case "press":
            state.press_order.push(msg);
            state.game_state = "judging";
            if (msg.is_first) {
                state.answerer_id = msg.player_id;
                stopCountdown();
                renderMainDisplay();
                renderStateLabel();
            }
            playPlayerSound(msg.player_id);
            renderPressOrder();
            break;
        case "judgment":
            if (msg.correct_count !== undefined) state.correct_count = msg.correct_count;
            if (msg.result === "correct" && !msg.round_continues) {
                state.game_state = "showing_result";
            }
            // Otherwise (multi-correct continuing) state updates via follow-up
            // next_answerer / no_answerer messages.
            state.answerer_id = msg.player_id;
            const p = state.players.find(pl => pl.id === msg.player_id);
            if (p) p.score = msg.new_score;
            showResult(msg.result, msg.player_id);
            renderScoreboard(msg.player_id);
            renderStateLabel();
            playSound(msg.result);
            break;
        case "batch_result":
            state.game_state = "showing_result";
            state.answerer_id = -1;
            msg.results.forEach(r => {
                const pl = state.players.find(pp => pp.id === r.player_id);
                if (pl) pl.score = r.new_score;
            });
            showBatchResult(msg.results);
            renderScoreboard();
            renderStateLabel();
            playSound(msg.sound === "correct" ? "batch_correct" : "incorrect");
            break;
        case "next_answerer":
            state.answerer_id = msg.player_id;
            clearResult();
            renderMainDisplay();
            renderPressOrder();
            break;
        case "no_answerer":
            if (msg.revival) {
                state.game_state = "armed";
                state.answerer_id = -1;
                state.press_order = [];
            } else {
                state.game_state = "showing_result";
                state.answerer_id = -1;
            }
            renderAll();
            break;
        case "countdown":
            countdownValue = msg.value || 10;
            playBgm("countdown");
            renderCountdown(document.getElementById("mainDisplay"));
            break;
        case "countdown_tick":
            countdownValue = msg.value;
            if (countdownValue <= 0) {
                fadeOutBgm(200);
                playSound("countdown_end");
                document.getElementById("mainDisplay").innerHTML =
                    '<div class="first-presser"><div class="player-name" style="color:#e76f51">TIME UP!</div></div>';
            } else {
                renderCountdown(document.getElementById("mainDisplay"));
            }
            break;
        case "jingle":
            playSound("jingle");
            break;
        case "audio_mode":
            displayAudioEnabled = !!msg.display;
            break;
        case "reset":
            state.game_state = msg.game_state;
            state.press_order = [];
            state.answerer_id = -1;
            stopCountdown();
            clearResult();
            renderAll();
            break;
        case "player_update":
            const player = state.players.find(pl => pl.id === msg.player_id);
            if (player) {
                player.name = msg.name;
                player.score = msg.score;
            }
            renderScoreboard();
            break;
    }
}

function renderAll() {
    renderStateLabel();
    renderMainDisplay();
    renderPressOrder();
    renderScoreboard();
}

function renderStateLabel() {
    const el = document.getElementById("stateLabel");
    const labels = {
        idle: ["待機中", "#666"],
        armed: ["出題中", "#2d6a4f"],
        judging: ["回答中", "#f4a261"],
        showing_result: ["結果", "#264653"],
    };
    const [text, bg] = labels[state.game_state] || ["---", "#666"];
    el.textContent = text;
    el.style.background = bg;
    // Remaining corrects (visible only in multi-correct mode)
    const maxC = state.max_correct || 1;
    const cnt = state.correct_count || 0;
    const remaining = Math.max(0, maxC - cnt);
    const rEl = document.getElementById("correctRemaining");
    if (rEl) {
        rEl.classList.toggle("hidden", maxC <= 1);
        document.getElementById("correctRemainingValue").textContent = `${remaining}/${maxC}`;
    }
}

function renderMainDisplay() {
    const el = document.getElementById("mainDisplay");

    // Remove result overlay if present during non-result states
    if (state.game_state !== "showing_result") {
        const overlay = el.querySelector(".result-overlay");
        if (overlay) overlay.remove();
    }

    if (state.game_state === "idle") {
        el.innerHTML = '<div class="display-idle">待機中</div>';
    } else if (state.game_state === "armed") {
        el.innerHTML = '<div class="display-armed">出題中</div>';
    } else if (state.game_state === "showing_result" && state.press_order.length > 0 && state.answerer_id >= 0) {
        // Correct answer - keep showing the answerer with overlay
        const answererId = state.answerer_id;
        const player = state.players.find(p => p.id === answererId);
        const name = player ? player.name : `Player ${answererId + 1}`;
        const color = PLAYER_COLORS[answererId] || "#666";

        const existingOverlay = el.querySelector(".result-overlay");
        const overlayHtml = existingOverlay ? existingOverlay.outerHTML : "";

        el.innerHTML = `
            <div class="first-presser">
                <div class="player-num" style="background:${color};color:${textColorFor(color)}">${answererId + 1}</div>
                <div class="player-name" style="color:${color}">${escapeHtml(name)}</div>
                <div class="press-label">正解!</div>
            </div>
            ${overlayHtml}
        `;
    } else if (state.press_order.length > 0 && state.answerer_id >= 0) {
        // Judging - show current answerer
        const answererId = state.answerer_id;
        const player = state.players.find(p => p.id === answererId);
        const name = player ? player.name : `Player ${answererId + 1}`;
        const color = PLAYER_COLORS[answererId] || "#666";
        const pressIdx = state.press_order.findIndex(pr => pr.player_id === answererId);
        const orderLabel = pressIdx === 0 ? "1st PRESS!" : `${pressIdx + 1}位 回答中`;

        const existingOverlay = el.querySelector(".result-overlay");
        const overlayHtml = existingOverlay ? existingOverlay.outerHTML : "";

        el.innerHTML = `
            <div class="first-presser">
                <div class="player-num" style="background:${color};color:${textColorFor(color)}">${answererId + 1}</div>
                <div class="player-name" style="color:${color}">${escapeHtml(name)}</div>
                <div class="press-label">${orderLabel}</div>
            </div>
            ${overlayHtml}
        `;
    } else if (state.press_order.length > 0) {
        // All answered incorrectly
        const existingOverlay = el.querySelector(".result-overlay");
        const overlayHtml = existingOverlay ? existingOverlay.outerHTML : "";
        el.innerHTML = `
            <div class="first-presser">
                <div class="player-name" style="color:#e76f51">全員不正解</div>
            </div>
            ${overlayHtml}
        `;
    }
}

function renderPressOrder() {
    const el = document.getElementById("pressOrderBar");
    if (state.press_order.length === 0) {
        el.innerHTML = "";
        return;
    }
    const firstTs = state.press_order[0].timestamp_us;
    el.innerHTML = state.press_order.map((pr, i) => {
        const player = state.players.find(p => p.id === pr.player_id);
        const name = player ? player.name : `P${pr.player_id + 1}`;
        const color = PLAYER_COLORS[pr.player_id] || "#666";
        const diff = i === 0 ? "" : ` (+${((pr.timestamp_us - firstTs) / 1000000).toFixed(3)}秒)`;
        const cls = i === 0 ? "press-order-first" : "";
        return `<span class="press-order-item ${cls}" style="background:${color};color:${textColorFor(color)}">${i + 1}位 ${escapeHtml(name)}${diff}</span>`;
    }).join("");
}

function renderScoreboard(highlightId) {
    const el = document.getElementById("scoreboard");
    el.innerHTML = state.players.map((p, i) => {
        const color = PLAYER_COLORS[i] || "#666";
        const highlight = p.id === highlightId ? "score-highlight" : "";
        const penalty = p.penalty || 0;
        const penaltyClass = penalty > 0 ? "score-penalty" : "";
        const penaltyText = penalty > 0 ? `<div class="penalty-label">${penalty}問休み</div>` : "";
        return `
            <div class="score-cell ${highlight} ${penaltyClass}">
                <div class="s-name" style="color:${penalty > 0 ? '#666' : color}">${escapeHtml(p.name)}</div>
                <div class="s-score" ${penalty > 0 ? 'style="color:#555"' : ''}>${p.score}</div>
                ${penaltyText}
            </div>
        `;
    }).join("");
}

function showBatchResult(results) {
    const el = document.getElementById("mainDisplay");
    let html = '<div style="text-align:center;padding:16px">';
    results.forEach(r => {
        const player = state.players.find(p => p.id === r.player_id);
        const name = player ? player.name : `Player ${r.player_id + 1}`;
        const color = PLAYER_COLORS[r.player_id] || "#666";
        let icon, bgColor;
        if (r.result === "correct") {
            icon = "&#9675;";
            bgColor = "rgba(45,106,79,0.3)";
        } else if (r.result === "noanswer") {
            icon = "&mdash;";
            bgColor = "rgba(100,100,100,0.3)";
        } else {
            icon = "&#10005;";
            bgColor = "rgba(231,111,81,0.3)";
        }
        const sign = r.delta >= 0 ? "+" : "";
        html += `<div style="display:inline-block;margin:8px;padding:12px 20px;border-radius:8px;background:${bgColor};min-width:120px">
            <div style="font-size:1.5em;font-weight:bold;color:${color}">${escapeHtml(name)}</div>
            <div style="font-size:2em">${icon}</div>
            <div style="font-size:1.2em;font-weight:bold">${r.order > 0 ? r.order + '位 ' : ''}${sign}${r.delta}pt</div>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

function showResult(result, playerId) {
    const mainDisplay = document.getElementById("mainDisplay");
    // Remove existing overlay
    const existing = mainDisplay.querySelector(".result-overlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.className = `result-overlay result-${result}`;
    overlay.textContent = result === "correct" ? "正解!" : "不正解...";

    if (result === "incorrect") {
        overlay.classList.add("shake");
    }

    mainDisplay.appendChild(overlay);

    if (result === "incorrect") {
        // Auto-clear after 3 seconds (before next answerer)
        if (resultTimeout) clearTimeout(resultTimeout);
        resultTimeout = setTimeout(() => {
            overlay.remove();
        }, 3000);
    }
    // Correct stays until reset
}

function clearResult() {
    if (resultTimeout) {
        clearTimeout(resultTimeout);
        resultTimeout = null;
    }
    const overlay = document.querySelector(".result-overlay");
    if (overlay) overlay.remove();
}

// startCountdown is no longer needed - server drives countdown via messages

function renderCountdown(el) {
    const urgent = countdownValue <= 3 ? "urgent" : "";
    const barWidth = (countdownValue / 10) * 100;
    el.innerHTML = `
        <div class="countdown-display">
            <div class="countdown-number ${urgent}">${countdownValue}</div>
            <div class="countdown-label">残り時間</div>
        </div>
        <div class="countdown-bar" style="width:${barWidth}%"></div>
    `;
}

function stopCountdown() {
    stopBgm();
}

function textColorFor(bg) {
    const hex = bg.replace("#", "");
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? "#000" : "#fff";
}

function unlockAudio() {
    const s = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=");
    s.play().then(() => {
        document.getElementById("audioUnlock").style.display = "none";
        preloadSounds();
    }).catch(() => {
        document.getElementById("audioUnlock").style.display = "none";
        preloadSounds();
    });
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

connect();
