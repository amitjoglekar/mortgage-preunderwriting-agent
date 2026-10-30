/* Pre-Underwriting Agent UI (vanilla JS, no build step). */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => (v == null ? "—" : "$" + Math.round(v).toLocaleString());
const pct = (v) => (v == null ? "—" : v.toFixed(1) + "%");

const STATUS_LABEL = { pass: "Pass", fail: "Fail", warn: "Review", missing: "Missing", info: "Info" };
const state = { status: null, loans: [], loan: null, tab: "rules", filter: "issues", pollTimer: null, openDoc: null, guidelines: null };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
}

/* ------------------------------------------------------------ sidebar */
async function loadStatus() {
  state.status = await api("/api/status");
  const e = $("#engineBadge");
  if (state.status.mode === "claude") {
    e.className = "engine";
    e.innerHTML = `Extraction and advice by <b>Claude</b><br><span class="muted">${esc(state.status.model)}</span>`;
  } else {
    e.className = "engine demo";
    e.innerHTML = `<b>Offline demo mode</b><br>No API key set. Extraction uses a basic parser tuned to the sample files; add ANTHROPIC_API_KEY to use Claude.`;
  }
  const names = { loan_A_clean: "Load sample A: clean purchase", loan_B_issues: "Load sample B: problem file" };
  $("#sampleRow").innerHTML = state.status.samples.map((s) => `<button data-sample="${esc(s)}">${esc(names[s] || s)}</button>`).join("");
}

async function loadLoans() {
  state.loans = await api("/api/loans");
  renderSidebar();
}
function renderSidebar() {
  $("#loanList").innerHTML = state.loans.length
    ? state.loans.map((l) => `
      <button class="loan-item" data-id="${l.id}" aria-current="${state.loan && state.loan.id === l.id}">
        <span class="pip ${esc(l.decision.code)}"></span>
        <span><div class="ln">${esc(l.name)}</div>
        <div class="ls">${esc(l.borrower || "No borrower yet")}, ${l.documents} doc${l.documents === 1 ? "" : "s"}</div></span>
      </button>`).join("")
    : `<div class="muted" style="padding:8px;font-size:12.5px">No loan files yet.</div>`;
}

/* ------------------------------------------------------------ loan */
async function openLoan(id) {
  if (!state.loan || state.loan.id !== id) state.filter = "issues";
  state.loan = await api(`/api/loans/${id}`);
  state.openDoc = null;
  location.hash = id;
  renderLoan();
  renderSidebar();
  schedulePoll();
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  const l = state.loan;
  if (!l) return;
  if (l.processing || l.advice_status === "generating") {
    state.pollTimer = setTimeout(async () => {
      try {
        const fresh = await api(`/api/loans/${l.id}`);
        if (state.loan && state.loan.id === fresh.id) {
          state.loan = fresh;
          renderLoan();
          if (!fresh.processing && fresh.advice_status !== "generating") loadLoans();
        }
      } catch (e) { /* keep polling */ }
      schedulePoll();
    }, 1500);
  }
}

function renderLoan() {
  const l = state.loan;
  $("#emptyState").hidden = !!l;
  $("#loanView").hidden = !l;
  if (!l) return;
  const ev = l.evaluation;

  if (document.activeElement !== $("#loanName")) $("#loanName").value = l.name;
  const meta = [];
  if (ev.borrower) meta.push(`<span>Borrower <b>${esc(ev.borrower)}</b></span>`);
  if (ev.property) meta.push(`<span>Property <b>${esc(ev.property)}</b></span>`);
  if (ev.metrics.loan_amount) meta.push(`<span>Loan <b>${money(ev.metrics.loan_amount)}</b></span>`);
  $("#loanMeta").innerHTML = meta.join("") || `<span>Upload documents to identify the borrower and property.</span>`;
  $("#methodSel").value = l.settings.underwriting_method;
  if (document.activeElement !== $("#noteDate")) $("#noteDate").value = l.settings.note_date;

  renderVerdict(l);
  renderRules(ev);
  renderDocs(l);
  renderMemo(l);
  renderChat(l);
  $("#cntRules").textContent = ev.results.length || "";
  $("#cntDocs").textContent = l.documents.length || "";
  $("#adviceDot").hidden = l.advice_status !== "stale";
}

