import { createForecastPlot } from './forecast-plot.js';

const MAX_BYTES = 5 * 1024 * 1024;
const TICK_MS = 180;
const POLL_MS = 5000;

function el(id) {
  const node = document.getElementById('forecast-' + id);
  if (!node) throw new Error('missing #forecast-' + id);
  return node;
}

function isFinitePrice(v) {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 && v <= 1e9;
}

function isIso(v) {
  if (typeof v !== 'string' || v.length > 64) return false;
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(v)) return false;
  const t = Date.parse(v);
  return Number.isFinite(t);
}

function isSortedStrict(rows) {
  let prev = null;
  for (const r of rows) {
    const t = Date.parse(r.date);
    if (prev !== null && !(t > prev)) return false;
    prev = t;
  }
  return true;
}

function validate(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return '结构无效';
  }
  if (data.ticker !== 'AAPL' && data.ticker !== 'MSFT' && data.ticker !== 'NVDA') {
    return 'ticker 仅支持 AAPL/MSFT/NVDA';
  }
  if (typeof data.synthetic !== 'boolean') return 'synthetic 必须为布尔';
  if (typeof data.source !== 'string' || data.source.length > 200) return 'source 无效';
  if (!isIso(data.as_of_utc)) return 'as_of_utc 无效';
  const asOf = Date.parse(data.as_of_utc);
  const h = data.history, f = data.forecast;
  if (!Array.isArray(h) || h.length < 2 || h.length > 5000) return 'history 长度不合规';
  if (!Array.isArray(f) || f.length < 1 || f.length > 1000) return 'forecast 长度不合规';
  for (const r of h) {
    if (!r || typeof r !== 'object') return 'history 行无效';
    if (!isIso(r.date)) return 'history 日期无效';
    if (!isFinitePrice(r.close)) return 'history 价格无效';
    if (Date.parse(r.date) > asOf) return 'history 日期超过 as_of';
  }
  for (const r of f) {
    if (!r || typeof r !== 'object') return 'forecast 行无效';
    if (!isIso(r.date)) return 'forecast 日期无效';
    if (!isFinitePrice(r.estimate) || !isFinitePrice(r.lower) || !isFinitePrice(r.upper)) {
      return 'forecast 价格无效';
    }
    if (!(r.lower <= r.estimate && r.estimate <= r.upper)) return 'forecast 区间无效';
    if (!(Date.parse(r.date) > asOf)) return 'forecast 日期未在 as_of 之后';
  }
  if (!isSortedStrict(h)) return 'history 日期非严格递增';
  if (!isSortedStrict(f)) return 'forecast 日期非严格递增';
  if (Date.parse(h[h.length - 1].date) > asOf) return 'history 末点超过 as_of';
  return null;
}

function num(v, dflt) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : dflt;
}

async function readCapped(response) {
  const text = await response.text();
  if (text.length > MAX_BYTES) throw new Error('响应过大');
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return text;
}

