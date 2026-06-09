"use strict";

/* ------------------------------------------------------------------ *
 * Transfer Center Protocol Engine — front-end controller
 * Vanilla JS, no build step. Source of truth lives in `state`; the DOM
 * is rendered from it and user actions write back into it.
 * ------------------------------------------------------------------ */

const state = {
  library: [],            // protocol-set summaries from /api/pathways
  activeSet: null,        // selected set id
  protocol: null,         // full selected protocol set
  caseFields: {},         // captured call/patient details
  caseStartedAt: null,    // ms epoch; set on first action
  caseClockInterval: null,
  instances: new Map(),   // instanceId -> running protocol instance
  events: [],             // audit log entries { at, label }
};

const el = (id) => document.getElementById(id);
const statusNode = el("status");
const statusText = el("statusText");
const libraryList = el("libraryList");
const contactsPanel = el("contactsPanel");
const contactsList = el("contactsList");
const triagePanel = el("triagePanel");
const triagePrompt = el("triagePrompt");
const triageOptions = el("triageOptions");
const pathwaySelect = el("pathwaySelect");
const activeProtocols = el("activeProtocols");
const timeline = el("timeline");
const caseClock = el("caseClock");
const caseBar = el("caseBar");
const toast = el("toast");

/* -- small utilities ------------------------------------------------ */

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtClock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function timeOfDay(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function showToast(message, kind = "") {
  toast.textContent = message;
  toast.className = `toast show ${kind}`.trim();
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => (toast.className = "toast"), 4000);
}

