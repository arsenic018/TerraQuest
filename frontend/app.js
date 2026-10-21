// TerraQuest frontend. Served by the FastAPI app; set window.TERRAQUEST_API to point at another host.
"use strict";

const API = (window.TERRAQUEST_API || "").replace(/\/$/, "") + "/api";
const TIERS = ["easy", "medium", "hard", "extreme"];
const CATEGORY_ICONS = {
    outdoors: "tree", water: "water", fitness: "heart-pulse", food: "cup-hot",
    culture: "bank", social: "people", other: "geo-alt",
};

// ------------------------
// Utilities
// ------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
}

const fmtNum = (n) => Number(n).toLocaleString();
const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const fmtDateTime = (ts) => new Date(ts * 1000).toLocaleString();
const tierColor = (tier) => `var(--tq-${tier})`;

function storage(key, value) {
    try {
        if (value === undefined) return localStorage.getItem(key);
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
    } catch (e) { /* storage unavailable: session-only */ }
    return null;
}

async function api(path, { method = "GET", body } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let res;
    try {
        res = await fetch(API + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
        throw new Error("Can't reach the server. Check your connection.");
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) {
        if (res.status === 401 && state.token && path !== "/auth/login") setSession(null, null);
        throw new Error(errorMessage(data) || `Request failed (${res.status})`);
    }
    return data;
}

function errorMessage(data) {
    if (!data || !data.detail) return null;
    if (typeof data.detail === "string") return data.detail;
    // FastAPI validation errors: [{loc, msg}, ...]
    return data.detail.map((d) => `${d.loc?.slice(-1)[0] ?? "field"}: ${d.msg}`).join("; ");
}

function toast(message, variant = "success") {
    const el = document.createElement("div");
    el.className = `toast align-items-center text-bg-${variant} border-0`;
    el.setAttribute("role", variant === "danger" ? "alert" : "status");
    el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(message)}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
    $("#toasts").appendChild(el);
    el.addEventListener("hidden.bs.toast", () => el.remove());
    bootstrap.Toast.getOrCreateInstance(el, { delay: 4000 }).show();
}