export function init() {
  let data = null;
  let plot = null;
  let currentCount = 0;
  let total = 0;
  let playing = false;
  let raf = 0;
  let lastTick = 0;
  let busy = false;
  let lastRaw = '';
  let lastError = '';

  const ui = {
    source: el('source'), importBtn: el('import'), file: el('file'),
    demo: el('demo'), refresh: el('refresh'), auto: el('auto'),
    notice: el('notice'), history: el('history'), horizon: el('horizon'),
    canvas: el('canvas'), readout: el('readout'), play: el('play'),
    reset: el('reset'), progress: el('progress'), step: el('step'),
    status: el('status'),
  };

  for (const b of [ui.importBtn, ui.demo, ui.refresh, ui.play, ui.reset]) {
    b.classList.add('btn');
    b.type = 'button';
  }

  function setText(node, text) {
    node.textContent = text;
  }

  function setStatus(text) {
    setText(ui.status, text);
  }

  function setBusy(on) {
    busy = on;
    for (const b of [ui.importBtn, ui.demo, ui.refresh]) b.disabled = on;
  }

  function setSourceBadge() {
    if (!data) return;
    const kind = data.synthetic ? '合成演示' : '文件预测';
    const node = ui.source;
    node.textContent = '';
    const ticker = document.createElement('strong');
    ticker.textContent = data.ticker;
    const rest = document.createElement('span');
    rest.textContent = ' · ' + kind + ' · ' + data.source + ' · as_of ' + data.as_of_utc;
    node.appendChild(ticker);
    node.appendChild(rest);
  }

  function setNotice() {
    if (!data) return;
    if (data.synthetic) {
      setText(ui.notice, '合成演示：历史、预测和区间均为界面示例，非真实行情或模型输出。');
    } else {
      setText(ui.notice, '显示文件中预测序列；区间按文件呈现，未在此重新验证模型。');
    }
  }

  function visibleHistory() {
    const n = ui.history.value;
    if (n === 'all' || !data) return data ? data.history.slice() : [];
    return data.history.slice(-num(n, data.history.length));
  }

  function visibleForecast() {
    const n = ui.horizon.value;
    if (n === 'all' || !data) return data ? data.forecast.slice() : [];
    return data.forecast.slice(0, num(n, data.forecast.length));
  }

  function pause() {
    playing = false;
    lastTick = 0;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    setText(ui.play, '播放');
  }

  function updateProgress() {
    ui.progress.max = String(Math.max(total, 1));
    ui.progress.value = String(currentCount);
    setText(ui.step, currentCount + ' / ' + total);
    if (plot) plot.setCount(currentCount);
  }

  function scheduleTick() {
    if (!playing) return;
    raf = requestAnimationFrame(tick);
  }

  function startPlayback() {
    if (!plot || total <= 0) return;
    if (currentCount >= total) {
      currentCount = 0;
      updateProgress();
    }
    playing = true;
    lastTick = 0;
    setText(ui.play, '暂停');
    scheduleTick();
  }

  function tick(ts) {
    raf = 0;
    if (!playing || !plot) return;
    if (!lastTick) lastTick = ts;
    if (ts - lastTick >= TICK_MS) {
      lastTick = ts;
      currentCount = Math.min(currentCount + 1, total);
      updateProgress();
      if (currentCount >= total) { pause(); return; }
    }
    scheduleTick();
  }

  function rebuild(animateFromZero) {
    if (!data) return;
    pause();
    setSourceBadge();
    setNotice();
    const hist = visibleHistory();
    const fut = visibleForecast();
    const view = { ticker: data.ticker, as_of_utc: data.as_of_utc, history: hist, forecast: fut };
    plot = createForecastPlot(ui.canvas, ui.readout, hist, fut);
    total = fut.length;
    currentCount = animateFromZero ? 0 : total;
    ui.progress.max = String(Math.max(total, 1));
    ui.progress.value = String(currentCount);
    setText(ui.step, currentCount + ' / ' + total);
    if (plot) { plot.setCount(currentCount); plot.resize(); }
    if (animateFromZero) startPlayback();
  }

  function applyParsed(rawText, label) {
    let parsed;
    try { parsed = JSON.parse(rawText); }
    catch (e) { setStatus('刷新失败，保留上次数据（' + label + ' 解析失败）'); return false; }
    const err = validate(parsed);
    if (err) { setStatus('刷新失败，保留上次数据（' + label + '：' + err + '）'); return false; }
    const stamp = new Date().toISOString();
    if (rawText === lastRaw && plot) {
      setStatus(label + ' 成功 · 数据未变化 · ' + stamp);
      lastRaw = rawText;
      return true;
    }
    data = parsed;
    lastRaw = rawText;
    rebuild(false);
    setStatus(label + ' 成功 · ' + stamp);
    return true;
  }

  async function fetchLocal(url, label) {
    if (busy) return;
    setBusy(true);
    try {
      const signal = AbortSignal.timeout(4000);
      const resp = await fetch(url, { cache: 'no-store', signal });
      const text = await readCapped(resp);
      applyParsed(text, label);
    } catch (e) {
      setStatus('刷新失败，保留上次数据（' + label + '：' + (e && e.message ? e.message : 'error') + '）');
    } finally {
      setBusy(false);
    }
  }

  function loadRefresh() {
    if (!data) { fetchLocal('/forecast.json', '本地示例'); return; }
    const raw = lastRaw;
    if (busy) return;
    setBusy(true);
    (async () => {
      try {
        const signal = AbortSignal.timeout(4000);
        const resp = await fetch('/forecast.json', { cache: 'no-store', signal });
        const text = await readCapped(resp);
        let parsed;
        try { parsed = JSON.parse(text); }
        catch (e) { setStatus('刷新失败，保留上次数据（本地刷新解析失败）'); return; }
        const err = validate(parsed);
        if (err) { setStatus('刷新失败，保留上次数据（本地刷新：' + err + '）'); return; }
        const same = text === raw;
        if (same && plot) {
          setStatus('刷新成功 · 数据未变化 · ' + new Date().toISOString());
          return;
        }
        data = parsed;
        lastRaw = text;
        rebuild(false);
        setStatus('刷新成功 · ' + new Date().toISOString());
      } catch (e) {
        setStatus('刷新失败，保留上次数据（本地刷新：' + (e && e.message ? e.message : 'error') + '）');
      } finally {
        setBusy(false);
      }
    })();
  }

  function loadDemo() {
    ui.auto.checked = false;
    fetchLocal('/forecast-demo.json', '示例加载').then(() => {
      if (data && plot) startPlayback();
    });
  }

  ui.importBtn.addEventListener('click', () => { ui.file.click(); });

  ui.file.addEventListener('change', () => {
    const file = ui.file.files && ui.file.files[0];
    if (!file) return;
    if(file.size > MAX_BYTES){setStatus('导入失败，保留上次数据（文件超过 5MiB）');ui.file.value='';return;}
  file.text().then((text) => {
      if (text.length > MAX_BYTES) {
        setStatus('导入失败，保留上次数据（文件超过 5MiB）');
        ui.file.value = '';
        return;
      }
      ui.auto.checked = false;
      let parsed;
      try { parsed = JSON.parse(text); }
      catch (e) {
        setStatus('导入失败，保留上次数据（解析失败）');
        ui.file.value = '';
        return;
      }
      const err = validate(parsed);
      if (err) {
        setStatus('导入失败，保留上次数据（' + err + '）');
        ui.file.value = '';
        return;
      }
      data = parsed;
      lastRaw = text;
      rebuild(false);
      setStatus('导入成功 · ' + new Date().toISOString());
      ui.file.value = '';
    }).catch(() => {
      setStatus('导入失败，保留上次数据（读取错误）');
      ui.file.value = '';
    });
  });

  ui.demo.addEventListener('click', loadDemo);
  ui.refresh.addEventListener('click', loadRefresh);

  ui.play.addEventListener('click', () => {
    if (!plot) return;
    if (playing) pause(); else startPlayback();
  });

  ui.reset.addEventListener('click', () => {
    if (!plot) return;
    pause();
    currentCount = 0;
    updateProgress();
    startPlayback();
  });

  ui.progress.addEventListener('input', () => {
    if (!plot) return;
    pause();
    currentCount = Math.max(0, Math.min(num(ui.progress.value, 0), total));
    updateProgress();
  });

  ui.history.addEventListener('change', () => { rebuild(false); });
  ui.horizon.addEventListener('change', () => { rebuild(false); });

  ui.auto.addEventListener('change', () => {
    if (ui.auto.checked) loadRefresh();
    else setStatus('自动刷新已暂停');
  });

  const resizeTarget = ui.canvas.parentElement || ui.canvas;
  let observer = null;
  if (typeof ResizeObserver === 'function') {
    observer = new ResizeObserver(() => { if (plot) plot.resize(); });
    observer.observe(resizeTarget);
  }
  window.addEventListener('resize', () => { if (plot) plot.resize(); });

  setBusy(false);
  setStatus('自动读取本地JSON，不触发模型 · 等待数据');
    ui.auto.checked = true;
fetchLocal('/forecast.json', '初始加载');
  setInterval(() => { if (ui.auto.checked) loadRefresh(); }, POLL_MS);
}

function boot() { init(); }

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}
