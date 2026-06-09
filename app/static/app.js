"use strict";

const state = {
  source: "default",   // default | path | upload
  dbPath: "",
  token: "",
  vm: null,
  page: 0,
  pageSize: 50,
  charts: {},
  loaded: false,
  selectedSessions: new Set(),
};

const $ = (id) => document.getElementById(id);
const esc = (v) => (v == null ? "" : String(v)).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const PALETTE = ["#c8f04a", "#5eead4", "#ff7a59", "#f5b23a", "#a78bfa", "#38bdf8", "#fb7185", "#4ade80", "#e879f9", "#facc15"];

/* ---------------- status ---------------- */
function showStatus(msg, kind = "info") {
  const el = $("status");
  el.textContent = msg;
  el.className = "status " + kind;
}
function hideStatus() { $("status").className = "status hidden"; }

function setLoading(on) {
  $("refreshBtn").classList.toggle("loading", on);
}

function queryParams() {
  const p = new URLSearchParams();
  if (state.source === "upload" && state.token) p.set("token", state.token);
  else if (state.source === "path" && state.dbPath) p.set("db_path", state.dbPath);
  return p;
}

/* ---------------- source selection ---------------- */
function setSource(src) {
  state.source = src;
  document.querySelectorAll(".seg").forEach((b) => b.classList.toggle("active", b.dataset.src === src));
  $("pathField").hidden = src !== "path";
  $("fileField").hidden = src !== "upload";
  hideStatus();

  if (src === "default") {
    runAnalysis();
  } else if (src === "path") {
    const inp = $("pathInput");
    inp.focus();
    if (state.dbPath) runAnalysis();
  } else if (src === "upload") {
    $("fileInput").click();
  }
}

document.querySelectorAll(".seg").forEach((b) => {
  b.addEventListener("click", () => setSource(b.dataset.src));
});

/* manual path: analyze on Enter or on blur (when changed & non-empty) */
$("pathInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { state.dbPath = e.target.value.trim(); runAnalysis(); }
});
$("pathInput").addEventListener("blur", (e) => {
  const v = e.target.value.trim();
  if (v && v !== state.dbPath) { state.dbPath = v; runAnalysis(); }
});

/* upload: analyze as soon as a file is picked */
$("fileInput").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("fileLabelText").textContent = file.name;
  showStatus("上传中… " + file.name, "info");
  setLoading(true);
  try {
    const fd = new FormData();
    fd.append("file", file);
    const up = await fetch("/api/upload", { method: "POST", body: fd });
    if (!up.ok) { showStatus("上传失败：" + (await up.json()).detail, "error"); setLoading(false); return; }
    state.token = (await up.json()).token;
    await runAnalysis();
  } catch (err) {
    showStatus("上传出错：" + err.message, "error");
    setLoading(false);
  }
});

/* refresh button — re-run on the current source */
$("refreshBtn").addEventListener("click", () => {
  if (state.source === "path") state.dbPath = $("pathInput").value.trim();
  runAnalysis();
});

/* ---------------- core analysis ---------------- */
async function runAnalysis() {
  if (state.source === "path" && !state.dbPath) { showStatus("请输入数据库路径后回车", "info"); return; }
  if (state.source === "upload" && !state.token) { return; }

  hideStatus();
  setLoading(true);
  try {
    const res = await fetch("/api/usage?" + queryParams().toString());
    if (!res.ok) {
      showStatus("加载失败：" + (await res.json()).detail, "error");
      setLoading(false);
      return;
    }
    const data = await res.json();
    state.vm = data.viewmodels;
    state.page = 0;
    state.loaded = true;
    state.selectedSessions = new Set();  // reset selection for the new dataset

    document.querySelector(".app").classList.remove("idle");
    $("emptyState").classList.remove("show");
    $("sourceDot").classList.add("live");
    $("sourceLabel").textContent = data.source;
    $("exportCsvBtn").disabled = false;
    $("exportReportBtn").disabled = false;

    renderAll();
    moveTabInk();
  } catch (err) {
    showStatus("出错：" + err.message, "error");
  } finally {
    setLoading(false);
  }
}