function renderVerdict(l) {
  const ev = l.evaluation, d = ev.decision, c = ev.counts;
  const docsPending = l.documents.filter((x) => x.status === "queued" || x.status === "processing").length;
  $("#stamp").className = `stamp ${d.code}`;
  $("#stamp").innerHTML = `
    <div class="stamp-mark">${esc(d.label)}</div>
    <div class="stamp-detail">${esc(d.detail)}</div>
    ${ev.results.length ? `<div class="stamp-counts">
      <span><i style="background:var(--fail)"></i>${c.fail} failed</span>
      <span><i style="background:var(--warn)"></i>${c.warn} to review</span>
      <span><i style="background:var(--missing)"></i>${c.missing} missing</span>
      <span><i style="background:var(--pass)"></i>${c.pass} passed</span></div>` : ""}
    ${docsPending ? `<div class="processing-note"><span class="spinner"></span>Reading ${docsPending} document${docsPending > 1 ? "s" : ""}; results will update.</div>` : ""}`;

  const m = ev.metrics, method = ev.settings.underwriting_method;
  const ltvRule = ev.results.find((r) => r.id === "COL-LTV");
  const resRule = ev.results.find((r) => r.id === "AST-RESERVES");
  const dtiLimit = method === "du" ? 50 : 45;
  const k = [
    { t: "Qualifying income", v: m.qualifying_income != null ? money(m.qualifying_income) + "<small>/mo</small>" : "—", lim: "Documented base pay" },
    { t: "Total DTI", v: pct(m.back_dti), lim: (m.front_dti != null ? `Housing ${pct(m.front_dti)}; ` : "") + (method === "du" ? "DU max 50%" : "manual max 36/45%"),
      cls: m.back_dti > dtiLimit ? "bad" : (m.back_dti > (method === "du" ? 45 : 36) ? "caution" : "") },
    { t: "LTV", v: pct(m.ltv), lim: ltvRule ? `Max ${esc(ltvRule.threshold.replace("≤ ", ""))}` : "Loan / value", cls: ltvRule && ltvRule.status === "fail" ? "bad" : "" },
    { t: "Credit score", v: m.representative_score ?? "—", lim: method === "du" ? "Representative; no DU minimum" : "Manual min 620 fixed" },
    { t: "Reserves", v: m.reserves_months != null ? m.reserves_months.toFixed(1) + "<small>mo</small>" : "—", lim: resRule ? `Required ${esc(resRule.threshold.replace("≥ ", ""))}` : "Months of PITIA",
      cls: resRule && resRule.status === "fail" ? "bad" : "" },
    { t: "Cash to close", v: money(m.cash_to_close), lim: m.verified_assets != null ? `${money(m.verified_assets)} verified` : "Down payment + costs",
      cls: m.verified_assets != null && m.cash_to_close > m.verified_assets + (m.gift_funds || 0) ? "bad" : "" },
  ];
  $("#kpis").innerHTML = k.map((x) => `<div class="kpi ${x.cls || ""}"><dt>${x.t}</dt><dd>${x.v}</dd><div class="lim">${x.lim}</div></div>`).join("");
}

function ruleRow(r) {
  const cites = (r.citation_links || []).map((c) => `<a href="${esc(c.url)}" target="_blank" rel="noopener" title="${esc(c.title)}">${esc(c.id)} ${esc(c.title)}</a>`).join("");
  return `<div class="rule ${r.status}">
    <div><span class="st ${r.status}">${STATUS_LABEL[r.status]}</span></div>
    <div>
      <div class="rule-name">${esc(r.name)}</div>
      <div class="rule-msg">${esc(r.message)}</div>
      <div class="rule-cites">${cites}${r.docs && r.docs.length ? `<span class="rule-docs">${esc(r.docs.join(", "))}</span>` : ""}</div>
    </div>
    <div class="rule-val">${r.value ? `<div class="v">${esc(r.value)}</div>` : ""}${r.threshold ? `<div class="t">${esc(r.threshold)}</div>` : ""}</div>
  </div>`;
}

