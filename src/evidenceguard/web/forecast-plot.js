// Fincept-inspired dark forecast chart (native Canvas 2D, no libs)
const BG = "#0f1623", GRID = "#293243", AXIS = "#95a2b8", TXT = "#c9d4e5";
const BLUE = "#68a7ff", ORANGE = "#ff984d", PANG = "rgba(181,154,255,.17)", PINK = "#b59aff";
const CROSS = "rgba(180,190,210,.55)";

const fmtPrice = (v) => "$" + v.toFixed(2);
const fmtMMDD = (ms) => {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return p(d.getMonth() + 1) + "-" + p(d.getDate());
};

export function createForecastPlot(canvas, readout, history, forecast) {
  const ctx = canvas.getContext("2d");
  let count = forecast.length;
  let W = 900, H = 340;
  let cross = null;

  // Domains fixed across the entire forecast so the axis never jumps.
  const xs = history.map((r) => Date.parse(r.date)).concat(forecast.map((r) => Date.parse(r.date)));
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const ys = history.map((r) => r.close)
    .concat(forecast.map((r) => r.lower))
    .concat(forecast.map((r) => r.upper));
  let yLo = Math.min(...ys), yHi = Math.max(...ys);
  const pad = (yHi - yLo || 1) * 0.05;
  yLo -= pad; yHi += pad;

  const M = { l: 55, r: 20, t: 24, b: 34 };
  const px = () => ({ x0: M.l, x1: W - M.r, y0: M.t, y1: H - M.b });
  const mapX = (ms, s) => s.x0 + ((ms - xMin) / (xMax - xMin || 1)) * (s.x1 - s.x0);
  const mapY = (v, s) => s.y1 - ((v - yLo) / (yHi - yLo || 1)) * (s.y1 - s.y0);

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth || 900;
    const ch = canvas.clientHeight || 340;
    W = cw; H = ch;
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function draw() {
    const s = px();
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, W, H);
    ctx.font = "11px system-ui, sans-serif";
    ctx.textBaseline = "middle";

    // horizontal grid + price labels
    for (let i = 0; i <= 4; i++) {
      const y = s.y0 + (i / 4) * (s.y1 - s.y0);
      ctx.strokeStyle = GRID;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(s.x0, y); ctx.lineTo(s.x1, y); ctx.stroke();
      const v = yHi - (i / 4) * (yHi - yLo);
      ctx.fillStyle = AXIS;
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(2), s.x0 - 6, y);
    }

    // date ticks
    ctx.textAlign = "center";
    for (let i = 0; i <= 4; i++) {
      const ms = xMin + (i / 4) * (xMax - xMin);
      ctx.fillStyle = AXIS;
      ctx.fillText(fmtMMDD(ms), mapX(ms, s), s.y1 + 14);
    }

    const lastH = Date.parse(history[history.length - 1].date);
    const bx = mapX(lastH, s);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = PINK;
    ctx.beginPath(); ctx.moveTo(bx, s.y0); ctx.lineTo(bx, s.y1); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = PINK;
    ctx.textAlign = "left";
    ctx.fillText("预测起点", bx + 4, s.y0 + 6);

    // visible future slice
    const fut = forecast.slice(0, count);

    // interval polygon
    if (fut.length) {
      ctx.beginPath();
      fut.forEach((r, i) => {
        const x = mapX(Date.parse(r.date), s), y = mapY(r.upper, s);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      for (let i = fut.length - 1; i >= 0; i--) {
        ctx.lineTo(mapX(Date.parse(fut[i].date), s), mapY(fut[i].lower, s));
      }
      ctx.closePath();
      ctx.fillStyle = PANG;
      ctx.fill();
    }

    // history line
    ctx.strokeStyle = BLUE;
    ctx.lineWidth = 2;
    ctx.beginPath();
    history.forEach((r, i) => {
      const x = mapX(Date.parse(r.date), s), y = mapY(r.close, s);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // forecast line anchored at last history close
    if (fut.length) {
      ctx.save();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = ORANGE;
      ctx.beginPath();
      ctx.moveTo(bx, mapY(history[history.length - 1].close, s));
      fut.forEach((r) => ctx.lineTo(mapX(Date.parse(r.date), s), mapY(r.estimate, s)));
      ctx.stroke();
      ctx.restore();
    }

    // crosshair
    if (cross) {
      const cx = mapX(cross.ms, s), cy = mapY(cross.price, s);
      ctx.save();
      ctx.strokeStyle = CROSS;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, s.y0); ctx.lineTo(cx, s.y1); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(s.x0, cy); ctx.lineTo(s.x1, cy); ctx.stroke();
      ctx.restore();
      ctx.fillStyle = ORANGE;
      ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();
    }
  }

  // nearest timestamp among visible points (history + first count future)
  function nearest(mx) {
    const s = px();
    const pts = history.map((r) => ({
      ms: Date.parse(r.date), price: r.close, fut: false, row: r
    }));
    forecast.slice(0, count).forEach((r) => pts.push({
      ms: Date.parse(r.date), price: r.estimate, fut: true, row: r
    }));
    let best = null, bd = Infinity;
    pts.forEach((p) => {
      const d = Math.abs(mapX(p.ms, s) - mx);
      if (d < bd) { bd = d; best = p; }
    });
    return best;
  }

  canvas.onpointermove = (ev) => {
    const s = px();
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    let cx = mx;
    if (cx < s.x0) cx = s.x0;
    if (cx > s.x1) cx = s.x1;
    const p = nearest(cx);
    if (!p) return;
    cross = { ms: p.ms, price: p.price };
    draw();
    const date = fmtMMDD(p.ms);
    if (p.fut) {
      const r = p.row;
      readout.textContent = date + " 预测 " + fmtPrice(r.estimate) +
        "（区间 " + fmtPrice(r.lower) + " ~ " + fmtPrice(r.upper) + "）";
    } else {
      readout.textContent = date + " 历史 " + fmtPrice(p.price);
    }
  };
  canvas.onpointerleave = () => {
    cross = null;
    readout.textContent = "提示悬停查看数据";
    draw();
  };

  readout.textContent = "提示悬停查看数据";
  resize();

  return {
    setCount(n) {
      count = Math.max(0, Math.min(forecast.length, n | 0));
      draw();
    },
    resize,
  };
}