/* ---------------- tabs ---------------- */
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("tab-" + t.dataset.tab).classList.add("active");
    moveTabInk();
  });
});

function moveTabInk() {
  const active = document.querySelector(".tab.active");
  const ink = $("tabInk");
  if (!active || !ink) return;
  ink.style.left = active.offsetLeft + "px";
  ink.style.width = active.offsetWidth + "px";
}
window.addEventListener("resize", () => { moveTabInk(); });

/* ---------------- render ---------------- */
function renderAll() {
  renderHeadChips();
  renderOverview();
  renderModels();
  renderSessions();
  renderDays();
  renderMessages();
}

function renderHeadChips() {
  const c = state.vm.overview.cards;
  $("headChips").innerHTML = [
    `<span class="chip">消息 <b>${esc(c.message_count)}</b></span>`,
    `<span class="chip">Token <b>${esc(c.total_tokens_display)}</b></span>`,
    `<span class="chip">模型 <b>${(state.vm.models || []).length}</b></span>`,
    `<span class="chip">会话 <b>${(state.vm.sessions || []).length}</b></span>`,
  ].join("");
}

function card(label, value, cls = "") {
  return `<div class="card ${cls}"><div class="card-label">${esc(label)}</div><div class="card-value">${esc(value)}</div></div>`;
}

function renderOverview() {
  const c = state.vm.overview.cards;
  $("cards").innerHTML = [
    card("总消息数", c.message_count),
    card("总 Token", c.total_tokens_display, "accent"),
    card("输入 Token", c.input_tokens_display),
    card("输出 Token", c.output_tokens_display),
    card("推理 Token", c.reasoning_tokens_display),
    card("缓存读取", c.cache_read_display),
    card("缓存写入", c.cache_write_display),
    card("预估成本", c.estimated_cost_total_display || "—", "cost"),
    card("已记录成本", c.recorded_cost_total_display || "—", "cost"),
    card("已定价 / 未定价", `${c.priced_message_count} / ${c.unpriced_message_count}`),
  ].join("");
  // stagger card reveal
  document.querySelectorAll("#cards .card").forEach((el, i) => { el.style.animationDelay = (i * 0.035) + "s"; });
  renderCharts();
}

/* ---------------- charts ---------------- */
function themeChart() {
  if (typeof Chart === "undefined") return;
  Chart.defaults.color = "#888f9e";
  Chart.defaults.borderColor = "rgba(255,255,255,0.06)";
  Chart.defaults.font.family = "'IBM Plex Mono', monospace";
  Chart.defaults.font.size = 11;
}

function destroyChart(key) { if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; } }

const GRID = { color: "rgba(255,255,255,0.05)" };
const NOLEGEND = { legend: { display: false } };