function renderRules(ev) {
  $("#legend").innerHTML = Object.entries(STATUS_LABEL).map(([k, v]) => `<span><span class="st ${k}">${v}</span></span>`).join("");
  $$("#ruleFilter button").forEach((b) => b.classList.toggle("on", b.dataset.f === state.filter));
  if (!ev.results.length) {
    $("#rulesList").innerHTML = `<div class="none">No rule results yet. Add documents on the Documents tab; rules run as soon as each one is read.</div>`;
    return;
  }
  const shown = state.filter === "issues" ? ev.results.filter((r) => ["fail", "warn", "missing"].includes(r.status)) : ev.results;
  if (!shown.length) {
    $("#rulesList").innerHTML = `<div class="none">Nothing needs attention. All ${ev.results.length} rules passed or are informational. Switch to All rules to see each check.</div>`;
    return;
  }
  const cats = [...new Set(shown.map((r) => r.category))];
  $("#rulesList").innerHTML = cats.map((c) => {
    const rows = shown.filter((r) => r.category === c);
    const all = ev.results.filter((r) => r.category === c);
    const passed = all.filter((r) => r.status === "pass").length;
    return `<div class="cat"><h3>${esc(c)}<span class="cat-sum">${passed} of ${all.length} passed</span></h3>
      <div class="rules">${rows.map(ruleRow).join("")}</div></div>`;
  }).join("");
}

function renderDocs(l) {
  const types = state.status.doc_types;
  $("#docsBody").innerHTML = l.documents.length ? l.documents.map((d) => {
    const st = d.status === "processed" ? (d.doc_type === "other" ? `<span class="st info">Not used</span>` : `<span class="st pass">Read</span>`)
      : d.status === "error" ? `<span class="st fail" title="${esc(d.error)}">Error</span>`
      : `<span class="processing-note"><span class="spinner"></span>${d.status === "queued" ? "Queued" : "Reading"}</span>`;
    const conf = d.confidence != null ? `<span class="conf-bar"><i style="width:${Math.round(d.confidence * 100)}%"></i></span>${Math.round(d.confidence * 100)}%` : "";
    return `<tr class="${d.status === "processed" || d.status === "error" ? "clickable" : ""}" data-doc="${d.id}">
      <td><span class="fname">${esc(d.filename)}</span>${d.edited ? `<span class="edited">corrected</span>` : ""}</td>
      <td>${d.doc_type ? esc(types[d.doc_type] || d.doc_type) : "<span class='muted'>—</span>"}</td>
      <td class="num">${conf}</td><td>${st}</td>
      <td class="num">${d.status === "processed" || d.status === "error" ? `<button class="btn ghost" data-open="${d.id}">Review</button>` : ""}</td></tr>`;
  }).join("") : `<tr><td colspan="5" class="muted" style="padding:16px">No documents yet.</td></tr>`;
}

