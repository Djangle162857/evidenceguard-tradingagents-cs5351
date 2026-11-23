(function () {
  "use strict";

  var TICKERS = ["AAPL", "MSFT", "NVDA"];
  var SECTION_KEYS = ["利好因素", "风险因素", "关键分歧", "未来一周观察", "数据缺口"];
  var MISSING = "信息不足（报告未提供）";

  var manual = { AAPL: undefined, MSFT: undefined, NVDA: undefined };

  function store() { return window.EGWorkbench.store; }

  function allArtifacts() {
    var out = [];
    var s = store();
    if (!s) return out;
    var rows = s.items();
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] && rows[i].artifact) out.push(rows[i].artifact);
    }
    return out;
  }

  function tickerOf(a) {
    return a && a.manifest ? a.manifest.ticker : undefined;
  }

  function selectedReports() {
    var s = store();
    var out = [];
    if (!s) return out;
    for (var i = 0; i < TICKERS.length; i++) {
      var t = TICKERS[i];
      var m = manual[t];
      var key = m === undefined ? s.latest(t) : m;
      if (key === undefined || key === null || key === "") continue;
      var a = s.get(key);
      if (a) out.push(a);
    }
    return out;
  }

  function fmt(v) {
    return v === undefined || v === null || v === "" ? "缺失" : String(v);
  }

  function forTicker(t) {
    var rows = allArtifacts();
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      if (tickerOf(rows[i]) === t) out.push(rows[i]);
    }
    return out;
  }

  function getBrief(a) {
    try {
      if (window.EGReports && typeof window.EGReports.brief === "function") {
        return window.EGReports.brief(a.report);
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  function sectionText(brief, key) {
    if (!brief || typeof brief !== "object") return MISSING;
    var v = brief.sections ? brief.sections[key] : undefined;
    if (v === undefined || v === null || String(v).trim() === "") return MISSING;
    return String(v);
  }

  function jsonBlock(obj) {
    try {
      return "```json\n" + JSON.stringify(obj, null, 2) + "\n```";
    } catch (e) {
      return "```json\nnull\n```";
    }
  }

  function exportMarkdown(artifacts) {
    var list = artifacts || selectedReports();
    var lines = ["# 本地研究日报", ""];
    if (!list.length) lines.push("（无已选择报告）", "");
    for (var i = 0; i < list.length; i++) {
      var a = list[i] || {};
      var man = a.manifest || {};
      var brief = getBrief(a);
      lines.push("## " + fmt(man.ticker) + " / " + fmt(a.run_id), "");
      lines.push("- manifest.ticker: " + fmt(man.ticker));
      lines.push("- run_id: " + fmt(a.run_id));
      lines.push("- revision: " + fmt(a.revision));
      lines.push("- artifact_hash: " + fmt(a.artifact_hash !== undefined ? a.artifact_hash : a.hash));
      lines.push("- artifact_hash(完整): " + fmt(a.artifact_hash));
      lines.push("- manifest.as_of_utc: " + fmt(man.as_of_utc));
      lines.push("- execution_status: " + fmt(a.execution_status));
      lines.push("- validation_status: " + fmt(a.validation_status));
      lines.push("- review_status: " + fmt(a.review_status));
      lines.push("- publication_status: " + fmt(a.publication_status));
      var sm = a.measurement && a.measurement.source_mode;
      lines.push("- source_mode: " + fmt(sm) + (sm === "offline_replay" ? "（合成演示）" : ""));
      lines.push("- 简报完整性: " + (brief && brief.complete ? "完整" : "简报不完整"));
      lines.push("");
      lines.push("### 简报摘要", "");
      lines.push(brief && brief.summary && String(brief.summary).length ? String(brief.summary) : MISSING, "");
      for (var k = 0; k < SECTION_KEYS.length; k++) {
        var key = SECTION_KEYS[k];
        lines.push("**" + key + "**", "", sectionText(brief, key), "");
      }
      lines.push("### 完整原始报告 (FULL ORIGINAL)", "");
      lines.push(a.report === undefined || a.report === null ? MISSING : String(a.report), "");
      lines.push("### 声明 (claims)", "");
      lines.push(jsonBlock(a.claims || []), "");
      lines.push("### 证据 (evidence)", "");
      lines.push(jsonBlock(a.evidence || []), "");
      lines.push("### 静态评审清单", "");
      lines.push("- [ ] 证据已核验 (evidence)");
      lines.push("- [ ] 数据缺口已知");
      lines.push("- [ ] 审批人已批准当前哈希");
      lines.push("");
    }
    return lines.join("\n") + "\n";
  }

  function exportMarkdown_(artifacts) { return exportMarkdown(artifacts); }
  exportMarkdown_ = exportMarkdown_;

  function buildControl(t) {
    var wrap = document.createElement("div");
    var label = document.createElement("label");
    label.setAttribute("for", "daily-" + t);
    label.textContent = t;
    var sel = document.createElement("select");
    sel.id = "daily-" + t;
    var opts = forTicker(t);
    var none = document.createElement("option");
    none.value = "";
    none.textContent = "不纳入";
    if (manual[t] === "") none.selected = true;
    sel.appendChild(none);
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      var m = o.manifest || {};
      var hash = o.artifact_hash || "";
      var key = window.EGReports.key(o);
      var created = document.createElement("option");
      created.value = key;
      created.textContent = "rev:" + fmt(o.revision) + " · " + String(hash).slice(0, 12) + " · " + fmt(m.as_of_utc) + " · " + fmt(o.execution_status) + " · run " + fmt(o.run_id) + " · " + fmt(o.execution_status);
      sel.appendChild(created);
    }
    var latest = store() ? store().latest(t) : undefined;
    if (manual[t] === undefined) sel.value = latest === undefined || latest === null ? "" : latest;
    else if (manual[t] === "") sel.value = "";
    else sel.value = manual[t];
    sel.addEventListener("change", function () {
      manual[t] = sel.value === "" ? "" : sel.value;
      var btn = document.getElementById("daily-export");
      if (btn) btn.disabled = selectedReports().length === 0;
    });
    wrap.appendChild(label);
    wrap.appendChild(sel);
    return wrap;
  }

  function render() {
    var host = document.getElementById("daily-panel");
    if (!host) return;
    host.textContent = "";
    var title = document.createElement("h3");
    title.textContent = "每日组合研究";
    host.appendChild(title);
    for (var i = 0; i < TICKERS.length; i++) host.appendChild(buildControl(TICKERS[i]));
    var download = document.createElement("button");
    download.id = "daily-export";
    download.type = "button";
    download.textContent = "导出 Markdown";
    download.disabled = selectedReports().length === 0;
    download.addEventListener("click", function () {
      var md = exportMarkdown(selectedReports());
      var blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "evidenceguard-daily.md";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
    host.appendChild(download);
  }

  function mount() {
    var metrics = document.querySelector(".metrics");
    var host = document.getElementById("daily-panel");
    if (!host) {
      host = document.createElement("section");
      host.id = "daily-panel";
      host.className = "daily-panel";
    }
    if (metrics && metrics.parentNode) {
      metrics.parentNode.insertBefore(host, metrics);
    } else if (!host.parentNode) {
      document.body.appendChild(host);
    }
    document.addEventListener("evidenceguard-report-change", render);
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }

  window.EGDaily = { exportMarkdown: exportMarkdown, selectedReports: selectedReports };
})();