function setStatus(kind, text) {
  statusNode.className = `status ${kind}`;
  statusText.textContent = text;
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status}).`);
  return payload;
}

/* -- case clock + audit log ----------------------------------------- */

function ensureCaseStarted() {
  if (state.caseStartedAt) return;
  state.caseStartedAt = Date.now();
  const tick = () => (caseClock.textContent = fmtClock(Date.now() - state.caseStartedAt));
  tick();
  state.caseClockInterval = window.setInterval(tick, 1000);
}

function logEvent(label) {
  ensureCaseStarted();
  state.events.push({ at: new Date().toISOString(), label });
  renderTimeline();
}

function renderTimeline() {
  if (!state.events.length) {
    timeline.innerHTML = '<div class="empty">Actions you take are recorded here with timestamps.</div>';
    return;
  }
  timeline.innerHTML = state.events
    .slice()
    .reverse()
    .map(
      (event) => `
      <div class="timeline-item">
        <span class="timeline-time">${esc(timeOfDay(new Date(event.at)))}</span>
        <span class="timeline-detail">${esc(event.label)}</span>
      </div>`
    )
    .join("");
}

/* -- library -------------------------------------------------------- */

async function loadLibrary() {
  const payload = await api("/api/pathways");
  state.library = payload.pathways;
  renderLibrary();
  if (!state.activeSet && state.library.length) {
    await selectProtocolSet(state.library[0].id);
  }
}

function renderLibrary() {
  if (!state.library.length) {
    libraryList.innerHTML = '<div class="empty">No pathways uploaded yet.</div>';
    return;
  }
  libraryList.innerHTML = "";
  state.library.forEach((item) => {
    const button = document.createElement("button");
    button.className = `library-item ${state.activeSet === item.id ? "active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <div class="row">
        <strong>${esc(item.title)}</strong>
        <span class="ghost-delete" title="Delete">✕</span>
      </div>
      <div class="row">
        <span class="subtle">${item.pathway_count} pathway${item.pathway_count === 1 ? "" : "s"}</span>
        ${item.has_triage ? '<span class="pill accent">triage</span>' : ""}
      </div>`;
    button.addEventListener("click", (event) => {
      if (event.target.classList.contains("ghost-delete")) {
        deletePathway(item);
      } else {
        selectProtocolSet(item.id);
      }
    });
    libraryList.appendChild(button);
  });
}

async function deletePathway(item) {
  if (!window.confirm(`Delete protocol set "${item.title}"? This cannot be undone.`)) return;
  try {
    await api(`/api/pathways/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    if (state.activeSet === item.id) {
      state.activeSet = null;
      state.protocol = null;
      triagePanel.hidden = true;
      contactsPanel.hidden = true;
    }
    showToast(`Deleted ${item.title}.`, "ok");
    await loadLibrary();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function selectProtocolSet(id) {
  state.protocol = await api(`/api/pathways/${encodeURIComponent(id)}`);
  state.activeSet = id;
  renderLibrary();
  renderTriage();
  renderContacts();
  setStatus("online", `${state.protocol.title} selected`);
}

/* -- triage + contacts ---------------------------------------------- */

function renderTriage() {
  const protocol = state.protocol;
  const entry = protocol.entry || {};
  triagePrompt.textContent = entry.prompt || "Choose a pathway";

  const options = entry.options || [];
  triageOptions.innerHTML = options
    .map(
      (option, index) => `
      <button class="triage-option" type="button" data-next="${esc(option.next)}" data-index="${index}">
        <span>${esc(option.label)}</span>
        <span class="arrow">Open →</span>
      </button>`
    )
    .join("");
  triageOptions.querySelectorAll(".triage-option").forEach((button) => {
    button.addEventListener("click", () => openPathway(button.dataset.next));
  });

  // Direct dropdown: choosing a pathway opens it immediately, then resets.
  const pathways = Object.entries(protocol.pathways);
  pathwaySelect.innerHTML =
    '<option value="">Select a pathway to open…</option>' +
    pathways.map(([key, pathway]) => `<option value="${esc(key)}">${esc(pathway.title || key)}</option>`).join("");

  triagePanel.hidden = false;
}

function renderContacts() {
  const contacts = state.protocol.contacts;
  if (!contacts || !Object.keys(contacts).length) {
    contactsPanel.hidden = true;
    return;
  }
  contactsList.innerHTML = Object.entries(contacts)
    .map(
      ([name, value]) => `
      <div class="contact-row">
        <span class="name">${esc(name.replaceAll("_", " "))}</span>
        <span class="value">${esc(value)}</span>
      </div>`
    )
    .join("");
  contactsPanel.hidden = false;
}

/* -- opening + running a pathway ------------------------------------ */

function openPathway(pathwayId) {
  if (!state.protocol || !pathwayId) return;
  const pathway = state.protocol.pathways[pathwayId];
  if (!pathway) {
    showToast("That pathway could not be found.", "error");
    return;
  }

  const instanceId = `${state.activeSet}:${pathwayId}:${Date.now()}`;
  const alertMin = Number(pathway.escalation_minutes) || 10;
  const warnMin = Math.max(1, Math.floor(alertMin / 2));

  const instance = {
    instanceId,
    setId: state.activeSet,
    setTitle: state.protocol.title,
    pathwayId,
    title: pathway.title,
    startedAt: Date.now(),
    intervalId: null,
    warnMin,
    alertMin,
    steps: (pathway.steps || []).map((text) => ({ text, done: false, doneAt: null, note: "" })),
    decisions: [],
  };
  state.instances.set(instanceId, instance);

  if (activeProtocols.querySelector(".empty")) activeProtocols.innerHTML = "";
  const card = buildCard(instance, pathway);
  activeProtocols.prepend(card);
  startTimer(instance, card);
  logEvent(`Opened pathway: ${pathway.title}`);
}

function buildCard(instance, pathway) {
  const card = document.createElement("article");
  card.className = "protocol-card";
  card.dataset.instanceId = instance.instanceId;
  card.innerHTML = `
    <div class="protocol-header">
      <div>
        <h2>${esc(pathway.title)}</h2>
        <div class="subtle">${esc(pathway.trigger || instance.setTitle)}</div>
      </div>
      <div class="stack" style="justify-items:end">
        <span class="timer">00:00</span>
        <button class="danger ghost close-protocol" type="button">Close</button>
      </div>
    </div>
    ${instance.steps.length ? '<div class="progress"><span></span></div>' : ""}
    ${renderSteps(instance)}
    ${renderDecisions(pathway)}
    ${renderDestination(pathway)}
    ${renderPageFormat(pathway)}
  `;

  wireSteps(instance, card);
  wireDecisions(instance, card);
  wirePageFormat(card);

  card.querySelector(".close-protocol").addEventListener("click", () => closeInstance(instance.instanceId));
  return card;
}

function renderSteps(instance) {
  if (!instance.steps.length) return "";
  const rows = instance.steps
    .map(
      (step, index) => `
      <div class="step" data-index="${index}">
        <div class="step-main">
          <label class="step-click">
            <input type="checkbox">
            <span class="step-text">${index + 1}. ${esc(step.text)}</span>
          </label>
          <div class="step-meta">
            <span class="step-time" hidden></span>
            <button class="ghost note-toggle" type="button">Note</button>
          </div>
        </div>
        <div class="step-note" hidden>
          <textarea placeholder="Add a note (recorded in the audit trail)…"></textarea>
        </div>
      </div>`
    )
    .join("");
  return `<div class="section-label">Checklist · <span class="step-count">0/${instance.steps.length}</span></div><div class="step-list">${rows}</div>`;
}

function wireSteps(instance, card) {
  const updateProgress = () => {
    const done = instance.steps.filter((s) => s.done).length;
    const total = instance.steps.length;
    const bar = card.querySelector(".progress > span");
    if (bar) bar.style.width = total ? `${Math.round((done / total) * 100)}%` : "0%";
    const counter = card.querySelector(".step-count");
    if (counter) counter.textContent = `${done}/${total}`;
  };

  card.querySelectorAll(".step").forEach((row) => {
    const index = Number(row.dataset.index);
    const step = instance.steps[index];
    const checkbox = row.querySelector('input[type="checkbox"]');
    const timeNode = row.querySelector(".step-time");
    const noteWrap = row.querySelector(".step-note");
    const noteField = row.querySelector("textarea");

    checkbox.addEventListener("change", () => {
      step.done = checkbox.checked;
      row.classList.toggle("done", step.done);
      if (step.done) {
        step.doneAt = new Date().toISOString();
        timeNode.textContent = `✓ ${timeOfDay(new Date(step.doneAt))}`;
        timeNode.hidden = false;
        logEvent(`[${instance.title}] ${step.text}`);
      } else {
        step.doneAt = null;
        timeNode.hidden = true;
      }
      updateProgress();
    });

    row.querySelector(".note-toggle").addEventListener("click", () => {
      noteWrap.hidden = !noteWrap.hidden;
      if (!noteWrap.hidden) noteField.focus();
    });

    noteField.addEventListener("change", () => {
      const value = noteField.value.trim();
      if (value && value !== step.note) logEvent(`Note · ${instance.title}: ${value}`);
      step.note = value;
    });
  });

  updateProgress();
}

function renderDecisions(pathway) {
  if (!pathway.decision_points || !pathway.decision_points.length) return "";
  return pathway.decision_points
    .map(
      (point, index) => `
      <div class="decision" data-decision-index="${index}">
        <div class="q">${esc(point.question)}</div>
        <div class="choice-row">
          <button class="yes" type="button" data-answer="yes">Yes</button>
          <button class="no" type="button" data-answer="no">No</button>
        </div>
        <div class="branch yes-branch" hidden>
          <strong>If yes</strong>
          <ul>${(point.yes || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
        </div>
        <div class="branch no-branch" hidden>
          <strong>If no</strong>
          <ul>${(point.no || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
        </div>
      </div>`
    )
    .join("");
}

function wireDecisions(instance, card) {
  const pathway = state.protocol.pathways[instance.pathwayId];
  card.querySelectorAll(".decision").forEach((node) => {
    const index = Number(node.dataset.decisionIndex);
    const question = (pathway.decision_points[index] || {}).question || "Decision";
    const yesBranch = node.querySelector(".yes-branch");
    const noBranch = node.querySelector(".no-branch");
    node.querySelectorAll(".choice-row button").forEach((button) => {
      button.addEventListener("click", () => {
        const answer = button.dataset.answer;
        node.querySelectorAll(".choice-row button").forEach((b) => b.classList.remove("chosen"));
        button.classList.add("chosen");
        yesBranch.hidden = answer !== "yes";
        noBranch.hidden = answer !== "no";
        instance.decisions[index] = { question, answer };
        logEvent(`Decision · ${question} → ${answer.toUpperCase()}`);
      });
    });
  });
}

function renderDestination(pathway) {
  if (!pathway.destination_guidance) return "";
  const boxes = Object.entries(pathway.destination_guidance)
    .map(([key, value]) => {
      const lines = [];
      if (value.call) lines.push(`<p><strong>Call:</strong> ${esc(value.call)}</p>`);
      if (value.call_7am_9pm) lines.push(`<p><strong>7am–9pm:</strong> ${esc(value.call_7am_9pm)}</p>`);
      if (value.pager_9pm_7am) lines.push(`<p><strong>9pm–7am pager:</strong> ${esc(value.pager_9pm_7am)}</p>`);
      if (value.criteria) lines.push(`<ul>${value.criteria.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`);
      if (value.examples) lines.push(`<ul>${value.examples.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`);
      if (value.notes) lines.push(`<p>${esc(value.notes.join(" "))}</p>`);
      return `<section class="info-box"><h3>${esc(key.replaceAll("_", " "))}</h3>${lines.join("")}</section>`;
    })
    .join("");
  return `<div class="section-label">Destination Guidance</div><div class="info-grid">${boxes}</div>`;
}

function renderPageFormat(pathway) {
  if (!pathway.page_format || !pathway.page_format.length) return "";
  return `
    <div class="page-format-wrap">
      <div class="page-format-head">
        <span class="section-label" style="border:0;padding:0;background:none">Page / Message Format</span>
        <button class="ghost copy-page" type="button">Copy</button>
      </div>
      <pre class="page-format">${esc(pathway.page_format.join("\n"))}</pre>
    </div>`;
}

function wirePageFormat(card) {
  const button = card.querySelector(".copy-page");
  if (!button) return;
  button.addEventListener("click", async () => {
    const text = card.querySelector(".page-format").textContent;
    try {
      await navigator.clipboard.writeText(text);
      showToast("Page format copied.", "ok");
    } catch {
      showToast("Copy not available in this browser.", "error");
    }
  });
}

function startTimer(instance, card) {
  const timer = card.querySelector(".timer");
  const tick = () => {
    const elapsed = Date.now() - instance.startedAt;
    timer.textContent = fmtClock(elapsed);
    const minutes = elapsed / 60000;
    timer.classList.toggle("warn", minutes >= instance.warnMin && minutes < instance.alertMin);
    timer.classList.toggle("alert", minutes >= instance.alertMin);
  };
  tick();
  instance.intervalId = window.setInterval(tick, 1000);
}

function closeInstance(instanceId) {
  const instance = state.instances.get(instanceId);
  if (!instance) return;
  window.clearInterval(instance.intervalId);
  state.instances.delete(instanceId);
  const card = activeProtocols.querySelector(`[data-instance-id="${CSS.escape(instanceId)}"]`);
  if (card) card.remove();
  logEvent(`Closed pathway: ${instance.title}`);
  if (!state.instances.size) {
    activeProtocols.innerHTML = '<article class="panel empty">No active protocols. Choose a pathway above to begin.</article>';
  }
}

/* -- case fields, save, export, reset ------------------------------- */

function wireCaseFields() {
  document.querySelectorAll("[data-field]").forEach((node) => {
    const field = node.dataset.field;
    state.caseFields[field] = node.value || "";
    const handler = () => {
      state.caseFields[field] = node.value;
      ensureCaseStarted();
      if (field === "acuity") applyAcuityStyle(node.value);
    };
    node.addEventListener("input", handler);
    node.addEventListener("change", handler);
  });
  applyAcuityStyle(state.caseFields.acuity);
}

function applyAcuityStyle(acuity) {
  caseBar.className = `panel-section case-bar acuity-${(acuity || "").replaceAll(" ", "-")}`;
}

function buildSnapshot() {
  const startedAt = state.caseStartedAt ? new Date(state.caseStartedAt).toISOString() : null;
  const elapsedSeconds = state.caseStartedAt ? Math.floor((Date.now() - state.caseStartedAt) / 1000) : 0;
  return {
    case_id: state.caseFields.case_id || "",
    caller: state.caseFields.caller || "",
    callback: state.caseFields.callback || "",
    patient: state.caseFields.patient || "",
    dob: state.caseFields.dob || "",
    facility: state.caseFields.facility || "",
    location: state.caseFields.location || "",
    acuity: state.caseFields.acuity || "",
    protocol_set: state.activeSet,
    started_at: startedAt,
    elapsed_seconds: elapsedSeconds,
    protocols: [...state.instances.values()].map((instance) => ({
      set: instance.setId,
      pathway_id: instance.pathwayId,
      title: instance.title,
      started_at: new Date(instance.startedAt).toISOString(),
      elapsed_seconds: Math.floor((Date.now() - instance.startedAt) / 1000),
      steps: instance.steps.map((s) => ({ text: s.text, done: s.done, done_at: s.doneAt, note: s.note })),
      decisions: instance.decisions.filter(Boolean),
    })),
    events: state.events,
  };
}

async function saveCase() {
  try {
    const snapshot = buildSnapshot();
    const result = await api("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    });
    if (!state.caseFields.case_id) {
      state.caseFields.case_id = result.case_id;
      el("caseId").value = result.case_id;
    }
    showToast(`Case saved as ${result.case_id}.`, "ok");
    logEvent(`Case saved (${result.case_id})`);
  } catch (error) {
    showToast(`Save failed: ${error.message}`, "error");
  }
}

function exportCase() {
  const snapshot = buildSnapshot();
  const name = (snapshot.case_id || `case-${new Date().toISOString().slice(0, 10)}`).replace(/[^a-z0-9_-]+/gi, "_");
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}.json`;
  link.click();
  URL.revokeObjectURL(url);
  showToast("Case exported.", "ok");
}

function resetCase() {
  if (state.instances.size && !window.confirm("Start a new case? Open protocols and the current timeline will be cleared.")) {
    return;
  }
  state.instances.forEach((instance) => window.clearInterval(instance.intervalId));
  state.instances.clear();
  window.clearInterval(state.caseClockInterval);
  state.caseClockInterval = null;
  state.caseStartedAt = null;
  state.events = [];
  caseClock.textContent = "00:00";
  activeProtocols.innerHTML = '<article class="panel empty">Select a protocol set, then choose a pathway. It opens automatically into the active call.</article>';
  document.querySelectorAll("[data-field]").forEach((node) => {
    if (node.tagName === "SELECT") node.selectedIndex = node.id === "acuity" ? 1 : 0;
    else node.value = "";
    state.caseFields[node.dataset.field] = node.value;
  });
  applyAcuityStyle(state.caseFields.acuity);
  renderTimeline();
  showToast("New case started.", "ok");
}

/* -- clipboard copy (per-field + copy-all) -------------------------- */

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function wireCopyButtons() {
  document.querySelectorAll(".copy-field").forEach((button) => {
    button.addEventListener("click", async () => {
      const field = button.dataset.copy;
      const value = state.caseFields[field] || "";
      if (!value) {
        showToast("Field is empty.", "error");
        return;
      }
      if (await copyToClipboard(value)) {
        button.classList.add("copied");
        button.textContent = "✓";
        window.setTimeout(() => {
          button.classList.remove("copied");
          button.textContent = "⎘";
        }, 1500);
      } else {
        showToast("Copy not available in this browser.", "error");
      }
    });
  });

  el("copyAllButton").addEventListener("click", async () => {
    const lines = [
      `Case ID:    ${state.caseFields.case_id || "—"}`,
      `Patient:    ${state.caseFields.patient || "—"}`,
      `DOB:        ${state.caseFields.dob || "—"}`,
      `Acuity:     ${state.caseFields.acuity || "—"}`,
      `Caller:     ${state.caseFields.caller || "—"}`,
      `Callback:   ${state.caseFields.callback || "—"}`,
      `Facility:   ${state.caseFields.facility || "—"}`,
      `Location:   ${state.caseFields.location || "—"}`,
    ];
    if (await copyToClipboard(lines.join("\n"))) {
      showToast("All fields copied to clipboard.", "ok");
    } else {
      showToast("Copy not available in this browser.", "error");
    }
  });
}

/* -- autofill staging ----------------------------------------------- */

async function stageAutofill() {
  const snapshot = buildSnapshot();
  try {
    await api("/api/autofill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    });
    const badge = el("autofillStatus");
    badge.textContent = "Staged";
    badge.className = "autofill-status staged";
    showToast("Case staged for autofill. Click the bookmarklet on the target form.", "ok");
    logEvent("Case staged for autofill");
  } catch (error) {
    showToast(`Stage failed: ${error.message}`, "error");
  }
}

/* -- bookmarklet generation ----------------------------------------- */

function generateBookmarklet() {
  const code = `(function(){
    fetch('http://127.0.0.1:8787/api/autofill')
      .then(function(r){return r.json()})
      .then(function(d){
        if(!d.case_data){alert('No case staged. Click Stage for Autofill in the Protocol Engine first.');return;}
        var c=d.case_data,maps=d.maps||[],filled=0,host=location.hostname,bestMap=null;
        for(var i=0;i<maps.length;i++){
          var pat=maps[i].url_pattern||'';
          if(pat&&new RegExp(pat.replace(/\\*/g,'.*'),'i').test(location.href)){bestMap=maps[i];break;}
        }
        if(!bestMap&&maps.length)bestMap=maps[0];
        if(!bestMap){alert('Case data ready but no field mappings configured. Go to Autofill & RPA in the Protocol Engine to add a field map.');return;}
        var m=bestMap.mappings||{};
        Object.keys(m).forEach(function(field){
          var sel=m[field];if(!sel)return;
          var el=document.querySelector(sel);
          if(el&&c[field]!=null){
            el.value=c[field];
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
            filled++;
          }
        });
        alert('Protocol Engine: Filled '+filled+' of '+Object.keys(m).length+' fields.');
      })
      .catch(function(e){alert('Autofill error: '+e.message+'\\n\\nMake sure the Protocol Engine server is running at http://127.0.0.1:8787');});
  })();`;

  const minified = code.replace(/\s+/g, " ").trim();
  const href = `javascript:${encodeURIComponent(minified)}`;

  const container = el("bookmarkletContainer");
  const link = document.createElement("a");
  link.className = "bookmarklet-link";
  link.href = href;
  link.textContent = "Autofill from Protocol Engine";
  link.title = "Drag this to your bookmarks bar";
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showToast("Drag this link to your bookmarks bar — don't click it here.", "ok");
  });
  container.appendChild(link);
}

/* -- field map management ------------------------------------------- */

let editingMapId = null;

async function loadFieldMaps() {
  try {
    const data = await api("/api/autofill/maps");
    renderFieldMaps(data.maps || []);
  } catch {
    renderFieldMaps([]);
  }
}

function renderFieldMaps(maps) {
  const list = el("fieldMapList");
  if (!maps.length) {
    list.innerHTML = '<div class="empty" style="padding:8px 0">No field maps yet. Add one to enable the bookmarklet.</div>';
    return;
  }
  list.innerHTML = maps
    .map((map) => {
      const count = Object.keys(map.mappings || {}).length;
      const preview = Object.entries(map.mappings || {})
        .slice(0, 3)
        .map(([field, selector]) => `${esc(field)} → ${esc(selector)}`)
        .join(", ");
      return `
        <div class="field-map-item">
          <div class="row">
            <strong>${esc(map.name)}</strong>
            <div class="button-row">
              <button class="ghost edit-map" type="button" data-id="${esc(map.id)}">Edit</button>
              <button class="ghost danger delete-map" type="button" data-id="${esc(map.id)}">Delete</button>
            </div>
          </div>
          ${map.url_pattern ? `<div class="mapping-preview">URL: ${esc(map.url_pattern)}</div>` : ""}
          <div class="mapping-preview">${count} mapping${count !== 1 ? "s" : ""}: ${esc(preview)}${count > 3 ? "…" : ""}</div>
        </div>`;
    })
    .join("");

  list.querySelectorAll(".edit-map").forEach((button) => {
    button.addEventListener("click", () => editFieldMap(maps.find((m) => m.id === button.dataset.id)));
  });
  list.querySelectorAll(".delete-map").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Delete this field map?")) return;
      try {
        await api(`/api/autofill/maps/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" });
        showToast("Field map deleted.", "ok");
        loadFieldMaps();
      } catch (error) {
        showToast(error.message, "error");
      }
    });
  });
}