function renderCharts() {
  if (typeof Chart === "undefined") return;
  themeChart();

  const days = (state.vm.days || []).slice().sort((a, b) => (a.day || "").localeCompare(b.day || ""));
  const models = (state.vm.models || []).slice(0, 10);
  const mLabels = models.map((m) => `${m.provider}:${m.model}`);
  const mTotals = models.map((m) => m.total_tokens);

  destroyChart("trend");
  state.charts.trend = new Chart($("trendChart"), {
    type: "line",
    data: {
      labels: days.map((d) => d.day),
      datasets: [
        { label: "总", data: days.map((d) => d.total_tokens), borderColor: "#c8f04a", backgroundColor: "rgba(200,240,74,0.12)", borderWidth: 2, tension: 0.3, fill: true, pointRadius: 0, pointHoverRadius: 4 },
        { label: "输入", data: days.map((d) => d.input_tokens), borderColor: "#5eead4", borderWidth: 1.5, tension: 0.3, pointRadius: 0, pointHoverRadius: 4 },
        { label: "输出", data: days.map((d) => d.output_tokens), borderColor: "#ff7a59", borderWidth: 1.5, tension: 0.3, pointRadius: 0, pointHoverRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { labels: { usePointStyle: true, boxWidth: 7, padding: 16 } } },
      scales: { x: { grid: { display: false } }, y: { grid: GRID, beginAtZero: true } },
    },
  });

  destroyChart("bar");
  state.charts.bar = new Chart($("modelBarChart"), {
    type: "bar",
    data: { labels: mLabels, datasets: [{ data: mTotals, backgroundColor: mLabels.map((_, i) => PALETTE[i % PALETTE.length]), borderRadius: 5, barThickness: "flex", maxBarThickness: 22 }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: NOLEGEND,
      scales: { x: { grid: GRID, beginAtZero: true }, y: { grid: { display: false } } },
    },
  });

  destroyChart("pie");
  state.charts.pie = new Chart($("modelPieChart"), {
    type: "doughnut",
    data: { labels: mLabels, datasets: [{ data: mTotals, backgroundColor: mLabels.map((_, i) => PALETTE[i % PALETTE.length]), borderColor: "#14161d", borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "right", labels: { usePointStyle: true, boxWidth: 7, padding: 10, font: { size: 10 } } } },
    },
  });
}

/* ---------------- tables ---------------- */
function badge(label) {
  if (label === "已定价") return '<span class="badge priced">已定价</span>';
  if (label === "未定价") return '<span class="badge unpriced">未定价</span>';
  return "";
}

function tableHTML(headers, rows) {
  const head = headers.map((h) => {
    if (h && typeof h === "object") return `<th class="${h.cls || ""}">${h.html != null ? h.html : esc(h.label || "")}</th>`;
    return `<th>${esc(h)}</th>`;
  }).join("");
  let body = rows.map((r) => "<tr>" + r.map((c) => (typeof c === "object" ? `<td class="${c.cls || ""}">${c.html}</td>` : `<td>${c}</td>`)).join("") + "</tr>").join("");
  if (!rows.length) body = `<tr><td class="empty" colspan="${headers.length}">无数据</td></tr>`;
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
const num = (v) => ({ html: esc(v), cls: "num" });
const cost = (v) => ({ html: esc(v || "—"), cls: "cost" });

function renderModels() {
  const rows = (state.vm.models || []).map((r) => [
    esc(r.provider), esc(r.model), num(r.message_count), num(r.total_tokens_display),
    num(r.input_tokens_display), num(r.output_tokens_display), cost(r.estimated_cost_display),
    { html: badge(r.price_status_label) },
  ]);
  $("modelsTable").innerHTML = tableHTML(["Provider", "模型", "消息数", "总Token", "输入", "输出", "预估成本", "定价"], rows);
}

function renderSessions() {
  const sessions = state.vm.sessions || [];
  const rows = sessions.map((r) => {
    const checked = state.selectedSessions.has(r.session_id) ? "checked" : "";
    return [
      { html: `<input type="checkbox" class="sess-check" data-id="${esc(r.session_id)}" ${checked}>`, cls: "col-check" },
      esc(r.session_title || r.session_id), num(r.message_count), num(r.total_tokens_display),
      cost(r.estimated_cost_display), { html: badge(r.price_status_label) },
      { html: `<button class="row-action" onclick="exportSession('${esc(r.session_id)}')">导出报告</button>` },
    ];
  });
  const headers = [
    { html: '<input type="checkbox" id="selectAllSessions">', cls: "col-check" },
    "会话", "消息数", "总Token", "预估成本", "定价", "操作",
  ];
  $("sessionsTable").innerHTML = tableHTML(headers, rows);
  $("sessionsTable").querySelectorAll(".sess-check").forEach((cb) => {
    cb.closest("tr").classList.toggle("row-selected", cb.checked);
  });
  updateSelectionUI();
}

/* ---- multi-session selection ---- */
function updateSelectionUI() {
  const total = (state.vm?.sessions || []).length;
  const n = state.selectedSessions.size;
  const selCount = $("selCount");
  selCount.textContent = "已选 " + n;
  selCount.classList.toggle("has", n > 0);
  $("exportSelectedBtn").disabled = n === 0;
  $("clearSelBtn").disabled = n === 0;
  const sa = $("selectAllSessions");
  if (sa) {
    sa.checked = n > 0 && n === total;
    sa.indeterminate = n > 0 && n < total;
  }
}

function toggleAllSessions(checked) {
  const sessions = state.vm?.sessions || [];
  if (checked) sessions.forEach((s) => state.selectedSessions.add(s.session_id));
  else state.selectedSessions.clear();
  renderSessions();
}

// delegated change handler — the inner table HTML is replaced on each render,
// but #sessionsTable itself persists, so one listener covers all checkboxes.
$("sessionsTable").addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "selectAllSessions") {
    toggleAllSessions(t.checked);
  } else if (t.classList.contains("sess-check")) {
    if (t.checked) state.selectedSessions.add(t.dataset.id);
    else state.selectedSessions.delete(t.dataset.id);
    t.closest("tr").classList.toggle("row-selected", t.checked);
    updateSelectionUI();
  }
});

