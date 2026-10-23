'use strict';
const { test, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { loadConfig } = require('../src/config');
const { createApp } = require('../src/app');
const E = require('../src/expr');
const T = require('../src/tests');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sg-test-'));
let server; let base; let db;

// Minimal cookie-aware HTTP client.
function client() {
  const jar = {};
  async function req(method, url, body, headers = {}) {
    const cookie = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ');
    const opts = { method, headers: { cookie, ...headers }, redirect: 'manual' };
    if (body && typeof body === 'object' && !(body instanceof URLSearchParams) && headers['content-type'] === 'application/json') opts.body = JSON.stringify(body);
    else if (body) { opts.body = new URLSearchParams(body); opts.headers['content-type'] = 'application/x-www-form-urlencoded'; }
    const res = await fetch(base + url, opts);
    for (const c of res.headers.getSetCookie()) {
      const [kv] = c.split(';');
      const i = kv.indexOf('=');
      jar[kv.slice(0, i)] = kv.slice(i + 1);
    }
    const text = await res.text();
    return { status: res.status, location: res.headers.get('location'), text };
  }
  const csrf = async (url = '/login') => {
    const r = await req('GET', url);
    return (/name="csrf" content="([^"]+)"/.exec(r.text) || [])[1];
  };
  return { req, csrf, jar };
}

async function register(c, name, email, pw = 'secret123') {
  const token = await c.csrf('/register');
  const r = await c.req('POST', '/register', { _csrf: token, name, email, password: pw, password2: pw });
  assert.match(r.text, /Check your email/);
  const mail = db.get("SELECT body FROM outbox WHERE to_email=? ORDER BY id DESC", email).body;
  const link = /\/verify\?token=\S+/.exec(mail)[0];
  const v = await c.req('GET', link);
  assert.strictEqual(v.location, '/login?m=verified');
  const t2 = await c.csrf('/login');
  const l = await c.req('POST', '/login', { _csrf: t2, email, password: pw });
  assert.strictEqual(l.location, '/dashboard');
}

