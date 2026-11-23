"use strict";

let current = null;
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function put(id, value) {
  const node = $(id);
  if (node) node.textContent = value === undefined || value === null ? "" : String(value);
}

function short(id) {
  const s = String(id || "");
  return s.length > 16 ? s.slice(0, 16) + "…" : s;
}

let toastTimer = null;
function toast(text) {
  const box = $("feedback");
  if (!box) return;
  box.textContent = text;
  box.hidden = false;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 6000);
}

const VIEW_LABELS = {
  overview: "研究总览",
 forecast: "预测对照",  evidence: "证据台账",
  claims: "论点卡片",
  details: "运行详情",
};

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => {
    if (v.id !== "view-" + name) v.hidden = true;
  });
  const target = $("view-" + name);
  if (target) target.hidden = false;
  document.querySelectorAll(".nav-item").forEach((item) => {
    const on = item.dataset.view === name;
    item.classList.toggle("is-active", on);
    if (on) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  put("breadcrumb", "工作空间 / " + (VIEW_LABELS[name] || name));
}

function valid(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("invalid payload");
  if (!data.manifest || typeof data.manifest !== "object" || Array.isArray(data.manifest)) throw new Error("invalid manifest");
  if (typeof data.report !== "string") throw new Error("invalid report");
  if (typeof data.run_id !== "string") throw new Error("invalid run id");
  for (const key of ["evidence", "claims"]) {
    if (!Array.isArray(data[key])) throw new Error("invalid " + key);
    data[key].forEach((row) => {
      if (!row || typeof row !== "object" || Array.isArray(row)) throw new Error("invalid " + key + " row");
    });
  }
  data.evidence.forEach((e) => { if (typeof e.evidence_id !== "string") throw new Error("invalid evidence id"); });
  data.claims.forEach((c) => { if (typeof c.claim_id !== "string") throw new Error("invalid claim id"); });
}

function safeUrl(uri) {
  try {
    const u = new URL(String(uri || ""));
    return u.protocol === "http:" || u.protocol === "https:" ? u : null;
  } catch {
    return null;
  }
}

function evidenceNode(e, compact) {
  const item = el("article", "evidence-item");
  const head = el("div", "evidence-heading");
  const url = safeUrl(e.source_uri);
  if (url) {
    const a = el("a", "", url.hostname);
    a.href = url.href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    head.appendChild(a);
  } else {
    head.appendChild(el("span", "", "来源未知"));
  }
  const status = e.eligibility === "eligible"
    ? ["合格证据", "badge good"]
    : e.eligibility === "excluded"
      ? ["已排除", "badge warn"]
      : ["未知", "badge"];
  head.appendChild(el("span", status[1], status[0]));
  item.appendChild(head);
  const body = el("p", "evidence-body");
  let text = String(e.excerpt || e.content || "");
  if (compact && text.length > 240) text = text.slice(0, 240) + "…";
  body.textContent = text;
  item.appendChild(body);
  const kind = e.kind === "market" ? "行情" : e.kind === "news" ? "新闻" : "未知";
  const meta = el("p", "muted");
  meta.textContent = kind + " · " + (e.qualification_time || e.available_at || e.published_at || "未知") + " · " + short(e.evidence_id);
  item.appendChild(meta);
  if (e.exclusion_reason) item.appendChild(el("p", "badge warn", e.exclusion_reason));
  if (!compact) {
    const det = el("details");
    det.appendChild(el("summary", "", "原文"));
    const pre = el("pre", "mono", e.content || "未提供");
    pre.setAttribute("data-evidence-id", String(e.evidence_id));
    pre.title = String(e.evidence_id);
    det.appendChild(pre);
    item.appendChild(det);
  }
  return item;
}

function renderEvidence() {
  const list = $("evidence-list");
  if (!list) return;
  const q = String(($("evidence-search") || {}).value || "").toLowerCase().trim();
  const filter = (($("evidence-filter") || {}).value) || "all";
  const rows = ((current && current.evidence) || []).filter((e) => {
    if (filter !== "all" && e.eligibility !== filter) return false;
    if (!q) return true;
    return [e.evidence_id, e.source_uri, e.excerpt, e.content]
      .some((v) => String(v || "").toLowerCase().includes(q));
  });
  list.replaceChildren();
  if (!rows.length) {
    list.appendChild(el("p", "empty", "没有匹配的证据。"));
  } else {
    rows.forEach((e) => list.appendChild(evidenceNode(e, false)));
  }
  const preview = $("evidence-preview");
  if (preview) {
    preview.replaceChildren();
    ((current && current.evidence) || []).slice(0, 2).forEach((e) => preview.appendChild(evidenceNode(e, true)));
  }
}

const KIND_LABELS = { fact: "事实", inference: "推断" };

function referenceButton(id) {
  const btn = el("button", "reference-btn", "证据" + short(id));
  btn.type = "button";
  btn.addEventListener("click", () => {
    showView("evidence");
    const search = $("evidence-search");
    const filter = $("evidence-filter");
    if (search) search.value = id;
    if (filter) filter.value = "all";
    renderEvidence();
  });
  return btn;
}

function renderClaims() {
  const list = $("claims-list");
  if (!list) return;
  const claims = (current && current.claims) || [];
  list.replaceChildren();
  if (!claims.length) {
    list.appendChild(el("p", "empty", "没有主张。"));
    return;
  }
  claims.forEach((c) => {
    const card = el("article", "claim-card");
    const kinds = [];
    if (KIND_LABELS[c.kind]) kinds.push(el("span", "badge", KIND_LABELS[c.kind]));
    else kinds.push(el("span", "badge", "未知"));
    kinds.push(el("span", "mono", short(c.claim_id)));
    const head = el("div", "claim-head");
    kinds.forEach((k) => head.appendChild(k));
    card.appendChild(head);
    card.appendChild(el("p", "text", c.text || ""));
    const refs = el("div", "claim-refs");
    const ids = Array.isArray(c.evidence_ids) ? c.evidence_ids : [];
    ids.forEach((id) => {
      const known = ((current && current.evidence) || []).some((e) => e.evidence_id === id);
      if (known) refs.appendChild(referenceButton(id));
      else refs.appendChild(el("span", "muted", short(id)));
    });
    card.appendChild(refs);
    if (c.uncertainty) card.appendChild(el("p", "muted", c.uncertainty));
    list.appendChild(card);
  });
}


const STATES = {
  completed: "已完成", failed: "失败", stopped: "已停止",
  pending: "待审阅", passed: "通过", rejected: "已退回",
  approved: "已批准", draft: "草稿", released: "已发布",
};

function state(v) {
  return STATES[v] || "未知";
}

function renderArtifact(a) {
  valid(a);
  current = a;

  put("metric-execution", state(a.execution_status));
  put("metric-evidence", a.evidence.length);
  put("metric-claims", a.claims.length);
  const g = a.gate_results;
  put("metric-gate", g && g.passed === true ? "通过" : g && g.passed === false ? "未通过" : "未知");

  const manifest = a.manifest || {};
  put("ticker", manifest.ticker || "\u2014");
  const ratingMap = { Buy: "买入", Overweight: "增持", Hold: "观望", Underweight: "减持", Sell: "卖出" };
  put("rating", ratingMap[a.rating] || "\u2014");
  put("as-of", manifest.as_of_utc || "\u2014");
  put("run-id", manifest.run_id || "\u2014");

  let reportText = typeof a.report === "string" ? a.report : "";
  if (Array.isArray(a.claims)) {
    a.claims.forEach((c, i) => {
      if (c && c.claim_id) {
        reportText = reportText.split("[" + c.claim_id + "]").join("[" + (i + 1) + "]");
      }
    });
  }
  put("report-content", reportText || "\u2014");

  put("publication", state(a.publication_status) + " \u00b7 审阅：" + state(a.review_status));

  const wf = $("workflow");
  if (wf) {
    wf.replaceChildren();
    const ev = Array.isArray(a.evidence) ? a.evidence : [];
    const cl = Array.isArray(a.claims) ? a.claims : [];
    const steps = [
      ["证据整理", "合格" + ev.filter((e) => e.eligibility === "eligible").length + "条 / 共" + ev.length + "条", a.execution_status === "completed"],
      ["论点构建", "已记录" + cl.length + "条论点", a.execution_status === "completed"],
      ["输出检查", state(a.validation_status), a.validation_status === "passed"],
      ["人工审阅", state(a.review_status), a.review_status === "approved"],
    ];
    steps.forEach((s, i) => {
      const step = el("div", "step" + (s[2] ? " good" : ""));
      step.appendChild(el("div", "step-num", String(i + 1)));
      const copy = el("div", "step-copy");
      copy.appendChild(el("div", "step-title", s[0]));
      copy.appendChild(el("div", "step-sub", s[1]));
      step.appendChild(copy);
      wf.appendChild(step);
    });
  }

  const synthetic = a.measurement?.source_mode === "offline_replay";
  const usage = $("usage-details");
  if (usage) {
    usage.textContent = synthetic
      ? "本次为离线回放，未发起模型请求。"
      : "未提供完整模型用量记录。";
  }

  const ann = document.querySelector(".announce");
  if (ann) {
    ann.textContent = synthetic ? "研究报告为合成演示；在线行情独立显示，不用于本次报告结论。" : "导入报告记录；在线行情独立显示。";
  }
  const pill = document.querySelector(".pill");
  if (pill) pill.textContent = synthetic ? "报告：离线回放" : "本地报告";
  const callout = document.querySelector(".callout");
  if (callout) {
    callout.replaceChildren();
    callout.appendChild(el("strong", "", synthetic ? "本地离线回放" : "本地记录导入"));
    callout.appendChild(el("span", "", synthetic ? " 合成示例，不会调用模型" : " 以原始运行记录为准"));
  }

  const dl = $("details-list");
  if (dl) {
    dl.replaceChildren();
    const rows = [
      ["运行编号", manifest.run_id],
      ["修订", a.revision],
      ["模型", manifest.model_id],
      ["分析截点", manifest.as_of_utc],
      ["运行状态", a.execution_status],
      ["检查状态", a.validation_status],
      ["审阅状态", a.review_status],
      ["文稿状态", a.publication_status],
      ["报告哈希", a.artifact_hash],
    ];
    rows.forEach((r) => {
      const row = el("div", "detail-row");
      row.appendChild(el("dt", "", String(r[0])));
      row.appendChild(el("dd", "mono", String(r[1] || "\u2014")));
      dl.appendChild(row);
    });
  }

  const lim = $("limitations-list");
  if (lim) {
    lim.replaceChildren();
    const limits = Array.isArray(a.limitations) ? a.limitations : [];
    limits.forEach((t) => { if (typeof t === "string") lim.appendChild(el("li", "", t)); });
    const viol = g && Array.isArray(g.violations) ? g.violations : [];
    viol.forEach((t) => { lim.appendChild(el("li", "", typeof t === "string" ? t : String(t))); });
    lim.appendChild(el("li", "note", "检查结果来自报告记录，本页面不重新执行门禁。"));
  }

  renderEvidence();
  renderClaims();
}


function wire() {
  const imports = $("import-btn");
  const fileInput = $("file-input");
  const demoBtn = $("demo-btn");
  const downloadBtn = $("download-btn");
  const filter = $("evidence-filter");
  const search = $("evidence-search");

  function loadDemo() {
    return fetch("/demo.json")
      .then((r) => {
        if (!r.ok) throw new Error("demo fetch failed");
        return r.json();
      })
      .then((d) => {
        valid(d);
        renderArtifact(d);
        showView("overview");
      })
      .catch(() => { toast("无法加载演示数据。"); });
  }

  if (demoBtn) demoBtn.addEventListener("click", () => { loadDemo(); });

  document.querySelectorAll(".nav-item").forEach((b) => {
    b.addEventListener("click", () => {
      const name = b.dataset.view;
      if (name) showView(name);
    });
  });
  document.querySelectorAll("[data-view]").forEach((b) => {
    if (b.classList.contains("nav-item")) return;
    b.addEventListener("click", () => {
      const name = b.dataset.view;
      if (name) showView(name);
    });
  });

  if (imports && fileInput) {
    imports.addEventListener("click", () => { fileInput.click(); });
  }

  if (fileInput) {
    fileInput.addEventListener("change", async () => {
      try {
        if (typeof window.importWorkbenchFiles === "function") {
          await window.importWorkbenchFiles(fileInput.files);
        }
      } finally {
        fileInput.value = "";
      }
    });
  }

  if (filter) {
    filter.addEventListener("input", renderEvidence);
    filter.addEventListener("change", renderEvidence);
  }
  if (search) {
    search.addEventListener("input", renderEvidence);
    search.addEventListener("change", renderEvidence);
  }

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (!current) return;
      const blob = new Blob([JSON.stringify(current, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const ticker = (current.manifest && current.manifest.ticker) || "report";
      anchor.href = url;
      anchor.download = "evidenceguard-" + String(ticker).replace(/[^A-Za-z0-9._-]/g, "_") + ".json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    });
  }

  showView("overview");
  loadDemo();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}
