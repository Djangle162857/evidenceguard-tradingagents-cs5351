(function () {
  "use strict";
  if (typeof window === "undefined" || typeof document === "undefined") return;
  var EGReports = window.EGReports;
  if (!EGReports || typeof EGReports.Store !== "function") return;
  var store = new EGReports.Store();
  var selectedKey = null;
  var TICKERS = ["AAPL", "MSFT", "NVDA"];
  var SECTIONS = ["利好因素", "风险因素", "关键分歧", "未来一周观察", "数据缺口"];
  var LIMIT = 5 * 1024 * 1024;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function $id(id) { return document.getElementById(id); }
  function put(id, value) {
    var node = $id(id);
    if (node) node.textContent = value === undefined || value === null ? "" : String(value);
  }
  function showView(name) {
    if (typeof window.showView === "function") return window.showView(name);
    document.querySelectorAll(".view").forEach(function (v) { v.hidden = v.id !== "view-" + name; });
  }
  function toast(text) {
    if (typeof window.toast === "function") return window.toast(text);
    var box = $id("feedback");
    if (box) { box.textContent = text; box.hidden = false; }
  }
  function short(s) {
    var t = String(s || "");
    return t.length > 16 ? t.slice(0, 16) + "…" : t;
  }
  function refs(text) {
    var out = [];
    var re = /\[(cl-[0-9a-fA-F]+)\]/g;
    var m;
    while ((m = re.exec(String(text || ""))) !== null) out.push(m[1]);
    return out;
  }
  function manifestOf(a) { return (a && a.manifest) || {}; }
  function tickerOf(a) { return manifestOf(a).ticker; }
  function asOfOf(a) { var v = manifestOf(a).as_of_utc; return typeof v === "string" && v ? v : "—"; }
  function statusOf(a) { return a && typeof a.execution_status === "string" && a.execution_status ? a.execution_status : "—"; }
  function hashOf(a) { var h = a && a.artifact_hash; return typeof h === "string" && h ? h : "—"; }
  function revisionOf(a) { return a && a.revision !== undefined && a.revision !== null ? a.revision : "—"; }
  function runOf(a) { return a && typeof a.run_id === "string" ? a.run_id : "—"; }
  function tickerOfRun(a) { var t = tickerOf(a); return typeof t === "string" && t ? t : "—"; }
  function label(a) {
    return tickerOfRun(a) + " · " + runOf(a) + " · rev " + revisionOf(a) + " · " + short(hashOf(a)) +
      " · " + asOfOf(a) + " · " + statusOf(a);
  }
  function currentNode() { return selectedKey ? store.get(selectedKey) || null : null; }
  function ensurePre() {
    var metrics = document.querySelector(".metrics");
    if (!metrics || !metrics.parentNode) return null;
    if ($id("theme-toggle") && $id("report-select")) return metrics.parentNode;
    var box = el("section", "workbench-controls");
    var row = el("div", "workbench-row");
    var theme = el("button", "reference-btn", "切换主题");
    theme.type = "button";
    theme.id = "theme-toggle";
    theme.addEventListener("click", function () {
      var root = document.documentElement;
      var dark = root.getAttribute("data-theme") === "dark";
      root.setAttribute("data-theme", dark ? "light" : "dark");
    });
    row.appendChild(theme);
    var lab = el("label", "muted", "当前报告");
    lab.setAttribute("for", "report-select");
    row.appendChild(lab);
    var sel = el("select");
    sel.id = "report-select";
    sel.setAttribute("aria-label", "当前报告");
    sel.addEventListener("change", function () {
      var k = String(sel.value || "");
      if (!k) return;
      var a = store.get(k);
      if (!a) return;
      selectedKey = k;
      syncMarket(a);
      refreshControls(false);
      window.renderArtifact(a);
      renderStructured();
      dispatchChange(a);
    });
    row.appendChild(sel);
    var count = el("span", "muted");
    count.id = "report-count";
    row.appendChild(count);
    var stocks = el("div", "workbench-row");
    stocks.id = "stock-summaries";
    row.appendChild(stocks);
    var mismatch = el("p", "muted");
    mismatch.id = "market-mismatch";
    mismatch.setAttribute("role", "status");
    box.appendChild(row);
    box.appendChild(mismatch);
    metrics.parentNode.insertBefore(box, metrics);
    return metrics.parentNode;
  }
  function syncMarket(a) {
    var t = tickerOf(a);
    var input = $id("market-symbol");
    if (input && typeof t === "string" && t && input.value !== t) {
      input.value = t;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    updateMismatch();
  }
  function sectionsOf(report) {
    var b;
    try { b = EGReports.brief(String(report || "")); } catch (e) { b = { summary: null, sections: {}, complete: false, missing: [] }; }
    if (!b || typeof b !== "object") b = { summary: null, sections: {}, complete: false, missing: [] };
    return b;
  }
  function claimButton(id) {
    var btn = el("button", "reference-btn", short(id));
    btn.type = "button";
    btn.title = id;
    btn.addEventListener("click", function () {
      showView("claims");
      var hit = null;
      document.querySelectorAll("#claims-list .claim-card").forEach(function (card) {
        if (hit) return;
        if (card.dataset && card.dataset.claimId === id) hit = card;
      });
      if (hit) { hit.scrollIntoView({ block: "center" }); hit.focus && hit.focus(); }
    });
    return btn;
  }
  function refLine(container, node, text) {
    var ids = refs(text);
    container.appendChild(node);
    if (!ids.length) return;
    var line = el("div", "claim-refs");
    ids.forEach(function (id) {
      if (node.someKnown && node.someKnown(id) === true) line.appendChild(claimButton(id));
      else line.appendChild(el("span", "muted", "缺失引用 " + short(id)));
    });
    container.appendChild(line);
  }
  function textBlock(a, text) {
    var wrap = el("div", "brief-section");
    var ids = refs(text);
    var known = function (id) {
      return ((a && a.claims) || []).some(function (c) { return c && c.claim_id === id; });
    };
    var p = el("p", "text", String(text || ""));
    p.someKnown = known;
    refLine(wrap, p, String(text || ""));
    return wrap;
  }
  function renderStructured() {
    var a = currentNode();
    var box = $id("report-content");
    if (!box) return;
    box.replaceChildren();
    if (!a) { box.appendChild(el("p", "empty", "简报不完整")); return; }
    var b = sectionsOf(a.report);
    if (b.summary && String(b.summary).length) box.appendChild(textBlock(a, String(b.summary)));
    else box.appendChild(el("p", "empty", "简报不完整"));
    if (!b.complete) box.appendChild(el("p", "badge warn", "简报不完整"));
    SECTIONS.forEach(function (title) {
      var sec = el("section", "brief-section");
      sec.appendChild(el("h3", "", title));
      var txt = b.sections && b.sections[title];
      if (typeof txt === "string" && txt.length) sec.appendChild(textBlock(a, txt));
      else sec.appendChild(el("p", "muted", "信息不足（报告未提供）"));
      box.appendChild(sec);
    });
    var details = $id("details-list");
    if (details) {
      var old = $id("original-report-details");
      if (old && old.parentNode) old.parentNode.removeChild(old);
      var back = el("details");
      back.id = "original-report-details";
      back.appendChild(el("summary", "", "完整原始报告"));
      back.appendChild(el("pre", "mono", String(a.report || "")));
      details.parentNode && details.parentNode.insertBefore(back, details.nextSibling);
    }
  }
  function renderStockSummaries() {
    var box = $id("stock-summaries");
    if (!box) return;
    box.replaceChildren();
    TICKERS.slice(0, 3).forEach(function (t) {
      var k = store.latest(t);
      var a = k ? store.get(k) : null;
      var summary = "";
      if (a) {
        var b = sectionsOf(a.report);
        summary = b.summary && String(b.summary).length ? String(b.summary) : "简报不完整";
      }
      var text = t + " · " + (a ? summary + " · " + asOfOf(a) + " · " + statusOf(a) : "待导入");
      var btn = el("button", "reference-btn", text);
      btn.type = "button";
      btn.addEventListener("click", function () {
        if (!k) { toast(t + " 尚未导入报告"); return; }
        var art = store.get(k);
        if (!art) return;
        selectedKey = k;
        refreshControls(false);
        window.renderArtifact(art);
        renderStructured();
        dispatchChange(art);
      });
      box.appendChild(btn);
    });
  }
  function refreshControls(rebuild) {
    var sel = $id("report-select");
    var count = $id("report-count");
    var items = store.items();
    if (sel && (rebuild || sel.options.length !== items.length)) {
      sel.replaceChildren();
      items.forEach(function (row) {
        var o = el("option", "", label(row.artifact));
        o.value = row.key;
        sel.appendChild(o);
      });
    }
    if (sel && selectedKey) sel.value = selectedKey;
    if (count) count.textContent = "共 " + items.length + " 份报告";
    renderStockSummaries();
  }
  function dispatchChange(a) {
    try {
      document.dispatchEvent(new CustomEvent("evidenceguard-report-change", { detail: { key: selectedKey, artifact: a } }));
    } catch (e) { /* ignore */ }
  }
  function wrapRender() {
    var original = window.renderArtifact;
    if (typeof original !== "function" || original.__workbench) return;
    var wrapped = function (a) {
      var res = null;
      try { res = store.add(a); } catch (e) { toast("报告与已有记录冲突"); return; }
      original(a);
      if (res && res.key) selectedKey = res.key;
      document.querySelectorAll("#claims-list .claim-card").forEach(function (card, index) {
        var cl = (a.claims || [])[index];
        card.dataset.claimId = cl ? String(cl.claim_id) : "";
        card.tabIndex = -1;
      });
      ensurePre();
      syncMarket(a);
      refreshControls(true);
      renderStructured();
      dispatchChange(a);
      if (res && res.duplicate) toast("报告重复导入");
    };
    wrapped.__workbench = true;
    window.renderArtifact = wrapped;
  }
  window.importWorkbenchFiles = async function (files) {
    var list = files ? Array.prototype.slice.call(files) : [];
    var ok = 0; var dup = 0; var bad = 0;
    for (var i = 0; i < list.length; i += 1) {
      var f = list[i];
      try {
        if (!f || typeof f.text !== "function") throw new Error("bad file");
        if (typeof f.size === "number" && f.size > LIMIT) throw new Error("too large");
        var raw = await f.text();
        var d = JSON.parse(String(raw || ""));
        var before = store.items().length;
        try { store.add(d); } catch (err) { bad += 1; continue; }
        ok += 1;
        if (store.items().length === before) dup += 1;
        window.renderArtifact(d);
        showView("overview");
      } catch (e) { bad += 1; }
    }
    var parts = ["成功导入 " + ok + " 份"];
    if (dup) parts.push("重复 " + dup + " 份");
    if (bad) parts.push("失败 " + bad + " 份");
    toast(parts.join("，"));
    refreshControls(true);
  };
  function updateMismatch() {
    var node = $id("market-mismatch");
    if (!node) return;
    var a = currentNode();
    var manifestTicker = a ? tickerOf(a) : undefined;
    var input = $id("market-symbol");
    var marketTicker = input ? input.value : "";
    var bad = typeof manifestTicker === "string" && manifestTicker && marketTicker && manifestTicker !== marketTicker;
    node.textContent = bad ? "当前报告标的与行情不一致" : "";
    node.className = bad ? "badge warn" : "muted";
  }
  function init() {
    ensurePre();
    var market = $id("market-symbol");
    if (market) market.addEventListener("change", updateMismatch);
    var input = $id("file-input");
    if (input) { input.multiple = true; input.setAttribute("multiple", ""); }
    wrapRender();
    var cur = currentNode();
    if (cur) {
      try { var r = store.add(cur); if (r && r.key) selectedKey = r.key; } catch (e) { /* keep */ }
      refreshControls(true);
      renderStructured();
    } else refreshControls(true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  window.EGWorkbench = { store: store };
})();
