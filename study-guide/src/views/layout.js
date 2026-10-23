'use strict';
const { html, raw } = require('../html');
const { themeColor } = require('../themes');

const ICON = raw('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19.5V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2"/><path d="M8 7h7M8 11h5"/></svg>');

function csrfField(req) {
  return html`<input type="hidden" name="_csrf" value="${req.csrf}">`;
}

function navLinks(req, active) {
  const u = req.user;
  if (!u) return html`<a href="/login" class="${active === 'login' ? 'active' : ''}">Sign in</a><a href="/register" class="${active === 'register' ? 'active' : ''}">Register</a>`;
  const link = (href, key, label) => html`<a href="${href}" class="${active === key ? 'active' : ''}">${label}</a>`;
  const items = u.role === 'admin'
    ? [link('/admin', 'admin', 'Overview'), link('/admin/review', 'review', 'Review'), link('/admin/students', 'students', 'Students'),
      link('/admin/content', 'content', 'Content'), link('/subjects', 'subjects', 'Study guide'), link('/settings', 'settings', 'Settings')]
    : [link('/dashboard', 'dashboard', 'Dashboard'), link('/subjects', 'subjects', 'Study'), link('/tests', 'tests', 'Tests'),
      link('/progress', 'progress', 'Progress'), link('/settings', 'settings', 'Settings')];
  return html`${items}<form method="post" action="/logout" style="display:inline">${csrfField(req)}<button class="ghost small" type="submit">Sign out</button></form>`;
}

function layout(req, { title, active, body, flash }) {
  const accent = themeColor(req.user);
  const home = req.user ? (req.user.role === 'admin' ? '/admin' : '/dashboard') : '/';
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title ? `${title} · ` : ''}Study Guide</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/vendor/katex/katex.min.css">
<link rel="stylesheet" href="/static/app.css">
<style id="theme-vars">:root{--accent:${accent}}</style>
${req.user ? '' : raw(`<script>try{var c=localStorage.getItem('sg-accent');if(c&&/^#[0-9a-f]{6}$/i.test(c))document.getElementById('theme-vars').textContent=':root{--accent:'+c+'}'}catch(e){}</script>`)}
${req.user ? raw(`<script>try{localStorage.setItem('sg-accent',${JSON.stringify(accent)})}catch(e){}</script>`) : ''}
<meta name="csrf" content="${req.csrf}">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="${home}"><span class="brand-mark">${ICON}</span>Study Guide</a>
    <button class="ghost small nav-toggle" type="button" onclick="document.querySelector('.nav').classList.toggle('open')">Menu</button>
    <nav class="nav">${navLinks(req, active)}</nav>
  </div>
</header>
<main class="wrap">
${flash ? html`<div class="alert ${flash.type || ''}">${flash.text}</div>` : ''}
${body}
</main>
<footer class="footer">Self-paced study · ${req.user ? html`Signed in as ${req.user.name}` : 'Sign in to save your progress'}</footer>
<script src="/static/app.js" defer></script>
</body>
</html>`;
}

function fmtDate(s, withTime = false) {
  if (!s) return '';
  const d = new Date(String(s).replace(' ', 'T') + (String(s).includes('Z') ? '' : 'Z'));
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString('en-CA', withTime
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric' });
}

function scoreChip(score, status) {
  if (status === 'in_progress') return html`<span class="chip accent">In progress</span>`;
  if (score == null) return html`<span class="chip warn">Awaiting marking</span>`;
  const cls = score >= 75 ? 'good' : score >= 50 ? 'warn' : 'bad';
  return html`<span class="chip ${cls}">${score.toFixed(0)}%${status === 'submitted' ? ' · provisional' : ''}</span>`;
}

function bar(fraction) {
  const pct = Math.max(0, Math.min(100, Math.round((fraction || 0) * 100)));
  return html`<div class="bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct}%"></span></div>`;
}

// Small dependency-free line chart of test scores over time.
function scoreChart(tests) {
  const pts = tests.filter((t) => t.score != null && t.submitted_at).slice().reverse().slice(-20);
  if (pts.length < 2) return html`<p class="muted">Your score trend appears after two marked tests.</p>`;
  const W = 640; const H = 200; const P = 30;
  const x = (i) => P + (i * (W - 2 * P)) / (pts.length - 1);
  const y = (v) => H - P - (v / 100) * (H - 2 * P);
  const line = pts.map((t, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(t.score).toFixed(1)}`).join(' ');
  const grid = [0, 25, 50, 75, 100].map((v) => `<line x1="${P}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-dasharray="${v ? '3 4' : ''}"/><text x="${P - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join('');
  const dots = pts.map((t, i) => `<circle cx="${x(i)}" cy="${y(t.score)}" r="4" fill="var(--strong)"><title>${t.kind} · ${t.score.toFixed(0)}%</title></circle>`).join('');
  return raw(`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Score trend">${grid}<path d="${line}" fill="none" stroke="var(--strong)" stroke-width="2" stroke-opacity=".7"/>${dots}</svg>`);
}

module.exports = { layout, csrfField, fmtDate, scoreChip, bar, scoreChart };