before(async () => {
  const config = loadConfig({
    dbFile: path.join(tmp, 'test.db'), uploadsDir: path.join(tmp, 'uploads'),
    contentDir: path.join(__dirname, '..', 'content'), adminEmail: 'admin@example.com', adminPassword: 'admin1234',
    appUrl: 'http://localhost', smtpUrl: '', smtpHost: '', anthropicKey: '', quiet: true, registration: 'open', allowedDomains: [],
  });
  const made = createApp(config);
  db = made.db;
  await new Promise((resolve) => { server = made.app.listen(0, resolve); });
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => { server.close(); fs.rmSync(tmp, { recursive: true, force: true }); });

test('expression evaluator and formatting', () => {
  assert.strictEqual(E.evaluate('2+3*4^2'), 50);
  assert.strictEqual(E.evaluate('-x^2', { x: 3 }), -9);
  assert.strictEqual(E.evaluate('logb(2, 32)'), 5);
  assert.throws(() => E.evaluate('process.exit()'));
  assert.strictEqual(E.formatSig(0.29545, 2), '0.30');
  assert.strictEqual(E.formatSig(12345, 2), '12000');
  const q = { vars: { m: { min: 2, max: 2, step: 1, decimals: 1 } }, derived: { w: 'm*9.8' } };
  assert.strictEqual(E.fill('{{m}} kg weighs {{w:2}} N', E.buildScope(q)), '2.0 kg weighs 20 N');
  assert.ok(E.checkNumeric(7.35, '7.4 N [up]', 0.02));
  assert.ok(!E.checkNumeric(7.35, '8 N', 0.02));
  assert.strictEqual(E.parseNumber('6 000 N'), 6000);
});

test('period keys', () => {
  assert.strictEqual(T.periodKey('weekly', new Date(2026, 0, 1)), '2026-W01');
  assert.strictEqual(T.periodKey('monthly', new Date(2026, 9, 23)), '2026-10');
  assert.strictEqual(T.periodKey('ondemand'), null);
});

test('registration requires email confirmation; bad passwords rejected', async () => {
  const c = client();
  const token = await c.csrf('/register');
  const weak = await c.req('POST', '/register', { _csrf: token, name: 'X', email: 'x@example.com', password: 'short', password2: 'short' });
  assert.strictEqual(weak.status, 400);
  const noCsrf = await c.req('POST', '/register', { name: 'X', email: 'x@example.com', password: 'secret123', password2: 'secret123' });
  assert.strictEqual(noCsrf.status, 403);
  await c.req('POST', '/register', { _csrf: token, name: 'Y', email: 'y@example.com', password: 'secret123', password2: 'secret123' });
  const t2 = await c.csrf('/login');
  const login = await c.req('POST', '/login', { _csrf: t2, email: 'y@example.com', password: 'secret123' });
  assert.match(login.text, /Confirm your email/);
});

test('full student flow, privacy between students, admin marking', async () => {
  const a = client(); const b = client();
  await register(a, 'Ann', 'ann@example.com');
  await register(b, 'Ben', 'ben@example.com');

  const dash = await a.req('GET', '/dashboard');
  assert.match(dash.text, /Physics 11/);
  const tok = (/name="csrf" content="([^"]+)"/.exec(dash.text))[1];

  const study = await a.req('GET', '/study/physics-11/4-2');
  assert.strictEqual(study.status, 200);
  assert.match(study.text, /katex/);

  const start = await a.req('POST', '/tests/new', { _csrf: tok, subject: 'physics-11', kind: 'daily' });
  assert.match(start.location, /^\/tests\/\d+$/);
  const testId = Number(start.location.split('/').pop());
  // Starting the daily test again returns the same test.
  const again = await a.req('POST', '/tests/new', { _csrf: tok, subject: 'physics-11', kind: 'daily' });
  assert.strictEqual(again.location, start.location);

  const items = db.all('SELECT * FROM test_items WHERE test_id=?', testId);
  assert.strictEqual(items.length, T.KINDS.daily.count);
  for (const it of items) {
    const q = JSON.parse(db.get('SELECT data FROM questions WHERE id=?', it.question_id).data);
    assert.ok(['problem', 'conceptual', 'explain', 'analysis', 'design'].includes(q.type), 'only subjective/problem questions');
  }

  // Ben cannot see or change Ann's test.
  assert.strictEqual((await b.req('GET', `/tests/${testId}`)).status, 404);
  const bTok = (/name="csrf" content="([^"]+)"/.exec((await b.req('GET', '/dashboard')).text))[1];
  assert.strictEqual((await b.req('POST', `/tests/${testId}/save`, { _csrf: bTok, [`answer_${items[0].id}`]: 'hack' })).status, 404);
  assert.strictEqual((await b.req('GET', '/admin')).status, 403);

  // Photo upload (1x1 PNG) – visible to Ann and admin only.
  const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  const up = await a.req('POST', `/tests/${testId}/items/${items[0].id}/photos`, { image: png }, { 'content-type': 'application/json', 'x-csrf-token': tok });
  const { name } = JSON.parse(up.text);
  assert.ok(name);
  assert.strictEqual((await a.req('GET', `/uploads/${name}`)).status, 200);
  assert.strictEqual((await b.req('GET', `/uploads/${name}`)).status, 404);

  const answers = { _csrf: tok };
  for (const it of items) answers[`answer_${it.id}`] = 'My working: F = ma …';
  const sub = await a.req('POST', `/tests/${testId}/submit`, answers);
  assert.strictEqual(sub.location, `/tests/${testId}`);
  let t = db.get('SELECT * FROM tests WHERE id=?', testId);
  assert.strictEqual(t.status, 'submitted');
  // Answers are locked after submission.
  await a.req('POST', `/tests/${testId}/save`, { _csrf: tok, [`answer_${items[0].id}`]: 'changed' });
  assert.notStrictEqual(db.get('SELECT answer_text FROM test_items WHERE id=?', items[0].id).answer_text, 'changed');

  // Self-assessment gives a provisional score.
  await a.req('POST', `/tests/${testId}/self-assess`, { _csrf: tok, item: String(items[0].id), pt: '0' });
  t = db.get('SELECT * FROM tests WHERE id=?', testId);
  assert.ok(t.score > 0 && t.status === 'submitted');

  // Admin marks every item -> graded.
  const ad = client();
  const at = await ad.csrf('/login');
  await ad.req('POST', '/login', { _csrf: at, email: 'admin@example.com', password: 'admin1234' });
  const atok = (/name="csrf" content="([^"]+)"/.exec((await ad.req('GET', '/admin')).text))[1];
  assert.strictEqual((await ad.req('GET', `/uploads/${name}`)).status, 200);
  for (const it of items) await ad.req('POST', `/admin/tests/${testId}/grade`, { _csrf: atok, item: String(it.id), marks: String(it.max_marks), feedback: 'Well done' });
  t = db.get('SELECT * FROM tests WHERE id=?', testId);
  assert.strictEqual(t.status, 'graded');
  assert.strictEqual(t.score, 100);
  const adminView = await ad.req('GET', `/admin/students/${db.get("SELECT id FROM users WHERE email='ann@example.com'").id}`);
  assert.match(adminView.text, /Ann/);
});

test('password reset flow', async () => {
  const c = client();
  const tok = await c.csrf('/forgot');
  const r = await c.req('POST', '/forgot', { _csrf: tok, email: 'ann@example.com' });
  assert.match(r.text, /Check your email/);
  const mail = db.get("SELECT body FROM outbox WHERE to_email='ann@example.com' AND subject LIKE 'Reset%' ORDER BY id DESC").body;
  const link = /\/reset\?token=\S+/.exec(mail)[0];
  const token = link.split('=')[1];
  const t2 = await c.csrf(link);
  const done = await c.req('POST', '/reset', { _csrf: t2, token, password: 'newpass123', password2: 'newpass123' });
  assert.strictEqual(done.location, '/login?m=reset');
  // Token is single-use.
  const reuse = await c.req('POST', '/reset', { _csrf: t2, token, password: 'other1234', password2: 'other1234' });
  assert.strictEqual(reuse.status, 400);
  const t3 = await c.csrf('/login');
  const login = await c.req('POST', '/login', { _csrf: t3, email: 'ann@example.com', password: 'newpass123' });
  assert.strictEqual(login.location, '/dashboard');
});

test('theme is stored per user', async () => {
  const c = client();
  const t = await c.csrf('/login');
  await c.req('POST', '/login', { _csrf: t, email: 'ben@example.com', password: 'secret123' });
  const tok = (/name="csrf" content="([^"]+)"/.exec((await c.req('GET', '/settings')).text))[1];
  await c.req('POST', '/settings/theme', { _csrf: tok, theme: 'custom', custom_color: '#a1b2c3' });
  const page = await c.req('GET', '/dashboard');
  assert.match(page.text, /--accent:#a1b2c3/);
  const bad = await c.req('POST', '/settings/theme', { _csrf: tok, theme: 'custom', custom_color: 'red;}' }, { accept: 'application/json' });
  assert.strictEqual(bad.status, 400);
});