function showMapEditor(map) {
  editingMapId = map ? map.id : null;
  el("mapName").value = map ? map.name : "";
  el("mapUrl").value = map ? (map.url_pattern || "") : "";
  const pairs = el("mappingPairs");
  pairs.innerHTML = "";

  const caseFields = ["case_id", "caller", "callback", "patient", "dob", "facility", "location", "acuity"];
  const mappings = map ? (map.mappings || {}) : {};

  if (map) {
    Object.entries(mappings).forEach(([field, selector]) => addMappingPair(field, selector));
  } else {
    addMappingPair("patient", "");
  }

  el("mapEditor").hidden = false;
}

function addMappingPair(field, selector) {
  const pairs = el("mappingPairs");
  const caseFields = ["case_id", "caller", "callback", "patient", "dob", "facility", "location", "acuity"];
  const row = document.createElement("div");
  row.className = "pair";
  row.innerHTML = `
    <div>
      <label>Case Field</label>
      <select class="map-field">
        ${caseFields.map((f) => `<option value="${f}" ${f === field ? "selected" : ""}>${f}</option>`).join("")}
      </select>
    </div>
    <div>
      <label>CSS Selector</label>
      <input class="map-selector" value="${esc(selector)}" placeholder="#patientName or [name='patient']">
    </div>
    <button class="danger ghost remove-pair" type="button">✕</button>`;
  row.querySelector(".remove-pair").addEventListener("click", () => row.remove());
  pairs.appendChild(row);
}