function setBusy(button, busy, label) {
    if (busy) {
        button.dataset.label = button.innerHTML;
        button.disabled = true;
        button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>${esc(label || "Working…")}`;
    } else {
        button.disabled = false;
        if (button.dataset.label) button.innerHTML = button.dataset.label;
    }
}

function showError(el, message) {
    el.textContent = message || "";
    el.hidden = !message;
}

const emptyState = (icon, text) => `<div class="col-12"><div class="empty-state"><i class="bi bi-${icon}"></i>${esc(text)}</div></div>`;
const userLink = (name) => `<a class="user-link" href="#" data-user="${esc(name)}">${esc(name)}</a>`;
const tierBadge = (tier) => `<span class="tier tier-${tier}">${tier}</span>`;

// ------------------------
// State / session
// ------------------------
const state = {
    token: storage("tq-token"),
    username: storage("tq-user"),
    view: "explore",
    activities: [],
    oldestBlock: null,
    authMode: "login",
    completing: null,
};

function setSession(token, username) {
    state.token = token;
    state.username = username;
    storage("tq-token", token);
    storage("tq-user", username);
    renderAuth();
}

function renderAuth() {
    const area = $("#authArea");
    if (state.username) {
        area.innerHTML = `
            <div class="dropdown">
                <button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">
                    <i class="bi bi-person-circle"></i> ${esc(state.username)}
                </button>
                <ul class="dropdown-menu dropdown-menu-end">
                    <li><a class="dropdown-item" href="#" data-user="${esc(state.username)}"><i class="bi bi-person"></i> My profile</a></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><button class="dropdown-item" id="logoutBtn"><i class="bi bi-box-arrow-right"></i> Log out</button></li>
                </ul>
            </div>`;
        $("#logoutBtn").addEventListener("click", logout);
    } else {
        area.innerHTML = `<button class="btn btn-sm btn-primary" id="loginBtn">Log in</button>`;
        $("#loginBtn").addEventListener("click", () => openAuth("login"));
    }
}

async function logout() {
    try { await api("/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
    setSession(null, null);
    toast("Logged out", "secondary");
    refreshAll();
}

// ------------------------
// Views
// ------------------------
function showView(view) {
    if (!["explore", "campaigns", "leaderboard", "ledger"].includes(view)) view = "explore";
    state.view = view;
    $$("[data-section]").forEach((s) => (s.hidden = s.dataset.section !== view));
    $$("[data-view]").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
    ({ explore: loadActivities, campaigns: loadCampaigns, leaderboard: loadLeaderboard, ledger: loadLedger })[view]();
    bootstrap.Collapse.getInstance($("#nav"))?.hide();
}

function refreshAll() {
    loadStats();
    showView(state.view);
}

// ------------------------
// Stats
// ------------------------
async function loadStats() {
    try {
        const s = await api("/stats");
        const tiles = [
            ["Activities", s.activities, "map"],
            ["Completions", s.completions, "check2-circle"],
            ["Players", s.players, "people"],
            ["Blocks", s.blocks, s.chain_valid ? "shield-check" : "shield-exclamation"],
        ];
        $("#stats").innerHTML = tiles.map(([label, value, icon]) => `
            <div class="col-6"><div class="tq-stat">
                <div class="label"><i class="bi bi-${icon}"></i> ${label}</div>
                <div class="value">${fmtNum(value)}</div>
            </div></div>`).join("");
        $("#aiBadge").innerHTML = s.ai_enabled
            ? `<i class="bi bi-stars"></i> AI scoring enabled`
            : `<i class="bi bi-cpu"></i> Heuristic scoring (set OPENAI_API_KEY for AI)`;
    } catch (e) {
        $("#stats").innerHTML = `<div class="col-12"><div class="alert alert-warning mb-0">${esc(e.message)}</div></div>`;
    }
}

// ------------------------
// Activities
// ------------------------
function activityCard(a) {
    let action;
    if (a.completed_by_me) action = `<span class="badge text-bg-success"><i class="bi bi-check2"></i> Completed</span>`;
    else if (a.posted_by_me) action = `<span class="badge text-bg-secondary">Your activity</span>`;
    else action = `<button class="btn btn-sm btn-outline-primary" data-complete="${esc(a.id)}">Complete</button>`;

    const rationale = a.scoring?.rationale
        ? ` title="${esc(`${a.scoring.method === "ai" ? "AI" : "Scoring"}: ${a.scoring.rationale}`)}"`
        : "";

    return `
    <div class="col-md-6 col-lg-4">
        <div class="card h-100 tq-card tier-border-${a.tier}">
            <div class="card-body d-flex flex-column">
                <div class="d-flex justify-content-between align-items-start mb-2 gap-2">
                    <h3 class="card-title mb-0"><i class="bi bi-${CATEGORY_ICONS[a.category] || "geo-alt"} text-body-secondary me-1"></i>${esc(a.name)}</h3>
                    ${tierBadge(a.tier)}
                </div>
                ${a.location ? `<div class="small text-body-secondary mb-2"><i class="bi bi-geo-alt"></i> ${esc(a.location)}</div>` : ""}
                <p class="desc text-body-secondary small mb-3">${esc(a.description)}</p>
                <div class="mt-auto">
                    <div class="d-flex justify-content-between small mb-1"${rationale}>
                        <span>Difficulty ${a.difficulty_rating.toFixed(1)}${a.scoring?.method === "ai" ? ` <i class="bi bi-stars" aria-label="AI scored"></i>` : ""}</span>
                        <span class="points">${fmtNum(a.points)} pts</span>
                    </div>
                    <div class="difficulty-bar mb-3"><span style="width:${a.difficulty_rating * 10}%;background:${tierColor(a.tier)}"></span></div>
                    <div class="d-flex justify-content-between align-items-center small">
                        <span class="text-body-secondary">by ${userLink(a.user_who_posted)} · ${fmtDate(a.time_posted)}<br>
                            <i class="bi bi-people"></i> ${a.completion_count} completed</span>
                        ${action}
                    </div>
                </div>
            </div>
        </div>
    </div>`;
}

let activityRequest = 0;
async function loadActivities() {
    const params = new URLSearchParams();
    const q = $("#filterQ").value.trim();
    if (q) params.set("q", q);
    if ($("#filterTier").value) params.set("tier", $("#filterTier").value);
    params.set("sort", $("#filterSort").value);

    const grid = $("#activityGrid");
    const req = ++activityRequest;
    if (!state.activities.length) grid.innerHTML = `<div class="col-12 text-center py-5"><div class="spinner-border text-secondary"></div></div>`;
    try {
        const items = await api(`/activities?${params}`);
        if (req !== activityRequest) return;
        state.activities = items;
        grid.innerHTML = items.length
            ? items.map(activityCard).join("")
            : emptyState("search", q || $("#filterTier").value ? "No activities match your filters." : "No activities yet. Post the first one!");
    } catch (e) {
        grid.innerHTML = `<div class="col-12"><div class="alert alert-danger">${esc(e.message)}</div></div>`;
    }
}

// ------------------------
// Campaigns
// ------------------------
async function loadCampaigns() {
    const grid = $("#campaignGrid");
    grid.innerHTML = `<div class="col-12 text-center py-5"><div class="spinner-border text-secondary"></div></div>`;
    try {
        const data = await api("/campaigns");
        $("#campaignMeta").textContent = data.generated_at
            ? `Generated ${fmtDateTime(data.generated_at)} using ${data.method === "ai" ? "AI" : "difficulty tiers"} from community activities.`
            : "Themed challenge sets generated from community activities.";
        if (!data.campaigns.length) {
            grid.innerHTML = emptyState("stars", "No campaigns yet. Post some activities, then regenerate.");
            return;
        }
        const campaigns = [...data.campaigns].sort((a, b) => TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier));
        grid.innerHTML = campaigns.map((c) => {
            const total = c.activities.length;
            const pct = total ? Math.round((c.completed_by_me / total) * 100) : 0;
            return `
            <div class="col-md-6">
                <div class="card h-100 tier-border-${c.tier}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start gap-2 mb-1">
                            <h3 class="h5 mb-0">${esc(c.title)}</h3>
                            ${tierBadge(c.tier)}
                        </div>
                        <p class="text-body-secondary small">${esc(c.description)}</p>
                        ${state.username ? `
                        <div class="d-flex justify-content-between small mb-1">
                            <span>Your progress</span><span>${c.completed_by_me}/${total}${pct === 100 ? " 🏆" : ""}</span>
                        </div>
                        <div class="progress mb-3" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
                            <div class="progress-bar" style="width:${pct}%"></div>
                        </div>` : ""}
                        <ul class="list-group list-group-flush small">
                            ${c.activities.map((a) => `
                            <li class="list-group-item px-0 d-flex justify-content-between align-items-center gap-2">
                                <span>${a.completed_by_me ? `<i class="bi bi-check-circle-fill text-success"></i>` : `<i class="bi bi-circle text-body-tertiary"></i>`}
                                    ${esc(a.name)}</span>
                                <span class="d-flex align-items-center gap-2 text-nowrap">
                                    <span class="points">${fmtNum(a.points)}</span>
                                    ${!a.completed_by_me && !a.posted_by_me ? `<button class="btn btn-sm btn-link p-0" data-complete="${esc(a.id)}" title="Complete" aria-label="Complete ${esc(a.name)}"><i class="bi bi-plus-circle"></i></button>` : ""}
                                </span>
                            </li>`).join("")}
                        </ul>
                    </div>
                    <div class="card-footer bg-transparent d-flex justify-content-between small text-body-secondary">
                        <span>${total} activities</span><span class="points">${fmtNum(c.total_points)} pts total</span>
                    </div>
                </div>
            </div>`;
        }).join("");
    } catch (e) {
        grid.innerHTML = `<div class="col-12"><div class="alert alert-danger">${esc(e.message)}</div></div>`;
    }
}

async function regenerateCampaigns() {
    if (!state.username) return openAuth("login");
    const btn = $("#regenCampaigns");
    setBusy(btn, true, "Generating…");
    try {
        const r = await api("/campaigns/generate", { method: "POST" });
        toast(`Generated ${r.count} campaigns`);
        loadCampaigns();
        loadStats();
    } catch (e) {
        toast(e.message, "danger");
    } finally {
        setBusy(btn, false);
    }
}

// ------------------------
// Leaderboard
// ------------------------
async function loadLeaderboard() {
    const body = $("#leaderboardBody");
    body.innerHTML = `<tr><td colspan="6" class="text-center py-4"><div class="spinner-border spinner-border-sm text-secondary"></div></td></tr>`;
    try {
        const rows = await api("/leaderboard");
        body.innerHTML = rows.length ? rows.map((r) => {
            const medal = r.rank <= 3 ? `<i class="bi bi-trophy-fill rank-${r.rank}"></i>` : r.rank;
            const isMe = state.username && r.user.toLowerCase() === state.username.toLowerCase();
            return `<tr class="${isMe ? "is-me" : ""}">
                <td class="ps-3 fw-semibold">${medal}</td>
                <td>${userLink(r.user)}${isMe ? ` <span class="badge text-bg-secondary">you</span>` : ""}</td>
                <td class="text-end">${r.completed}</td>
                <td class="text-end d-none d-sm-table-cell">${r.posted}</td>
                <td class="text-end d-none d-md-table-cell">${fmtNum(r.creator_points)}</td>
                <td class="text-end pe-3 points">${fmtNum(r.total_points)}</td>
            </tr>`;
        }).join("") : `<tr><td colspan="6" class="empty-state">No players yet.</td></tr>`;
    } catch (e) {
        body.innerHTML = `<tr><td colspan="6"><div class="alert alert-danger m-2">${esc(e.message)}</div></td></tr>`;
    }
}

// ------------------------
// Ledger explorer
// ------------------------
function blockSummary(b) {
    const p = b.payload;
    if (b.event_type === "activity_submission") return `Activity posted: <strong>${esc(p.activity.name)}</strong> by ${esc(p.activity.user_who_posted)}`;
    if (b.event_type === "activity_completed") return `${esc(p.completion.user)} completed an activity (+${p.completion.points} pts)`;
    if (b.event_type === "campaign_batch") return `${p.batch.campaigns.length} campaigns generated (${esc(p.batch.method)})`;
    if (b.event_type === "campaign_generated") return `Campaign: ${esc(p.title || "untitled")} (legacy)`;
    if (b.event_type === "genesis") return "Genesis block";
    return esc(b.event_type);
}

function blockCard(b) {
    return `
    <details class="card block">
        <summary class="card-body py-2 d-flex flex-wrap gap-2 align-items-center" style="cursor:pointer">
            <span class="badge text-bg-dark">#${b.height}</span>
            <span class="badge text-bg-light border">${esc(b.event_type)}</span>
            <span class="flex-grow-1" style="font-family:var(--bs-body-font-family);font-size:.9rem">${blockSummary(b)}</span>
            <span class="text-body-secondary">${fmtDateTime(b.ts)}</span>
        </summary>
        <div class="card-body pt-0">
            <div class="hash">hash&nbsp;&nbsp;${esc(b.hash)}</div>
            <div class="hash mb-2">prev&nbsp;&nbsp;${esc(b.prev_hash)}</div>
            <pre class="bg-body-tertiary p-2 rounded">${esc(JSON.stringify(b.payload, null, 2))}</pre>
        </div>
    </details>`;
}

async function loadLedger(append = false) {
    const list = $("#blockList");
    if (!append) {
        state.oldestBlock = null;
        list.innerHTML = `<div class="text-center py-4"><div class="spinner-border text-secondary"></div></div>`;
        verifyChain(false);
    }
    try {
        const params = new URLSearchParams({ limit: 25 });
        if (append && state.oldestBlock !== null) params.set("before", state.oldestBlock);
        const blocks = await api(`/chain/blocks?${params}`);
        const html = blocks.map(blockCard).join("");
        if (append) list.insertAdjacentHTML("beforeend", html);
        else list.innerHTML = html || `<div class="empty-state">No blocks.</div>`;
        if (blocks.length) state.oldestBlock = blocks[blocks.length - 1].height;
        $("#moreBlocks").hidden = blocks.length < 25 || state.oldestBlock === 0;
    } catch (e) {
        list.innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`;
    }
}

