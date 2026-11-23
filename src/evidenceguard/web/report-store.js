'use strict';

const TICKERS = ['AAPL', 'MSFT', 'NVDA'];
const SECTIONS = ['利好因素', '风险因素', '关键分歧', '未来一周观察', '数据缺口'];

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    const out = {};
    for (const k of Object.keys(value).sort()) out[k] = canonical(value[k]);
    return out;
  }
  return value;
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function isId(v) {
  return typeof v === 'string' && v.length > 0;
}

function tickerOf(a) {
  return a && a.manifest && typeof a.manifest === 'object' ? a.manifest.ticker : undefined;
}

function asOfOf(a) {
  return a && a.manifest && typeof a.manifest === 'object' ? a.manifest.as_of_utc : undefined;
}

function key(a) {
  if (!isPlainObject(a)) throw new TypeError('artifact required');
  const rev = a.revision === undefined || a.revision === null ? null : a.revision;
  const hash = typeof a.artifact_hash === 'string' && a.artifact_hash
    ? a.artifact_hash
    : JSON.stringify(canonical(a));
  return JSON.stringify([tickerOf(a), a.run_id, rev, hash]);
}

function clone(v) {
  if (v === null || typeof v !== 'object') return v;
  return JSON.parse(JSON.stringify(v));
}