function editFieldMap(map) {
  showMapEditor(map);
}

async function saveFieldMap() {
  const name = el("mapName").value.trim();
  const urlPattern = el("mapUrl").value.trim();
  if (!name) {
    showToast("Map name is required.", "error");
    return;
  }

  const mappings = {};
  el("mappingPairs").querySelectorAll(".pair").forEach((row) => {
    const field = row.querySelector(".map-field").value;
    const selector = row.querySelector(".map-selector").value.trim();
    if (field && selector) mappings[field] = selector;
  });

  if (!Object.keys(mappings).length) {
    showToast("Add at least one field mapping.", "error");
    return;
  }

  const payload = { name, url_pattern: urlPattern, mappings };
  if (editingMapId) payload.id = editingMapId;

  try {
    await api("/api/autofill/maps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showToast(`Field map "${name}" saved.`, "ok");
    el("mapEditor").hidden = true;
    editingMapId = null;
    loadFieldMaps();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function wireAutofill() {
  el("stageAutofillButton").addEventListener("click", stageAutofill);
  generateBookmarklet();
  loadFieldMaps();

  el("addMapButton").addEventListener("click", () => showMapEditor(null));
  el("addPairButton").addEventListener("click", () => addMappingPair("", ""));
  el("saveMapButton").addEventListener("click", saveFieldMap);
  el("cancelMapButton").addEventListener("click", () => {
    el("mapEditor").hidden = true;
    editingMapId = null;
  });

  wireCollapsible("autofillToggle", "autofillBody");
  wireCollapsible("rpaToggle", "rpaBody");
}

function wireCollapsible(headId, bodyId) {
  const head = el(headId);
  const body = el(bodyId);
  head.addEventListener("click", () => {
    head.classList.toggle("open");
    body.classList.toggle("open");
  });
}

/* -- uploads -------------------------------------------------------- */

async function uploadPathway() {
  const file = el("uploadInput").files[0];
  if (!file) {
    showToast("Choose a JSON pathway file first.");
    return;
  }
  try {
    const payload = JSON.parse(await file.text());
    const result = await api("/api/pathways", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showToast(`${result.pathway.title} uploaded.`, "ok");
    await loadLibrary();
    await selectProtocolSet(result.pathway.id);
  } catch (error) {
    showToast(error.message, "error");
  }
}

/* -- boot ----------------------------------------------------------- */

function boot() {
  el("uploadButton").addEventListener("click", uploadPathway);
  pathwaySelect.addEventListener("change", () => {
    const value = pathwaySelect.value;
    if (value) {
      openPathway(value);
      pathwaySelect.value = "";
    }
  });
  el("saveCaseButton").addEventListener("click", saveCase);
  el("exportButton").addEventListener("click", exportCase);
  el("printButton").addEventListener("click", () => window.print());
  el("resetButton").addEventListener("click", resetCase);

  wireCaseFields();
  wireCopyButtons();
  wireAutofill();
  renderTimeline();

  api("/api/health")
    .then(() => setStatus("online", "Backend online"))
    .catch(() => setStatus("offline", "Backend offline"));

  loadLibrary().catch((error) => {
    setStatus("offline", "Backend error");
    showToast(error.message, "error");
  });
}

boot();