/* ------------------------------------------------------------ memo */
function cites(arr) {
  return (arr || []).length ? ` <span class="cite">[${arr.map(esc).join(", ")}]</span>` : "";
}
function renderMemo(l) {
  const a = l.advice, s = l.advice_status;
  const st = $("#adviceStatus");
  $("#adviceBtn").disabled = s === "generating" || l.processing;
  $("#adviceBtn").textContent = a ? "Regenerate memo" : "Write memo";
  st.innerHTML = s === "generating" ? `<span class="spinner"></span>Writing the advisor memo`
    : s === "stale" ? `The file changed since this memo was written. Regenerate to include the latest data.`
    : s === "error" ? `<span class="st fail">Error</span> ${esc(l.advice_error)}`
    : l.processing ? `The memo is written after all documents are read.`
    : a ? `Written ${new Date(a.generated_at).toLocaleString()}` : "";
  if (!a) {
    $("#memo").innerHTML = `<p class="muted" style="font-family:var(--sans)">No memo yet. It is written automatically once all documents are read.</p>`;
    return;
  }
  const engine = (a.engine || "").startsWith("claude") ? `Drafted by ${esc(a.engine.replace("claude:", "Claude "))}` : "Template memo (offline demo mode)";
  let h = `<div class="memo-head">Pre-underwriting memo. ${engine}.</div><h2>${esc(a.headline)}</h2><p>${esc(a.summary)}</p>`;
  if (a.blockers?.length) {
    h += `<h4>Eligibility blockers</h4>` + a.blockers.map((b) => `<div class="blocker"><b>${esc(b.issue)}</b>${cites(b.citations)}<div>${esc(b.detail)}</div>${b.fix ? `<div class="fix">Possible fix: ${esc(b.fix)}</div>` : ""}</div>`).join("");
  }
  if (a.conditions?.length) {
    const tm = { prior_to_approval: "Prior to approval", prior_to_closing: "Prior to closing", prior_to_funding: "Prior to funding" };
    h += `<h4>Suggested conditions</h4><table><thead><tr><th>Condition</th><th>Why</th><th>Timing</th></tr></thead><tbody>` +
      a.conditions.map((c) => `<tr><td><b>${esc(c.condition)}</b>${cites(c.citations)}</td><td>${esc(c.reason)}</td><td class="timing">${esc(tm[c.timing] || "")}</td></tr>`).join("") + `</tbody></table>`;
  }
  const list = (title, arr) => (arr?.length ? `<h4>${title}</h4><ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
  h += list("Compensating factors", a.compensating_factors);
  h += list("Questions for the underwriter", a.questions_for_underwriter);
  h += list("Data quality notes", a.data_quality_notes);
  h += `<div class="disclaimer">Advisory only. Rule outcomes come from the deterministic engine; DU findings and the underwriter's judgment make the decision.</div>`;
  $("#memo").innerHTML = h;
}

/* ------------------------------------------------------------ chat */
const SUGGESTIONS = [
  "Which conditions should I clear first?",
  "What would it take to get DTI under the limit?",
  "Explain how qualifying income was calculated.",
  "Does this file meet the reserve requirements?",
];
function renderChat(l) {
  const chat = l.chat || [];
  $("#chat").innerHTML = chat.length ? chat.map((m) => `<div class="msg ${m.role}">${esc(m.content)}</div>`).join("")
    : `<p class="muted">Ask about this loan file or any Fannie Mae guideline. Answers use the extracted data, rule results and the guideline summaries.</p>`;
  $("#suggest").innerHTML = SUGGESTIONS.map((q) => `<button type="button">${esc(q)}</button>`).join("");
}
async function ask(q) {
  if (!q.trim() || !state.loan) return;
  const l = state.loan;
  l.chat = [...(l.chat || []), { role: "user", content: q }, { role: "assistant", content: "Thinking…" }];
  renderChat(l);
  $("#askInput").value = "";
  try {
    const r = await api(`/api/loans/${l.id}/ask`, { method: "POST", body: JSON.stringify({ question: q }) });
    l.chat = r.chat;
  } catch (e) {
    l.chat[l.chat.length - 1].content = "Could not get an answer: " + e.message;
  }
  renderChat(l);
  $("#chat").lastElementChild?.scrollIntoView({ block: "nearest" });
}

/* ------------------------------------------------------------ guidelines */
async function renderGuidelines() {
  if (!state.guidelines) state.guidelines = await api("/api/guidelines");
  const g = state.guidelines;
  $("#guideList").innerHTML = Object.entries(g.sections).map(([id, s]) => `
    <div class="gsec"><div class="gh"><span class="gid">${esc(id)}</span><span class="gt">${esc(s.title)}</span>
    <span class="gr">Revised ${esc(s.revised)}. <a href="${esc(s.url)}" target="_blank" rel="noopener">Open in Selling Guide</a></span></div>
    <p>${esc(s.summary)}</p></div>`).join("");
}

/* ------------------------------------------------------------ document drawer */
const TYPE_OPTIONS = () => Object.entries(state.status.doc_types);
function openDrawer(docId) {
  const d = state.loan.documents.find((x) => x.id === docId);
  if (!d) return;
  state.openDoc = d;
  $("#dTitle").textContent = d.filename;
  $("#dSub").textContent = d.status === "error" ? `Error: ${d.error}` : `${state.status.doc_types[d.doc_type] || "Unclassified"}, read by ${d.engine === "offline-demo" ? "offline parser" : (d.engine || "").replace("claude:", "Claude ")}`;
  $("#dPdf").src = `/api/loans/${state.loan.id}/documents/${d.id}/file`;
  $("#dType").innerHTML = TYPE_OPTIONS().map(([k, v]) => `<option value="${k}" ${k === d.doc_type ? "selected" : ""}>${esc(v)}</option>`).join("");
  $("#dRationale").textContent = d.rationale ? `Why: ${d.rationale}` : "";
  renderFields(d);
  $("#drawer").hidden = $("#scrim").hidden = false;
  $("#dClose").focus();
}
function closeDrawer() {
  $("#drawer").hidden = $("#scrim").hidden = true;
  $("#dPdf").src = "about:blank";
  state.openDoc = null;
}
const pretty = (k) => k.replace(/_/g, " ").replace(/\b(ssn|ytd|ein|hoa|w2|gla)\b/gi, (m) => m.toUpperCase()).replace(/^./, (c) => c.toUpperCase());
function renderFields(d) {
  const f = d.fields || {};
  const scalars = Object.entries(f).filter(([, v]) => !Array.isArray(v));
  const lists = Object.entries(f).filter(([, v]) => Array.isArray(v));
  const editable = d.doc_type && d.doc_type !== "other";
  let h = scalars.map(([k, v]) => {
    const kind = typeof v === "boolean" ? "bool" : typeof v === "number" ? "num" : "text";
    const input = kind === "bool" || (v === null && /^(declares_|first_time|self_employed|us_citizen|to_be)/.test(k))
      ? `<select name="${k}" data-kind="bool" ${editable ? "" : "disabled"}><option value="">—</option><option value="true" ${v === true ? "selected" : ""}>Yes</option><option value="false" ${v === false ? "selected" : ""}>No</option></select>`
      : `<input name="${k}" data-kind="${kind}" value="${esc(v ?? "")}" title="${esc(v ?? "")}" placeholder="—" ${editable ? "" : "disabled"}>`;
    return `<div class="frow ${v == null ? "empty" : ""}"><label for="">${esc(pretty(k))}</label>${input}</div>`;
  }).join("");
  h += lists.map(([k, arr]) => {
    if (!arr.length) return `<div class="fgroup"><h5>${esc(pretty(k))}</h5><div class="muted" style="font-size:12px">None found</div></div>`;
    const cols = Object.keys(arr[0]);
    return `<div class="fgroup"><h5>${esc(pretty(k))} (${arr.length})</h5><table><thead><tr>${cols.map((c) => `<th>${esc(pretty(c))}</th>`).join("")}</tr></thead>
      <tbody>${arr.map((row) => `<tr>${cols.map((c) => `<td>${esc(typeof row[c] === "boolean" ? (row[c] ? "Yes" : "No") : row[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }).join("");
  $("#dForm").innerHTML = h || `<p class="muted">No data extracted.</p>`;
  $("#dSave").hidden = !editable;
}
async function saveFields() {
  const d = state.openDoc;
  const changes = {};
  $$("#dForm [name]").forEach((el) => {
    const k = el.name, old = d.fields[k];
    let v = el.value.trim();
    if (el.dataset.kind === "bool") v = v === "" ? null : v === "true";
    else if (v === "") v = null;
    else if (el.dataset.kind === "num" || (old === null && /^-?[\d,]+(\.\d+)?$/.test(v) && !/(date|last4|ein|zip)/.test(k))) v = Number(v.replace(/,/g, ""));
    if (JSON.stringify(v) !== JSON.stringify(old)) changes[k] = v;
  });
  if (!Object.keys(changes).length) return toast("No changes to save.");
  try {
    state.loan = await api(`/api/loans/${state.loan.id}/documents/${d.id}`, { method: "PATCH", body: JSON.stringify({ fields: changes }) });
    toast(`Saved ${Object.keys(changes).length} correction${Object.keys(changes).length > 1 ? "s" : ""}. Rules re-ran.`);
    closeDrawer();
    renderLoan();
  } catch (e) { toast(e.message); }
}

/* ------------------------------------------------------------ upload */
async function uploadFiles(files) {
  if (!state.loan || !files.length) return;
  const fd = new FormData();
  [...files].forEach((f) => fd.append("files", f));
  $("#uploadMsg").textContent = `Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`;
  try {
    const r = await api(`/api/loans/${state.loan.id}/documents`, { method: "POST", body: fd });
    $("#uploadMsg").textContent = `${r.accepted.length} uploaded and queued for reading.` + (r.rejected.length ? ` Skipped: ${r.rejected.map((x) => `${x.filename} (${x.reason})`).join(", ")}.` : "");
    await openLoan(state.loan.id);
  } catch (e) { $("#uploadMsg").textContent = e.message; }
}

/* ------------------------------------------------------------ events */
function setTab(t) {
  state.tab = t;
  $$(".tab").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === t));
  $$(".panel").forEach((p) => (p.hidden = p.dataset.panel !== t));
  if (t === "guide") renderGuidelines();
}
async function newLoan() {
  const loan = await api("/api/loans", { method: "POST", body: JSON.stringify({ name: "New loan file" }) });
  await loadLoans();
  await openLoan(loan.id);
  setTab("docs");
  $("#loanName").select();
}
async function patchLoan(body) {
  state.loan = await api(`/api/loans/${state.loan.id}`, { method: "PATCH", body: JSON.stringify(body) });
  renderLoan(); loadLoans();
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest("button, tr.clickable");
  if (!t) return;
  if (t.matches(".tab")) return setTab(t.dataset.tab);
  if (t.matches(".loan-item")) return openLoan(t.dataset.id);
  if (t.dataset.sample) {
    t.disabled = true;
    try { const loan = await api(`/api/samples/${t.dataset.sample}`, { method: "POST" }); await loadLoans(); await openLoan(loan.id); setTab("rules"); }
    finally { t.disabled = false; }
    return;
  }
  if (t.closest("#ruleFilter")) { state.filter = t.dataset.f; return renderRules(state.loan.evaluation); }
  if (t.closest("#suggest")) return ask(t.textContent);
  if (t.dataset.open || t.matches("tr.clickable")) return openDrawer(t.dataset.open || t.dataset.doc);
});
$("#newLoanBtn").onclick = newLoan;
$("#emptyNew").onclick = newLoan;
$("#loanName").addEventListener("change", (e) => patchLoan({ name: e.target.value }));
$("#methodSel").addEventListener("change", (e) => patchLoan({ settings: { underwriting_method: e.target.value } }));
$("#noteDate").addEventListener("change", (e) => e.target.value && patchLoan({ settings: { note_date: e.target.value } }));
$("#deleteLoan").onclick = async () => {
  if (!confirm(`Delete "${state.loan.name}" and its documents?`)) return;
  await api(`/api/loans/${state.loan.id}`, { method: "DELETE" });
  state.loan = null; location.hash = ""; renderLoan(); loadLoans();
};
$("#adviceBtn").onclick = async () => {
  const l = state.loan;
  l.advice_status = "generating"; renderMemo(l);
  try { state.loan = await api(`/api/loans/${l.id}/advice`, { method: "POST" }); } catch (e) { toast(e.message); }
  renderLoan();
};
$("#askForm").addEventListener("submit", (e) => { e.preventDefault(); ask($("#askInput").value); });

const drop = $("#drop");
$("#fileInput").addEventListener("change", (e) => { uploadFiles(e.target.files); e.target.value = ""; });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));

$("#dClose").onclick = closeDrawer;
$("#scrim").onclick = closeDrawer;
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#drawer").hidden) closeDrawer(); });
$("#dSave").onclick = saveFields;
$("#dType").addEventListener("change", async (e) => {
  const d = state.openDoc;
  await api(`/api/loans/${state.loan.id}/documents/${d.id}`, { method: "PATCH", body: JSON.stringify({ doc_type: e.target.value }) });
  toast("Re-reading the document as " + state.status.doc_types[e.target.value] + ".");
  closeDrawer();
  await openLoan(state.loan.id);
});
$("#dDelete").onclick = async () => {
  const d = state.openDoc;
  if (!confirm(`Remove ${d.filename} from this loan file?`)) return;
  state.loan = await api(`/api/loans/${state.loan.id}/documents/${d.id}`, { method: "DELETE" });
  closeDrawer(); renderLoan(); loadLoans();
};

(async function init() {
  await loadStatus();
  await loadLoans();
  const id = location.hash.slice(1);
  if (id && state.loans.some((l) => l.id === id)) await openLoan(id);
  else if (state.loans.length) await openLoan(state.loans[0].id);
  else renderLoan();
})();