function validate(a) {
  if (!isPlainObject(a)) throw new TypeError('artifact required');
  if (!isPlainObject(a.manifest)) throw new TypeError('manifest required');
  const m = a.manifest;
  if (!TICKERS.includes(m.ticker)) throw new RangeError('invalid ticker');
  if (typeof a.report !== 'string') throw new TypeError('report must be string');
  if (typeof a.run_id !== 'string') throw new TypeError('run_id must be string');
  if (!Array.isArray(a.evidence)) throw new TypeError('evidence must be object[]');
  for (const e of a.evidence) {
    if (!isPlainObject(e)) throw new TypeError('evidence item must be object');
    if (!isId(e.evidence_id)) throw new TypeError('evidence_id required');
  }
  if (!Array.isArray(a.claims)) throw new TypeError('claims must be object[]');
  for (const c of a.claims) {
    if (!isPlainObject(c)) throw new TypeError('claim item must be object');
    if (!isId(c.claim_id)) throw new TypeError('claim_id required');
  }
  if (m.run_id !== undefined && m.run_id !== null && m.run_id !== a.run_id) {
    throw new RangeError('manifest.run_id mismatch');
  }
  const ar = a.revision === undefined ? null : a.revision;
  if (m.revision !== undefined && m.revision !== null && m.revision !== ar) {
    throw new RangeError('manifest.revision mismatch');
  }
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function headingPattern(title) {
  return new RegExp('^(#{2,3})\\s*' + escapeRegExp(title) + '\\s*$', 'm');
}

function boldPattern(title) {
  return new RegExp('^\\*\\*' + escapeRegExp(title) + '\\*\\*\\s*:?[ \\t]*', 'm');
}

function metadataPattern() {
  return new RegExp('^(?:#{2,3}\\s*|\\*\\*)\\s*(?:Price Target|Time Horizon)\\b', 'm');
}

function anyHeadingIndex(body) {
  const m = /^(?:#{2,3}\s+\S|\*\*[^*]+\*\*)/m.exec(body);
  return m ? m.index : -1;
}

function sectionContent(report, title, allTitles) {
  const re = headingPattern(title);
  const m = re.exec(report);
  if (!m) return null;
  const level = m[1].length;
  const start = m.index + m[0].length;
  let end = report.length;
  const metaHead = metadataPattern().exec(report.slice(start));
  if (metaHead) end = start + metaHead.index;
  const next = /^(#{2,3})\s+\S.*$/gm;
  next.lastIndex = start;
  let n;
  while ((n = next.exec(report)) !== null) {
    const t = n[0].replace(/^#+\s*/, '').trim();
    if (n.index >= end) break;
    if (allTitles.includes(t) || n[1].length <= level || t.startsWith('Price Target') ||
        t.startsWith('Time Horizon')) {
      end = n.index;
      break;
    }
  }
  return report.slice(start, end).trim();
}

function extractSummary(report) {
  let es = /^(#{2,3})\s*Executive Summary\s*$/m.exec(report);
  let it = /^(#{2,3})\s*Investment Thesis\s*$/m.exec(report);
  if (!es) {
    es = boldPattern('Executive Summary').exec(report);
    it = boldPattern('Investment Thesis').exec(report);
    if (!es) return null;
    const start = es.index + es[0].length;
    let end = it && it.index > es.index ? it.index : report.length;
    const body = report.slice(start, end).trim();
    if (!body) return null;
    const meta = metadataPattern().exec(body);
    return meta ? body.slice(0, meta.index).trim() || null : body;
  }
  const start = es.index + es[0].length;
  let end = report.length;
  if (it && it.index > es.index) end = it.index;
  const body = report.slice(start, end).trim();
  if (!body) return null;
  const meta = metadataPattern().exec(body);
  if (meta) return body.slice(0, meta.index).trim() || null;
  return body;
}

function brief(report) {
  if (typeof report !== 'string') throw new TypeError('report must be string');
  const summary = extractSummary(report);
  const sections = {};
  const missing = [];
  let ordered = true;
  let seen = 0;
  for (const title of SECTIONS) {
    const content = sectionContent(report, title, SECTIONS);
    if (content === null) {
      sections[title] = null;
      missing.push(title);
      ordered = false;
      continue;
    }
    if (!content) {
      sections[title] = content;
      missing.push(title);
      ordered = false;
      continue;
    }
    sections[title] = content;
    if (ordered) seen += 1;
  }
  if (summary === null) missing.unshift('Executive Summary');
  const found = [];
  const seenHeads = /^### (.*)$/gm;
  let hm;
  while ((hm = seenHeads.exec(report)) !== null) {
    found.push(hm[1].trim());
  }
  const orderExact = found.length === SECTIONS.length &&
    SECTIONS.every((name, i) => found[i] === name);
  if (!orderExact && !missing.includes('章节顺序或重复')) missing.push('章节顺序或重复');
  const orderOk = ordered && orderExact && seen === SECTIONS.length;
  const complete = typeof summary === 'string' && summary.length > 0 && orderOk && missing.length === 0;
  return { summary, sections, complete, missing };
}

class Store {
  constructor() {
    this.map = new Map();
  }

  add(a) {
    validate(a);
    const art = clone(a);
    const k = key(art);
    const existing = this.map.get(k);
    if (existing) {
      if (JSON.stringify(canonical(existing)) === JSON.stringify(canonical(art))) {
        return { key: k, duplicate: true };
      }
      throw new Error('conflicting artifact for key: ' + k);
    }
    this.map.set(k, art);
    return { key: k, duplicate: false };
  }

  get(k) {
    return this.map.has(k) ? this.map.get(k) : null;
  }

  items() {
    return Array.from(this.map.entries()).map(([k, artifact]) => ({ key: k, artifact }));
  }

  latest(ticker) {
    let best = null;
    let bestTime = null;
    let bestRev = null;
    for (const k of this.map.keys()) {
      const a = this.map.get(k);
      if (tickerOf(a) !== ticker) continue;
      const raw = asOfOf(a);
      const time = typeof raw === 'string' && raw.length > 0 ? Date.parse(raw) : NaN;
      const t = Number.isNaN(time) ? null : time;
      const rev = typeof a.revision === 'number' && Number.isFinite(a.revision) ? a.revision : null;
      if (best === null || compareLatest(t, bestTime, rev, bestRev, k, best) > 0) {
        best = k;
        bestTime = t;
        bestRev = rev;
      }
    }
    return best;
  }
}

function compareLatest(t1, t2, r1, r2, k1, k2) {
  if (t1 !== t2) {
    if (t1 === null) return -1;
    if (t2 === null) return 1;
    return t1 > t2 ? 1 : -1;
  }
  if (r1 !== r2) {
    if (r1 === null) return -1;
    if (r2 === null) return 1;
    return r1 > r2 ? 1 : -1;
  }
  if (k1 === k2) return 0;
  return k1 < k2 ? 1 : -1;
}

const EGReports = { Store, key, brief, canonical };
globalThis.EGReports = EGReports;
if (typeof module !== 'undefined' && module.exports) module.exports = EGReports;