async function verifyChain(announce = true) {
    const box = $("#chainStatus");
    try {
        const r = await api("/chain/verify");
        box.innerHTML = r.valid
            ? `<div class="alert alert-success py-2 mb-0"><i class="bi bi-shield-check"></i> All ${fmtNum(r.blocks)} blocks verified: hashes and links are intact.</div>`
            : `<div class="alert alert-danger py-2 mb-0"><i class="bi bi-shield-exclamation"></i> Chain verification failed: ${esc(r.error)}</div>`;
        if (announce) toast(r.valid ? "Chain verified" : "Chain verification failed", r.valid ? "success" : "danger");
    } catch (e) {
        box.innerHTML = `<div class="alert alert-warning py-2 mb-0">${esc(e.message)}</div>`;
    }
}

// ------------------------
// Profile
// ------------------------
async function openProfile(username) {
    const modal = bootstrap.Modal.getOrCreateInstance($("#profileModal"));
    $("#profileTitle").textContent = username;
    $("#profileBody").innerHTML = `<div class="text-center py-4"><div class="spinner-border text-secondary"></div></div>`;
    modal.show();
    try {
        const p = await api(`/users/${encodeURIComponent(username)}`);
        const stat = (label, value) => `<div class="col-6 col-md-3"><div class="tq-stat"><div class="label">${label}</div><div class="value">${value}</div></div></div>`;
        $("#profileBody").innerHTML = `
            <div class="row g-3 mb-4">
                ${stat("Rank", `#${p.rank}`)}
                ${stat("Total points", fmtNum(p.total_points))}
                ${stat("Quests done", p.completed)}
                ${stat("Creator pts", fmtNum(p.creator_points))}
            </div>
            <h6>Completed</h6>
            ${p.completions.length ? `<ul class="list-group list-group-flush mb-4 small">${p.completions.map((c) => `
                <li class="list-group-item px-0 d-flex justify-content-between gap-2">
                    <span><i class="bi bi-check-circle-fill text-success"></i> ${esc(c.activity_name)}
                        ${c.note ? `<span class="d-block text-body-secondary fst-italic">“${esc(c.note)}”</span>` : ""}</span>
                    <span class="text-nowrap text-body-secondary">+${c.points} · ${fmtDate(c.time_completed)}</span>
                </li>`).join("")}</ul>` : `<p class="text-body-secondary small mb-4">Nothing yet.</p>`}
            <h6>Posted</h6>
            ${p.activities.length ? `<ul class="list-group list-group-flush small">${p.activities.map((a) => `
                <li class="list-group-item px-0 d-flex justify-content-between gap-2">
                    <span>${tierBadge(a.tier)} ${esc(a.name)}</span>
                    <span class="text-nowrap text-body-secondary">${a.completion_count} completed</span>
                </li>`).join("")}</ul>` : `<p class="text-body-secondary small mb-0">Nothing yet.</p>`}`;
    } catch (e) {
        $("#profileBody").innerHTML = `<div class="alert alert-danger mb-0">${esc(e.message)}</div>`;
    }
}

// ------------------------
// Auth modal
// ------------------------
let afterAuth = null;

function openAuth(mode, then = null) {
    afterAuth = then;
    setAuthMode(mode);
    showError($("#authError"), null);
    $("#authForm").reset();
    bootstrap.Modal.getOrCreateInstance($("#authModal")).show();
}

function setAuthMode(mode) {
    state.authMode = mode;
    const register = mode === "register";
    $$("[data-auth-mode]").forEach((b) => b.classList.toggle("active", b.dataset.authMode === mode));
    $("#authTitle").textContent = register ? "Join TerraQuest" : "Welcome back";
    $("#authSubmit").textContent = register ? "Create account" : "Log in";
    $("#authPass").autocomplete = register ? "new-password" : "current-password";
    $("#authUserHelp").hidden = !register;
    $("#authPassHelp").hidden = !register;
}

async function submitAuth(e) {
    e.preventDefault();
    const username = $("#authUser").value.trim();
    const password = $("#authPass").value;
    const err = $("#authError");
    if (!/^[A-Za-z0-9_]{3,24}$/.test(username)) return showError(err, "Username must be 3–24 letters, numbers or underscores.");
    if (password.length < 8) return showError(err, "Password must be at least 8 characters.");

    const btn = $("#authSubmit");
    setBusy(btn, true);
    try {
        const r = await api(`/auth/${state.authMode}`, { method: "POST", body: { username, password } });
        setSession(r.token, r.username);
        bootstrap.Modal.getInstance($("#authModal")).hide();
        toast(state.authMode === "register" ? `Welcome to TerraQuest, ${r.username}!` : `Logged in as ${r.username}`);
        refreshAll();
        const next = afterAuth;
        afterAuth = null;
        if (next) setTimeout(next, 350);
    } catch (ex) {
        showError(err, ex.message);
    } finally {
        setBusy(btn, false);
    }
}

// ------------------------
// Submit activity
// ------------------------
function openSubmit() {
    if (!state.username) return openAuth("login", openSubmit);
    $("#submitForm").reset();
    updateDiffLabel();
    showError($("#submitError"), null);
    bootstrap.Modal.getOrCreateInstance($("#submitModal")).show();
}

function updateDiffLabel() {
    const v = parseFloat($("#actDiff").value);
    $("#actDiffVal").textContent = v < 0 ? "Skip" : v.toFixed(1);
}

async function submitActivity(e) {
    e.preventDefault();
    const name = $("#actName").value.trim();
    const description = $("#actDesc").value.trim();
    const place = $("#actLoc").value.trim();
    const diff = parseFloat($("#actDiff").value);
    const err = $("#submitError");
    if (name.length < 3) return showError(err, "Name must be at least 3 characters.");
    if (description.length < 10) return showError(err, "Description must be at least 10 characters.");

    const btn = $("#submitBtn");
    setBusy(btn, true, "Scoring…");
    try {
        const r = await api("/activities", {
            method: "POST",
            body: { name, description, location: place || null, suggested_difficulty: diff < 0 ? null : diff },
        });
        bootstrap.Modal.getInstance($("#submitModal")).hide();
        toast(`Posted! Scored ${r.activity.difficulty_rating.toFixed(1)} difficulty, worth ${r.activity.points} pts (block #${r.height}).`);
        if (state.view !== "explore") location.hash = "#explore";
        refreshAll();
    } catch (ex) {
        showError(err, ex.message);
    } finally {
        setBusy(btn, false);
    }
}

// ------------------------
// Complete activity
// ------------------------
async function openComplete(id) {
    if (!state.username) return openAuth("login", () => openComplete(id));
    let a = state.activities.find((x) => x.id === id);
    if (!a) {
        try { a = await api(`/activities/${encodeURIComponent(id)}`); } catch (e) { return toast(e.message, "danger"); }
    }
    if (a.completed_by_me || a.posted_by_me) return;
    state.completing = a;
    $("#completeSummary").innerHTML = `<strong>${esc(a.name)}</strong> · ${tierBadge(a.tier)} · <span class="points">${fmtNum(a.points)} pts</span>`;
    $("#completeForm").reset();
    showError($("#completeError"), null);
    bootstrap.Modal.getOrCreateInstance($("#completeModal")).show();
}

async function submitComplete(e) {
    e.preventDefault();
    const a = state.completing;
    if (!a) return;
    const btn = $("#completeBtn");
    setBusy(btn, true);
    try {
        await api(`/activities/${encodeURIComponent(a.id)}/complete`, { method: "POST", body: { note: $("#completeNote").value.trim() } });
        bootstrap.Modal.getInstance($("#completeModal")).hide();
        toast(`+${a.points} points for ${a.name}!`);
        refreshAll();
    } catch (ex) {
        showError($("#completeError"), ex.message);
    } finally {
        setBusy(btn, false);
    }
}

// ------------------------
// Theme
// ------------------------
function toggleTheme() {
    const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", next);
    storage("tq-theme", next);
}

// ------------------------
// Wiring
// ------------------------
function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

document.addEventListener("click", (e) => {
    const user = e.target.closest("[data-user]");
    if (user) { e.preventDefault(); return openProfile(user.dataset.user); }
    const complete = e.target.closest("[data-complete]");
    if (complete) return openComplete(complete.dataset.complete);
    if (e.target.closest("[data-action='submit']")) return openSubmit();
    const mode = e.target.closest("[data-auth-mode]");
    if (mode) return setAuthMode(mode.dataset.authMode);
});

$("#authForm").addEventListener("submit", submitAuth);
$("#submitForm").addEventListener("submit", submitActivity);
$("#completeForm").addEventListener("submit", submitComplete);
$("#actDiff").addEventListener("input", updateDiffLabel);
$("#filters").addEventListener("submit", (e) => e.preventDefault());
$("#filterQ").addEventListener("input", debounce(loadActivities, 250));
$("#filterTier").addEventListener("change", loadActivities);
$("#filterSort").addEventListener("change", loadActivities);
$("#regenCampaigns").addEventListener("click", regenerateCampaigns);
$("#verifyChain").addEventListener("click", () => verifyChain(true));
$("#moreBlocks").addEventListener("click", () => loadLedger(true));
$("#themeToggle").addEventListener("click", toggleTheme);
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));

renderAuth();
loadStats();
showView(location.hash.slice(1) || "explore");

// Validate a stored session in the background.
if (state.token) api("/auth/me").catch(() => {});
