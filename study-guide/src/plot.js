'use strict';
// Server-side SVG graphs for ```plot blocks in study material, e.g.
//
//   ```plot
//   f: x^3 - 4*x
//   f: 1/(x-2) | dashed
//   domain: -5, 5
//   range: -10, 10
//   points: (-2,0), (0,0), (2,0)
//   asymptote x: 2
//   asymptote y: 0
//   ticks: 1, 2            (x step, y step – optional)
//   xticks: pi             (label x axis in multiples of π)
//   ```
const { evaluate } = require('./expr');

let plotSeq = 0;
const COLORS = ['#5b6fd6', '#d1606f', '#3f9b74', '#c08a1e'];
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function niceStep(span) {
  const raw = span / 10;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
}

function piLabel(v) {
  const n = Math.round((v / Math.PI) * 2); // multiples of π/2
  if (n === 0) return '0';
  const num = n % 2 === 0 ? n / 2 : n;
  const den = n % 2 === 0 ? '' : '/2';
  const coef = Math.abs(num) === 1 ? (num < 0 ? '−' : '') : String(num).replace('-', '−');
  return `${coef}π${den}`;
}

function renderPlot(src) {
  const fns = []; const pts = []; const vas = []; const has = [];
  let domain = [-10, 10]; let range = null; let ticks = null; let piTicks = false; let title = '';
  for (const lineRaw of String(src).split('\n')) {
    const line = lineRaw.trim();
    if (!line || line.startsWith('#')) continue;
    const i = line.indexOf(':');
    if (i < 0) continue;
    const key = line.slice(0, i).trim().toLowerCase();
    const value = line.slice(i + 1).trim();
    const nums = () => value.split(',').map((x) => evaluate(x.trim()));
    if (key === 'f') {
      const [expr, opts = ''] = value.split('|').map((x) => x.trim());
      const label = (/label=([^;]+)/.exec(opts) || [])[1];
      fns.push({ expr, dashed: /dashed/.test(opts), label: label ? label.trim() : '' });
    } else if (key === 'domain') domain = nums();
    else if (key === 'range') range = nums();
    else if (key === 'ticks') ticks = nums();
    else if (key === 'xticks') piTicks = /pi/.test(value);
    else if (key === 'title') title = value;
    else if (key === 'points') {
      for (const m of value.matchAll(/\(([^,()]+),([^()]+)\)/g)) pts.push([evaluate(m[1]), evaluate(m[2])]);
    } else if (key === 'asymptote x') vas.push(...nums());
    else if (key === 'asymptote y') has.push(...nums());
  }
  const [x0, x1] = domain;
  const N = 600;
  const series = fns.map((f) => {
    const out = [];
    for (let k = 0; k <= N; k++) {
      const x = x0 + ((x1 - x0) * k) / N;
      let y;
      try { y = evaluate(f.expr, { x }); } catch { y = NaN; }
      out.push([x, y]);
    }
    return out;
  });
  if (!range) {
    const ys = series.flat().map((p) => p[1]).filter(Number.isFinite).sort((a, b) => a - b);
    const lo = ys.length ? ys[Math.floor(ys.length * 0.02)] : -10;
    const hi = ys.length ? ys[Math.ceil(ys.length * 0.98) - 1] : 10;
    const pad = (hi - lo) * 0.1 || 1;
    range = [Math.min(lo - pad, -1), Math.max(hi + pad, 1)];
  }
  const [y0, y1] = range;
  const clip = `pc${++plotSeq}`;
  const W = 520; const H = 360; const P = 28;
  const sx = (x) => P + ((x - x0) / (x1 - x0)) * (W - 2 * P);
  const sy = (y) => H - P - ((y - y0) / (y1 - y0)) * (H - 2 * P);
  const xs = piTicks ? Math.PI / 2 : (ticks ? ticks[0] : niceStep(x1 - x0));
  const ysStep = ticks ? ticks[1] || ticks[0] : niceStep(y1 - y0);
  let g = '';
  for (let v = Math.ceil(x0 / xs) * xs; v <= x1 + 1e-9; v += xs) {
    const X = sx(v).toFixed(1);
    g += `<line x1="${X}" x2="${X}" y1="${P}" y2="${H - P}" class="gl"/>`;
    if (Math.abs(v) > 1e-9) g += `<text x="${X}" y="${Math.min(H - P + 14, Math.max(P + 12, sy(0) + 14)).toFixed(1)}" text-anchor="middle">${piTicks ? piLabel(v) : +v.toFixed(4)}</text>`;
  }
  for (let v = Math.ceil(y0 / ysStep) * ysStep; v <= y1 + 1e-9; v += ysStep) {
    const Y = sy(v).toFixed(1);
    g += `<line x1="${P}" x2="${W - P}" y1="${Y}" y2="${Y}" class="gl"/>`;
    if (Math.abs(v) > 1e-9) g += `<text x="${Math.max(P + 2, Math.min(W - P - 2, sx(0) - 5)).toFixed(1)}" y="${(+Y + 4).toFixed(1)}" text-anchor="end">${+v.toFixed(4)}</text>`;
  }
  let axes = '';
  if (y0 <= 0 && y1 >= 0) axes += `<line x1="${P}" x2="${W - P}" y1="${sy(0)}" y2="${sy(0)}" class="ax"/>`;
  if (x0 <= 0 && x1 >= 0) axes += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${P}" y2="${H - P}" class="ax"/>`;
  const asym = vas.map((v) => `<line x1="${sx(v)}" x2="${sx(v)}" y1="${P}" y2="${H - P}" class="as"/>`).join('')
    + has.map((v) => `<line x1="${P}" x2="${W - P}" y1="${sy(v)}" y2="${sy(v)}" class="as"/>`).join('');
  const span = y1 - y0;
  const paths = series.map((s, idx) => {
    let d = ''; let pen = false; let prev = null;
    for (const [x, y] of s) {
      const ok = Number.isFinite(y) && y > y0 - span * 3 && y < y1 + span * 3;
      // Break the line at discontinuities (vertical asymptotes) as well as gaps.
      if (!ok || (prev && Math.abs(y - prev) > span * 1.5)) { pen = false; prev = ok ? y : null; if (!ok) continue; }
      d += `${pen ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(Math.max(y0 - span, Math.min(y1 + span, y))).toFixed(1)}`;
      pen = true; prev = y;
    }
    const f = fns[idx];
    return `<path d="${d}" fill="none" stroke="${COLORS[idx % COLORS.length]}" stroke-width="2.2"${f.dashed ? ' stroke-dasharray="6 5"' : ''}/>`;
  }).join('');
  const dots = pts.map(([x, y]) => `<circle cx="${sx(x).toFixed(1)}" cy="${sy(y).toFixed(1)}" r="4" fill="#fff" stroke="#2a2b38" stroke-width="1.6"><title>(${+x.toFixed(3)}, ${+y.toFixed(3)})</title></circle>`).join('');
  const legend = fns.some((f) => f.label)
    ? `<div class="plot-legend">${fns.map((f, i) => (f.label ? `<span><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(f.label)}</span>` : '')).join('')}</div>` : '';
  return `<figure class="plot">${title ? `<figcaption>${esc(title)}</figcaption>` : ''}<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title || fns.map((f) => `y = ${f.expr}`).join(', '))}"><defs><clipPath id="${clip}"><rect x="${P}" y="${P}" width="${W - 2 * P}" height="${H - 2 * P}"/></clipPath></defs>${g}${axes}<g clip-path="url(#${clip})">${asym}${paths}</g>${dots}</svg>${legend}</figure>`;
}

module.exports = { renderPlot };
