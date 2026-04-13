"""
Demanda 9 (higiene visual v2) -- Gera uma pagina HTML standalone para
revisao interativa do pilot_120 por Murilo.

Le:
  reports/tail_pilot_120_for_murilo_2026-04-10.csv

Gera:
  reports/tail_pilot_120_review.html   (standalone, abre em qualquer navegador)

Features:
  - 1 wine por tela (card), navegacao anterior/proximo
  - botoes grandes para as 4 categorias (business_class, review_state,
    confidence, action)
  - auto-sugestao via botao "aceitar Claude" (preenche com R1)
  - auto-save em localStorage (nao perde progresso se fechar)
  - barra de progresso (X / 120)
  - pula direto pra wine N via dropdown
  - botao "baixar CSV" no fim gera tail_pilot_120_for_murilo_2026-04-10.csv
    preenchido pronto pros scripts rodarem
  - sem servidor, sem internet, sem install -- so double-click no arquivo

Uso:
  python scripts/export_murilo_review_html.py
"""

import csv
import json
import os

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
IN_CSV = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")
OUT_HTML = os.path.join(REPORT_DIR, "tail_pilot_120_review.html")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Pilot 120 Review -- Murilo</title>
<style>
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #F5F5F7; color: #1C1C1E;
  font-size: 15px;
}
.wrap {
  max-width: 1100px; margin: 0 auto; padding: 16px;
}
header {
  background: #1C1C1E; color: #fff; padding: 12px 20px;
  border-radius: 10px; margin-bottom: 14px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
header h1 { margin: 0; font-size: 17px; font-weight: 600; }
header .progress-box { flex: 1; min-width: 260px; }
.progress-bar {
  height: 8px; background: #3A3A3C; border-radius: 4px; overflow: hidden;
}
.progress-fill {
  height: 100%; background: linear-gradient(90deg, #34C759, #32ADE6);
  transition: width 0.2s ease;
}
.progress-text { font-size: 13px; color: #AEAEB2; margin-top: 4px; }
.nav-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.nav-controls button, .nav-controls select {
  background: #2C2C2E; color: #fff; border: 1px solid #48484A;
  padding: 7px 14px; border-radius: 7px; font-size: 14px; cursor: pointer;
}
.nav-controls button:hover { background: #3A3A3C; }
.nav-controls button.primary {
  background: #0A84FF; border-color: #0A84FF;
}
.nav-controls button.primary:hover { background: #0071E3; }
.nav-controls button.success {
  background: #30D158; border-color: #30D158; color: #000;
}
.nav-controls button.success:hover { background: #28B84E; }
.nav-controls select { min-width: 70px; }

.card {
  background: #fff; border-radius: 12px; padding: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  margin-bottom: 14px;
}

.wine-title {
  font-size: 20px; font-weight: 700; margin: 0 0 6px 0;
  color: #1C1C1E; line-height: 1.3;
}
.wine-meta {
  display: flex; gap: 18px; flex-wrap: wrap;
  font-size: 14px; color: #636366; margin-bottom: 14px;
}
.wine-meta strong { color: #1C1C1E; }

.flag-strip {
  display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 16px 0;
}
.flag {
  padding: 5px 12px; border-radius: 999px; font-size: 12.5px;
  background: #F2F2F7; color: #3A3A3C; font-weight: 500;
}
.flag.warning { background: #FFF3CD; color: #664D03; }
.flag.danger { background: #F8D7DA; color: #58151C; font-weight: 600; }
.flag.info { background: #CFE2FF; color: #084298; }

.candidate-block {
  border-left: 3px solid #D1D1D6; padding: 10px 14px;
  background: #F8F9FA; border-radius: 6px; margin: 10px 0;
}
.candidate-block.render { border-color: #0A84FF; }
.candidate-block.import { border-color: #AF52DE; }
.candidate-block h4 { margin: 0 0 6px 0; font-size: 13px; color: #636366; text-transform: uppercase; letter-spacing: 0.5px; }
.candidate-block .top1 { font-size: 15px; font-weight: 600; color: #1C1C1E; margin-bottom: 6px; }
.candidate-block .top3 { font-size: 13px; color: #3A3A3C; line-height: 1.6; white-space: pre-line; }
.candidate-block .empty { font-style: italic; color: #8E8E93; }

.claude-suggestion {
  background: linear-gradient(135deg, #F0F7FF 0%, #F5F0FF 100%);
  border-left: 3px solid #5E5CE6; padding: 12px 14px;
  border-radius: 6px; margin: 12px 0;
  font-size: 14px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.claude-suggestion .suggestion-body { flex: 1 1 360px; min-width: 0; }
.claude-suggestion h4 {
  margin: 0 0 6px 0; font-size: 13px; color: #3634A3;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.claude-suggestion .r1-values {
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;
}
.claude-suggestion .r1-tag {
  background: #fff; padding: 3px 9px; border-radius: 5px;
  font-size: 12.5px; font-weight: 600; color: #3634A3;
  border: 1px solid #D1D0FA;
}
.claude-suggestion .r1-reason { color: #4B4A9E; font-size: 13px; margin-top: 4px; }
.claude-suggestion .accept-btn {
  background: #5E5CE6; color: #fff; border: none;
  padding: 14px 22px; border-radius: 10px;
  font-size: 15px; font-weight: 700; cursor: pointer;
  white-space: nowrap;
  box-shadow: 0 3px 10px rgba(94,92,230,0.3);
  transition: all 0.1s ease;
}
.claude-suggestion .accept-btn:hover {
  background: #4A48D4; transform: translateY(-1px);
  box-shadow: 0 5px 14px rgba(94,92,230,0.4);
}
.claude-suggestion .accept-btn:active { transform: translateY(0); }
.claude-suggestion .accept-btn .check { margin-right: 6px; font-size: 17px; }

.decision-section {
  background: #fff; border-radius: 12px; padding: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  margin-bottom: 14px;
}
.decision-section h3 {
  margin: 0 0 16px 0; font-size: 16px; color: #1C1C1E;
}

.field {
  margin-bottom: 16px;
}
.field-label {
  display: block; font-size: 13px; font-weight: 600;
  color: #3A3A3C; margin-bottom: 8px;
  text-transform: uppercase; letter-spacing: 0.4px;
}
.field-hint {
  font-size: 12.5px; color: #8E8E93; font-weight: 400;
  text-transform: none; letter-spacing: 0;
}

.button-row {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.pick {
  background: #F2F2F7; color: #1C1C1E; border: 2px solid transparent;
  padding: 10px 16px; border-radius: 9px; font-size: 14px;
  cursor: pointer; font-weight: 500; flex: 1 1 auto; min-width: 120px;
  transition: all 0.1s ease;
}
.pick:hover { background: #E5E5EA; }
.pick.selected {
  background: #0A84FF; color: #fff; border-color: #0A84FF;
  box-shadow: 0 2px 8px rgba(10,132,255,0.3);
}
.pick.selected.green { background: #30D158; border-color: #30D158; color: #000; }
.pick.selected.red { background: #FF453A; border-color: #FF453A; }
.pick.selected.purple { background: #BF5AF2; border-color: #BF5AF2; }

.notes {
  width: 100%; padding: 10px 12px; border-radius: 8px;
  border: 1px solid #D1D1D6; font-family: inherit; font-size: 14px;
  resize: vertical; min-height: 60px;
}
.notes:focus { outline: 2px solid #0A84FF; border-color: #0A84FF; }

.quick-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
.quick-actions button {
  background: #fff; color: #0A84FF; border: 1.5px solid #0A84FF;
  padding: 8px 16px; border-radius: 8px; font-size: 14px;
  cursor: pointer; font-weight: 500;
}
.quick-actions button:hover { background: #0A84FF; color: #fff; }

.footer {
  text-align: center; color: #8E8E93; font-size: 12px; padding: 16px;
}
.status-pill {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 600; margin-left: 8px;
}
.status-pill.done { background: #D4EDDA; color: #155724; }
.status-pill.pending { background: #FFF3CD; color: #664D03; }

kbd {
  background: #2C2C2E; color: #fff; padding: 2px 6px; border-radius: 4px;
  font-size: 12px; font-family: ui-monospace, "SF Mono", Consolas, monospace;
}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>Pilot 120 Review</h1>
    <div class="progress-box">
      <div class="progress-bar"><div id="pbar" class="progress-fill" style="width:0%"></div></div>
      <div class="progress-text"><span id="pdone">0</span> de <span id="ptotal">0</span> classificados -- <span id="pcurrent">1</span>/<span id="pctotal">0</span> visualizando</div>
    </div>
    <div class="nav-controls">
      <button id="btnPrev">&larr; anterior</button>
      <select id="jumpSelect"></select>
      <button id="btnNext" class="primary">proximo &rarr;</button>
      <button id="btnDownload" class="success">baixar CSV</button>
    </div>
  </header>

  <div class="card" id="wineCard">
    <div id="wineContent"></div>
  </div>

  <div class="decision-section">
    <h3>Sua decisao
      <span id="doneStatus" class="status-pill pending">nao preenchido</span>
    </h3>

    <div class="field">
      <label class="field-label">
        business_class
        <span class="field-hint">&mdash; que tipo de wine e?</span>
      </label>
      <div class="button-row" id="bcRow">
        <button class="pick" data-val="MATCH_RENDER">MATCH_RENDER</button>
        <button class="pick" data-val="MATCH_IMPORT">MATCH_IMPORT</button>
        <button class="pick" data-val="STANDALONE_WINE">STANDALONE_WINE</button>
        <button class="pick" data-val="NOT_WINE">NOT_WINE</button>
      </div>
    </div>

    <div class="field">
      <label class="field-label">
        review_state
        <span class="field-hint">&mdash; voce decidiu?</span>
      </label>
      <div class="button-row" id="rsRow">
        <button class="pick" data-val="RESOLVED">RESOLVED</button>
        <button class="pick" data-val="SECOND_REVIEW">SECOND_REVIEW</button>
        <button class="pick" data-val="UNRESOLVED">UNRESOLVED</button>
      </div>
    </div>

    <div class="field">
      <label class="field-label">
        confidence
        <span class="field-hint">&mdash; quanta certeza?</span>
      </label>
      <div class="button-row" id="cfRow">
        <button class="pick" data-val="HIGH">HIGH</button>
        <button class="pick" data-val="MEDIUM">MEDIUM</button>
        <button class="pick" data-val="LOW">LOW</button>
      </div>
    </div>

    <div class="field">
      <label class="field-label">
        action
        <span class="field-hint">&mdash; preenchido automaticamente pelo business_class, mas pode mudar</span>
      </label>
      <div class="button-row" id="acRow">
        <button class="pick" data-val="ALIAS">ALIAS</button>
        <button class="pick" data-val="IMPORT_THEN_ALIAS">IMPORT_THEN_ALIAS</button>
        <button class="pick" data-val="KEEP_STANDALONE">KEEP_STANDALONE</button>
        <button class="pick" data-val="SUPPRESS">SUPPRESS</button>
      </div>
    </div>

    <div class="field">
      <label class="field-label">notes <span class="field-hint">&mdash; opcional</span></label>
      <textarea class="notes" id="notes" placeholder="anotacao livre (opcional)"></textarea>
    </div>

    <div class="quick-actions">
      <button id="btnAcceptClaude">aceitar sugestao do Claude</button>
      <button id="btnClear">limpar este row</button>
    </div>
  </div>

  <div class="footer">
    Atalhos: <kbd>&larr;</kbd> anterior, <kbd>&rarr;</kbd> proximo, <kbd>Ctrl+S</kbd> baixar CSV.
    Progresso salvo automaticamente no navegador.
  </div>

</div>

<script>
// ==== dados embutidos ====
const PILOT = __PILOT_JSON__;
const HEADERS = __HEADERS_JSON__;

// ==== estado ====
let currentIdx = 0;
const storageKey = "winegod_pilot120_reviews_v2";

function loadSaved() {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return {};
    return JSON.parse(raw);
  } catch(e) { return {}; }
}
function saveAll(state) {
  localStorage.setItem(storageKey, JSON.stringify(state));
}
let STATE = loadSaved();

// Default action por business_class
const BC_TO_ACTION = {
  "MATCH_RENDER": "ALIAS",
  "MATCH_IMPORT": "IMPORT_THEN_ALIAS",
  "STANDALONE_WINE": "KEEP_STANDALONE",
  "NOT_WINE": "SUPPRESS",
};

function getWineState(wid) {
  return STATE[wid] || {
    murilo_business_class: "",
    murilo_review_state: "",
    murilo_confidence: "",
    murilo_action: "",
    murilo_notes: "",
  };
}
function setWineField(wid, field, val) {
  if (!STATE[wid]) STATE[wid] = getWineState(wid);
  STATE[wid][field] = val;
  saveAll(STATE);
  updateProgress();
  updateStatusPill();
}

function isComplete(wid) {
  const s = STATE[wid];
  if (!s) return false;
  return s.murilo_business_class && s.murilo_review_state && s.murilo_confidence && s.murilo_action;
}

function updateProgress() {
  let done = 0;
  for (const row of PILOT) {
    if (isComplete(row.render_wine_id)) done++;
  }
  document.getElementById("pdone").innerText = done;
  document.getElementById("ptotal").innerText = PILOT.length;
  document.getElementById("pbar").style.width = (done * 100 / PILOT.length) + "%";
  document.getElementById("pcurrent").innerText = (currentIdx + 1);
  document.getElementById("pctotal").innerText = PILOT.length;
}
function updateStatusPill() {
  const wid = PILOT[currentIdx].render_wine_id;
  const pill = document.getElementById("doneStatus");
  if (isComplete(wid)) {
    pill.className = "status-pill done";
    pill.innerText = "preenchido";
  } else {
    pill.className = "status-pill pending";
    pill.innerText = "nao preenchido";
  }
}

// ==== render ====
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function formatTop3(s) {
  if (!s) return "";
  return s.split(" || ").join("\n");
}

function renderWineCard() {
  const row = PILOT[currentIdx];
  const wid = row.render_wine_id;

  const flags = [];
  flags.push('<span class="flag info">bucket: ' + esc(row.pilot_bucket_proxy) + '</span>');
  if (row.wine_filter_category) {
    flags.push('<span class="flag danger">wine_filter: ' + esc(row.wine_filter_category) + '</span>');
  }
  if (row.y2_any_not_wine_or_spirit === "1") {
    flags.push('<span class="flag warning">y2 flagou not_wine</span>');
  }
  if (row.no_source_flag === "1") {
    flags.push('<span class="flag warning">no_source_flag</span>');
  }

  let html = '';
  html += '<div class="wine-title">' + esc(row.nome || "(sem nome)") + '</div>';
  html += '<div class="wine-meta">';
  html += '<span><strong>produtor:</strong> ' + esc(row.produtor || "-") + '</span>';
  if (row.safra) html += '<span><strong>safra:</strong> ' + esc(row.safra) + '</span>';
  if (row.tipo) html += '<span><strong>tipo:</strong> ' + esc(row.tipo) + '</span>';
  if (row.preco_min) html += '<span><strong>preco:</strong> ' + esc(row.preco_min) + '</span>';
  if (row.wine_sources_count_live) html += '<span><strong>sources:</strong> ' + esc(row.wine_sources_count_live) + '</span>';
  html += '<span><strong>wid:</strong> ' + esc(row.render_wine_id) + '</span>';
  html += '</div>';

  if (flags.length) {
    html += '<div class="flag-strip">' + flags.join('') + '</div>';
  }

  // Render candidate
  html += '<div class="candidate-block render">';
  html += '<h4>top1 render</h4>';
  if (row.top1_render_human) {
    html += '<div class="top1">' + esc(row.top1_render_human) + '</div>';
  } else {
    html += '<div class="top1 empty">(sem candidato render)</div>';
  }
  if (row.top3_render_summary) {
    html += '<div class="top3"><strong>top3:</strong>\n' + esc(formatTop3(row.top3_render_summary)) + '</div>';
  }
  html += '</div>';

  // Import candidate
  html += '<div class="candidate-block import">';
  html += '<h4>top1 import</h4>';
  if (row.top1_import_human) {
    html += '<div class="top1">' + esc(row.top1_import_human) + '</div>';
  } else {
    html += '<div class="top1 empty">(sem candidato import)</div>';
  }
  if (row.top3_import_summary) {
    html += '<div class="top3"><strong>top3:</strong>\n' + esc(formatTop3(row.top3_import_summary)) + '</div>';
  }
  html += '</div>';

  // Claude R1 suggestion (com botao inline de aceitar + avancar)
  html += '<div class="claude-suggestion">';
  html += '<div class="suggestion-body">';
  html += '<h4>sugestao R1 Claude</h4>';
  html += '<div class="r1-values">';
  if (row.r1_business_class) html += '<span class="r1-tag">' + esc(row.r1_business_class) + '</span>';
  if (row.r1_review_state) html += '<span class="r1-tag">' + esc(row.r1_review_state) + '</span>';
  if (row.r1_confidence) html += '<span class="r1-tag">' + esc(row.r1_confidence) + '</span>';
  if (row.r1_action) html += '<span class="r1-tag">' + esc(row.r1_action) + '</span>';
  html += '</div>';
  if (row.r1_reason_short) html += '<div class="r1-reason"><strong>motivo:</strong> ' + esc(row.r1_reason_short) + '</div>';
  html += '</div>';
  html += '<button class="accept-btn" id="btnAcceptInline"><span class="check">&check;</span>concordo &mdash; proximo</button>';
  html += '</div>';

  document.getElementById("wineContent").innerHTML = html;

  // O botao inline e recriado a cada render; rebinda aqui
  const inlineBtn = document.getElementById("btnAcceptInline");
  if (inlineBtn) {
    inlineBtn.addEventListener("click", acceptClaudeAndNext);
  }

  // Render selected buttons based on STATE
  renderPicks();
}

function acceptClaudeAndNext() {
  acceptClaude();
  // pequena pausa para o usuario ver o preenchimento antes de avancar
  setTimeout(() => goTo(currentIdx + 1), 180);
}

function renderPicks() {
  const row = PILOT[currentIdx];
  const wid = row.render_wine_id;
  const s = getWineState(wid);
  applyPicks("bcRow", s.murilo_business_class, "green");
  applyPicks("rsRow", s.murilo_review_state, "green");
  applyPicks("cfRow", s.murilo_confidence, "green");
  applyPicks("acRow", s.murilo_action, "green");
  document.getElementById("notes").value = s.murilo_notes || "";
  updateStatusPill();
  updateProgress();
}
function applyPicks(rowId, val, styleClass) {
  const row = document.getElementById(rowId);
  const btns = row.querySelectorAll("button.pick");
  btns.forEach(b => {
    b.classList.remove("selected", "green", "red", "purple");
    if (b.dataset.val === val) {
      b.classList.add("selected");
      if (styleClass) b.classList.add(styleClass);
    }
  });
}

// ==== event handlers ====
function bindPicks(rowId, field, auto) {
  const row = document.getElementById(rowId);
  row.querySelectorAll("button.pick").forEach(b => {
    b.addEventListener("click", () => {
      const wid = PILOT[currentIdx].render_wine_id;
      const val = b.dataset.val;
      setWineField(wid, field, val);
      // auto-fill action when business_class changes
      if (field === "murilo_business_class" && BC_TO_ACTION[val]) {
        const s = getWineState(wid);
        if (!s.murilo_action) {
          setWineField(wid, "murilo_action", BC_TO_ACTION[val]);
        }
      }
      renderPicks();
    });
  });
}

function onNotesChange() {
  const wid = PILOT[currentIdx].render_wine_id;
  setWineField(wid, "murilo_notes", document.getElementById("notes").value);
}

function goTo(idx) {
  if (idx < 0) idx = 0;
  if (idx >= PILOT.length) idx = PILOT.length - 1;
  currentIdx = idx;
  document.getElementById("jumpSelect").value = idx;
  renderWineCard();
  window.scrollTo(0, 0);
}

function buildJumpSelect() {
  const sel = document.getElementById("jumpSelect");
  for (let i = 0; i < PILOT.length; i++) {
    const opt = document.createElement("option");
    opt.value = i;
    opt.innerText = (i + 1) + " / " + PILOT.length;
    sel.appendChild(opt);
  }
  sel.addEventListener("change", (e) => goTo(parseInt(e.target.value)));
}

function acceptClaude() {
  const row = PILOT[currentIdx];
  const wid = row.render_wine_id;
  setWineField(wid, "murilo_business_class", row.r1_business_class || "");
  setWineField(wid, "murilo_review_state", row.r1_review_state || "");
  setWineField(wid, "murilo_confidence", row.r1_confidence || "");
  setWineField(wid, "murilo_action", row.r1_action || "");
  renderPicks();
}

function clearRow() {
  const wid = PILOT[currentIdx].render_wine_id;
  STATE[wid] = {
    murilo_business_class: "",
    murilo_review_state: "",
    murilo_confidence: "",
    murilo_action: "",
    murilo_notes: "",
  };
  saveAll(STATE);
  renderPicks();
}

function downloadCSV() {
  // Build CSV using original PILOT rows + STATE injection
  const rows = [];
  rows.push(HEADERS.map(csvCell).join(","));
  for (const row of PILOT) {
    const s = getWineState(row.render_wine_id);
    const rowCopy = Object.assign({}, row, {
      murilo_business_class: s.murilo_business_class,
      murilo_review_state: s.murilo_review_state,
      murilo_confidence: s.murilo_confidence,
      murilo_action: s.murilo_action,
      murilo_notes: s.murilo_notes,
    });
    rows.push(HEADERS.map(h => csvCell(rowCopy[h] || "")).join(","));
  }
  const csv = rows.join("\r\n");
  // UTF-8 BOM para Excel reconhecer
  const blob = new Blob(["\uFEFF" + csv], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tail_pilot_120_for_murilo_2026-04-10.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function csvCell(v) {
  if (v === null || v === undefined) v = "";
  v = String(v);
  if (v.includes(",") || v.includes("\"") || v.includes("\n") || v.includes("\r")) {
    return '"' + v.replace(/"/g, '""') + '"';
  }
  return v;
}

// ==== keyboard ====
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft") { goTo(currentIdx - 1); }
  if (e.key === "ArrowRight") { goTo(currentIdx + 1); }
  if (e.ctrlKey && e.key === "s") { e.preventDefault(); downloadCSV(); }
});

// ==== init ====
document.addEventListener("DOMContentLoaded", () => {
  buildJumpSelect();
  bindPicks("bcRow", "murilo_business_class", true);
  bindPicks("rsRow", "murilo_review_state", false);
  bindPicks("cfRow", "murilo_confidence", false);
  bindPicks("acRow", "murilo_action", false);
  document.getElementById("notes").addEventListener("input", onNotesChange);
  document.getElementById("btnPrev").addEventListener("click", () => goTo(currentIdx - 1));
  document.getElementById("btnNext").addEventListener("click", () => goTo(currentIdx + 1));
  document.getElementById("btnAcceptClaude").addEventListener("click", acceptClaude);
  document.getElementById("btnClear").addEventListener("click", clearRow);
  document.getElementById("btnDownload").addEventListener("click", downloadCSV);

  // Start at first unanswered wine, or 0
  let start = 0;
  for (let i = 0; i < PILOT.length; i++) {
    if (!isComplete(PILOT[i].render_wine_id)) { start = i; break; }
  }
  goTo(start);
});
</script>
</body>
</html>
"""


def main():
    with open(IN_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)
    print(f"[read] {len(rows)} rows, {len(headers)} cols")

    pilot_json = json.dumps(rows, ensure_ascii=False)
    headers_json = json.dumps(headers, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__PILOT_JSON__", pilot_json).replace("__HEADERS_JSON__", headers_json)

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[write] {OUT_HTML}")
    print()
    print(f"Abra no navegador (double-click):")
    print(f"  {OUT_HTML}")


if __name__ == "__main__":
    main()