$("clearSelBtn").addEventListener("click", () => { state.selectedSessions.clear(); renderSessions(); });

$("exportSelectedBtn").addEventListener("click", () => {
  if (!state.selectedSessions.size) return;
  const p = queryParams();
  state.selectedSessions.forEach((id) => p.append("session_id", id));
  window.location.href = "/api/export/report?" + p.toString();
});

function renderDays() {
  const rows = (state.vm.days || []).map((r) => [
    esc(r.day), num(r.message_count), num(r.total_tokens_display),
    num(r.input_tokens_display), num(r.output_tokens_display), cost(r.estimated_cost_display),
  ]);
  $("daysTable").innerHTML = tableHTML(["日期", "消息数", "总Token", "输入", "输出", "预估成本"], rows);
}

function renderMessages() {
  const all = state.vm.raw_messages || [];
  const pages = Math.max(1, Math.ceil(all.length / state.pageSize));
  if (state.page >= pages) state.page = pages - 1;
  const slice = all.slice(state.page * state.pageSize, (state.page + 1) * state.pageSize);
  const rows = slice.map((r) => [
    { html: esc(r.time_created_text), cls: "num" }, esc(r.session_title || r.session_id), esc(r.provider), esc(r.model),
    esc(r.role), num(r.total_tokens_display), num(r.input_tokens_display), num(r.output_tokens_display),
    cost(r.estimated_cost_display), { html: badge(r.price_status_label) },
  ]);
  $("messagesTable").innerHTML = tableHTML(
    ["时间", "会话", "Provider", "模型", "角色", "总Token", "输入", "输出", "预估成本", "定价"], rows);
  $("pageInfo").textContent = `第 ${state.page + 1} / ${pages} 页 · 共 ${all.length} 条`;
}

$("prevPage").addEventListener("click", () => { if (state.page > 0) { state.page--; renderMessages(); } });
$("nextPage").addEventListener("click", () => {
  const pages = Math.ceil((state.vm.raw_messages || []).length / state.pageSize);
  if (state.page < pages - 1) { state.page++; renderMessages(); }
});

/* ---------------- exports ---------------- */
$("exportCsvBtn").addEventListener("click", () => {
  window.location.href = "/api/export/csv?" + queryParams().toString();
});
$("exportReportBtn").addEventListener("click", () => {
  window.location.href = "/api/export/report?" + queryParams().toString();
});
window.exportSession = function (sessionId) {
  const p = queryParams();
  p.set("session_id", sessionId);
  window.location.href = "/api/export/report?" + p.toString();
};

/* ---------------- boot ---------------- */
async function boot() {
  document.querySelector(".app").classList.add("idle");
  $("emptyState").classList.add("show");
  try {
    const res = await fetch("/api/db/default");
    const data = await res.json();
    $("pathInput").placeholder = data.path + (data.exists ? "（默认）" : "（不存在）");
    if (data.exists) {
      // auto-analyze the default source on first load
      runAnalysis();
    }
  } catch (_) {}
}
boot();
