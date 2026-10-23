'use strict';
const express = require('express');
const { html, raw } = require('../html');
const { layout, csrfField, fmtDate, scoreChip, bar, scoreChart } = require('../views/layout');
const { renderSectionBody } = require('../views/study');
const { takeView, reviewView } = require('../views/testview');
const T = require('../tests');
const A = require('../auth');
const { THEMES, HEX, themeColor } = require('../themes');

function requireUser(req, res, next) {
  if (!req.user) return res.redirect('/login');
  next();
}

module.exports = function studentRoutes(ctx) {
  const { db, config, grader } = ctx;
  const r = express.Router();
  r.use(requireUser);

  const send = (req, res, opts) => res.send(String(layout(req, opts)));
  const notFound = (req, res) => res.status(404).send(String(layout(req, { title: 'Not found', body: html`<div class="card"><h1>Not found</h1><p>That page does not exist or you do not have access to it.</p></div>` })));

  // Admin can see every subject; students only the ones they are enrolled in.
  function subjectsFor(user) {
    const hasContent = 'EXISTS (SELECT 1 FROM sections x WHERE x.subject_id=s.id AND x.active=1)';
    if (user.role === 'admin') return db.all(`SELECT s.* FROM subjects s WHERE s.active=1 AND ${hasContent} ORDER BY s.name`);
    return db.all(`SELECT s.* FROM subjects s JOIN enrollments e ON e.subject_id=s.id WHERE e.user_id=? AND s.active=1 AND ${hasContent} ORDER BY s.name`, user.id);
  }
  function canSee(user, subjectId) {
    if (user.role === 'admin') return !!db.get('SELECT 1 FROM subjects WHERE id=? AND active=1', subjectId);
    return !!db.get('SELECT 1 FROM enrollments e JOIN subjects s ON s.id=e.subject_id WHERE e.user_id=? AND e.subject_id=? AND s.active=1', user.id, subjectId);
  }
  function subjectProgress(userId, subjectId) {
    const total = db.get('SELECT COUNT(*) n FROM sections WHERE subject_id=? AND active=1', subjectId).n;
    const done = db.get(`SELECT COUNT(*) n FROM progress p JOIN sections s ON s.key=p.section_key
      WHERE p.user_id=? AND s.subject_id=? AND s.active=1 AND p.status='completed'`, userId, subjectId).n;
    return { total, done };
  }
  function availableTests(userId, subjectId) {
    return ['daily', 'weekly', 'monthly'].map((kind) => {
      const t = db.get('SELECT * FROM tests WHERE user_id=? AND subject_id=? AND kind=? AND period_key=?', userId, subjectId, kind, T.periodKey(kind));
      return { kind, test: t };
    });
  }
  function startButton(req, subjectId, kind, test) {
    const label = T.KINDS[kind].label;
    if (test && test.status === 'in_progress') return html`<a class="btn small" href="/tests/${test.id}">Continue ${label.toLowerCase()}</a>`;
    if (test) return html`<a class="btn ghost small" href="/tests/${test.id}">${label} done ✓</a>`;
    return html`<form method="post" action="/tests/new" style="display:inline">${csrfField(req)}<input type="hidden" name="subject" value="${subjectId}"><input type="hidden" name="kind" value="${kind}"><button class="small" type="submit">Start ${label.toLowerCase()}</button></form>`;
  }

  r.get('/dashboard', (req, res) => {
    if (req.user.role === 'admin') return res.redirect('/admin');
    const u = req.user;
    const subjects = subjectsFor(u);
    const stats = T.studentStats(db, u.id);
    const next = db.get(`SELECT s.* FROM sections s JOIN enrollments e ON e.subject_id=s.subject_id
      LEFT JOIN progress p ON p.section_key=s.key AND p.user_id=?
      WHERE e.user_id=? AND s.active=1 AND (p.status IS NULL OR p.status!='completed') ORDER BY p.updated_at IS NULL, p.updated_at DESC, s.sort LIMIT 1`, u.id, u.id);
    send(req, res, {
      title: 'Dashboard', active: 'dashboard',
      body: html`
      <div class="page-head"><div><h1>Hi ${u.name.split(' ')[0]} 👋</h1><p class="muted">Pick up where you left off, or take today's practice.</p></div></div>
      <div class="grid grid-4">
        <div class="card stat"><span class="num">${stats.streak}</span><span class="lbl">day study streak</span></div>
        <div class="card stat"><span class="num">${stats.completed}</span><span class="lbl">sections completed</span></div>
        <div class="card stat"><span class="num">${stats.done.length}</span><span class="lbl">tests completed</span></div>
        <div class="card stat"><span class="num">${stats.avg != null ? `${stats.avg.toFixed(0)}%` : '—'}</span><span class="lbl">average score</span></div>
      </div>
      ${next ? html`<div class="card tint" style="margin-top:1rem"><div class="row"><div><small class="muted">Continue studying</small><h3 style="margin:.2rem 0">${next.number} ${next.title}</h3></div><span class="spacer"></span><a class="btn" href="/study/${next.key}">Open section</a></div></div>` : ''}
      <h2>Your subjects</h2>
      ${subjects.length ? html`<div class="grid grid-2">${subjects.map((s) => {
    const p = subjectProgress(u.id, s.id);
    return html`<div class="card">
          <div class="row"><h3 style="margin:0">${s.name}</h3><span class="spacer"></span><small class="muted">${p.done}/${p.total} sections</small></div>
          <p class="muted">${s.description}</p>${bar(p.total ? p.done / p.total : 0)}
          <div class="form-actions"><a class="btn ghost small" href="/subjects/${s.id}">Study guide</a>
          ${availableTests(u.id, s.id).map((a) => startButton(req, s.id, a.kind, a.test))}</div>
        </div>`;
  })}</div>` : html`<div class="card"><p>You are not enrolled in any subjects yet. Your teacher will add you.</p></div>`}
      <h2>Recent tests</h2>
      ${testTable(stats.tests.slice(0, 6))}
      <div class="card" style="margin-top:1rem"><h3>Score trend</h3>${scoreChart(stats.tests)}</div>`,
    });
  });

  function testTable(tests, { showStudent = false } = {}) {
    if (!tests.length) return html`<p class="muted">No tests yet.</p>`;
    return html`<div class="card table-wrap"><table><thead><tr>${showStudent ? html`<th>Student</th>` : ''}<th>Test</th><th>Date</th><th>Score</th><th></th></tr></thead><tbody>
      ${tests.map((t) => html`<tr>${showStudent ? html`<td>${t.student_name}</td>` : ''}<td>${t.title}</td><td>${fmtDate(t.created_at)}</td><td>${scoreChip(t.score, t.status)}</td><td><a href="${showStudent ? '/admin' : ''}/tests/${t.id}">${t.status === 'in_progress' ? 'Continue' : 'Review'}</a></td></tr>`)}
    </tbody></table></div>`;
  }
  ctx.testTable = testTable;

  r.get('/subjects', (req, res) => {
    const subjects = subjectsFor(req.user);
    if (subjects.length === 1) return res.redirect(`/subjects/${subjects[0].id}`);
    send(req, res, {
      title: 'Subjects', active: 'subjects',
      body: html`<h1>Subjects</h1><div class="grid grid-2" style="margin-top:1rem">${subjects.map((s) => {
        const p = subjectProgress(req.user.id, s.id);
        return html`<a class="card" href="/subjects/${s.id}" style="text-decoration:none;color:inherit"><h3>${s.name}</h3><p class="muted">${s.description}</p>${bar(p.total ? p.done / p.total : 0)}</a>`;
      })}</div>${subjects.length ? '' : html`<p class="muted">No subjects yet.</p>`}`,
    });
  });

  r.get('/subjects/:sid', (req, res) => {
    const sid = req.params.sid;
    if (!canSee(req.user, sid)) return notFound(req, res);
    const subject = db.get('SELECT * FROM subjects WHERE id=?', sid);
    const sections = db.all(`SELECT s.*, p.status, p.updated_at AS seen,
      (SELECT COUNT(*) FROM questions q WHERE q.section_key=s.key AND q.active=1) AS qcount
      FROM sections s LEFT JOIN progress p ON p.section_key=s.key AND p.user_id=? WHERE s.subject_id=? AND s.active=1 ORDER BY s.sort`, req.user.id, sid);
    const mastery = T.sectionMastery(db, req.user.id, sid);
    const chapters = [];
    for (const s of sections) {
      let ch = chapters.find((c) => c.id === s.chapter_id);
      if (!ch) chapters.push(ch = { id: s.chapter_id, title: s.chapter_title, sections: [] });
      ch.sections.push(s);
    }
    const p = subjectProgress(req.user.id, sid);
    send(req, res, {
      title: subject.name, active: 'subjects',
      body: html`
      <div class="page-head"><div><h1>${subject.name}</h1><p class="muted">${subject.description}</p></div>
        <div style="min-width:220px"><small class="muted">${p.done} of ${p.total} sections complete</small>${bar(p.total ? p.done / p.total : 0)}</div></div>
      ${req.user.role !== 'admin' ? html`<div class="card tint row" style="margin-bottom:1rem"><strong>Tests</strong><span class="spacer"></span>${availableTests(req.user.id, sid).map((a) => startButton(req, sid, a.kind, a.test))}<a class="btn ghost small" href="/tests/new?subject=${sid}">Build your own</a></div>` : ''}
      ${chapters.map((ch) => html`<h2>${ch.title}</h2><div class="grid grid-3">${ch.sections.map((s) => {
        const m = mastery[s.key];
        return html`<a class="card" href="/study/${s.key}" style="text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:.4rem">
          <div class="row"><span class="chip accent">${s.number}</span>${s.status === 'completed' ? html`<span class="chip good">Completed</span>` : s.status ? html`<span class="chip warn">In progress</span>` : ''}</div>
          <h3 style="margin:.2rem 0">${s.title}</h3>
          <small class="muted">${s.minutes ? `~${s.minutes} min · ` : ''}${s.qcount} test questions</small>
          ${m ? html`<small class="muted">Mastery ${Math.round(m.mastery * 100)}%</small>${bar(m.mastery)}` : ''}
        </a>`;
      })}</div>`)}`,
    });
  });

  r.get('/study/:sid/:sec', (req, res) => {
    const key = `${req.params.sid}/${req.params.sec}`;
    const s = db.get('SELECT * FROM sections WHERE key=? AND active=1', key);
    if (!s || !canSee(req.user, s.subject_id)) return notFound(req, res);
    if (req.user.role !== 'admin') {
      db.run(`INSERT INTO progress (user_id, section_key) VALUES (?,?) ON CONFLICT(user_id, section_key) DO UPDATE SET updated_at=datetime('now')`, req.user.id, key);
    }
    const prog = db.get('SELECT * FROM progress WHERE user_id=? AND section_key=?', req.user.id, key) || {};
    const { toc, body } = renderSectionBody(key, s.data);
    const siblings = db.all('SELECT key, number, title FROM sections WHERE subject_id=? AND active=1 ORDER BY sort', s.subject_id);
    const idx = siblings.findIndex((x) => x.key === key);
    const prev = siblings[idx - 1]; const next = siblings[idx + 1];
    send(req, res, {
      title: `${s.number} ${s.title}`, active: 'subjects',
      body: html`
      <div class="page-head"><div><small class="muted"><a href="/subjects/${s.subject_id}">${s.chapter_title}</a></small><h1>${s.number} ${s.title}</h1>
        ${s.minutes ? html`<small class="muted">Estimated study time ~${s.minutes} minutes</small>` : ''}</div>
        ${prog.status === 'completed' ? html`<span class="chip good">Completed ${fmtDate(prog.completed_at)}</span>` : ''}</div>
      <div class="guide">
        <aside class="toc card no-print">${toc.map((t) => html`<a href="#${t.id}">${t.label}</a>`)}<a href="#notes">My notes</a></aside>
        <div data-section="${key}" data-practice-done="${prog.practice_done || '[]'}">
          ${body}
          ${req.user.role !== 'admin' ? html`<section id="notes" class="card lesson no-print"><h2>My notes</h2>
            <form method="post" action="/study/${key}/progress">${csrfField(req)}
              <textarea name="notes" rows="5" placeholder="Summarise the section in your own words, or note anything to ask your teacher.">${prog.notes || ''}</textarea>
              <div class="form-actions">
                <button type="submit" name="action" value="notes" class="ghost">Save notes</button>
                ${prog.status === 'completed'
    ? html`<button type="submit" name="action" value="reopen" class="ghost">Mark as not finished</button>`
    : html`<button type="submit" name="action" value="complete">Mark section complete</button>`}
                <a class="btn ghost" href="/tests/new?subject=${s.subject_id}&section=${encodeURIComponent(key)}">Test me on this section</a>
              </div>
            </form></section>` : ''}
          <div class="row no-print" style="margin-top:1rem">${prev ? html`<a class="btn ghost" href="/study/${prev.key}">← ${prev.number} ${prev.title}</a>` : ''}<span class="spacer"></span>${next ? html`<a class="btn ghost" href="/study/${next.key}">${next.number} ${next.title} →</a>` : ''}</div>
        </div>
      </div>`,
    });
  });

  r.post('/study/:sid/:sec/progress', (req, res) => {
    const key = `${req.params.sid}/${req.params.sec}`;
    const s = db.get('SELECT * FROM sections WHERE key=? AND active=1', key);
    if (!s || !canSee(req.user, s.subject_id) || req.user.role === 'admin') return notFound(req, res);
    db.run(`INSERT INTO progress (user_id, section_key) VALUES (?,?) ON CONFLICT DO NOTHING`, req.user.id, key);
    const notes = req.body.notes != null ? String(req.body.notes).slice(0, 20000) : null;
    if (notes != null) db.run(`UPDATE progress SET notes=?, updated_at=datetime('now') WHERE user_id=? AND section_key=?`, notes, req.user.id, key);
    if (req.body.action === 'complete') db.run(`UPDATE progress SET status='completed', completed_at=datetime('now'), updated_at=datetime('now') WHERE user_id=? AND section_key=?`, req.user.id, key);
    if (req.body.action === 'reopen') db.run(`UPDATE progress SET status='started', completed_at=NULL WHERE user_id=? AND section_key=?`, req.user.id, key);
    if (req.body.practice != null) {
      const arr = String(req.body.practice).split(',').map(Number).filter((n) => Number.isInteger(n) && n >= 0 && n < 200);
      db.run(`UPDATE progress SET practice_done=?, updated_at=datetime('now') WHERE user_id=? AND section_key=?`, JSON.stringify([...new Set(arr)]), req.user.id, key);
      return res.json({ ok: true });
    }
    res.redirect(req.body.action === 'complete' ? `/subjects/${s.subject_id}` : `/study/${key}#notes`);
  });

  // ---- Tests ----
  r.get('/tests', (req, res) => {
    if (req.user.role === 'admin') return res.redirect('/admin/review');
    const stats = T.studentStats(db, req.user.id);
    const subjects = subjectsFor(req.user);
    send(req, res, {
      title: 'Tests', active: 'tests',
      body: html`
      <div class="page-head"><div><h1>Tests</h1><p class="muted">Daily practice resets every day, weekly tests every Monday and the monthly exam on the 1st.</p></div><a class="btn" href="/tests/new">Build an on-demand test</a></div>
      <div class="grid grid-2">${subjects.map((s) => html`<div class="card"><h3>${s.name}</h3>
        <div class="grid" style="gap:.6rem">${availableTests(req.user.id, s.id).map((a) => html`<div class="row"><div><strong>${T.KINDS[a.kind].label}</strong><br><small class="muted">${T.KINDS[a.kind].count} questions · ${T.KINDS[a.kind].minutes} min</small></div><span class="spacer"></span>${startButton(req, s.id, a.kind, a.test)}</div>`)}</div></div>`)}</div>
      <h2>History</h2>${testTable(stats.tests)}`,
    });
  });

  r.get('/tests/new', (req, res) => {
    if (req.user.role === 'admin') return res.redirect('/admin');
    const subjects = subjectsFor(req.user);
    const subjectId = subjects.some((s) => s.id === req.query.subject) ? req.query.subject : subjects[0] && subjects[0].id;
    if (!subjectId) return res.redirect('/dashboard');
    const sections = db.all(`SELECT s.key, s.number, s.title, (SELECT COUNT(*) FROM questions q WHERE q.section_key=s.key AND q.active=1) n
      FROM sections s WHERE s.subject_id=? AND s.active=1 ORDER BY s.sort`, subjectId);
    const preselect = req.query.section ? [String(req.query.section)] : [];
    send(req, res, {
      title: 'New test', active: 'tests',
      body: html`<h1>Build an on-demand test</h1>
      <form method="get" action="/tests/new" class="row" style="margin:.5rem 0 1rem">${subjects.length > 1 ? html`<select name="subject" onchange="this.form.submit()">${subjects.map((s) => html`<option value="${s.id}" ${s.id === subjectId ? 'selected' : ''}>${s.name}</option>`)}</select>` : ''}</form>
      <form method="post" action="/tests/new" class="card">
        ${csrfField(req)}<input type="hidden" name="subject" value="${subjectId}"><input type="hidden" name="kind" value="ondemand">
        <h3>Topics</h3>
        <div class="grid grid-2" style="gap:.2rem 1rem">${sections.map((s) => html`<label class="check"><input type="checkbox" name="sections" value="${s.key}" ${preselect.includes(s.key) ? 'checked' : ''} ${s.n ? '' : 'disabled'}> <span>${s.number} ${s.title} <small class="muted">(${s.n})</small></span></label>`)}</div>
        <small class="muted">Leave all unticked to include every topic.</small>
        <div class="grid grid-3">
          <div><label for="count">Number of questions</label><input id="count" type="number" name="count" min="1" max="20" value="6"></div>
          <div><label for="minutes">Time limit (minutes, 0 = untimed)</label><input id="minutes" type="number" name="minutes" min="0" max="240" value="45"></div>
          <div><label>Difficulty</label>
            <label class="check"><input type="checkbox" name="difficulty" value="1" checked> Foundation</label>
            <label class="check"><input type="checkbox" name="difficulty" value="2" checked> Standard</label>
            <label class="check"><input type="checkbox" name="difficulty" value="3" checked> Challenge</label></div>
        </div>
        <div class="form-actions"><button type="submit">Start test</button></div>
      </form>`,
    });
  });

  const arr = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);

  r.post('/tests/new', (req, res) => {
    if (req.user.role === 'admin') return res.redirect('/admin');
    const subjectId = String(req.body.subject || '');
    const kind = String(req.body.kind || '');
    if (!canSee(req.user, subjectId) || !T.KINDS[kind]) return notFound(req, res);
    try {
      const id = T.createTest(db, {
        userId: req.user.id, subjectId, kind,
        sectionKeys: arr(req.body.sections).map(String),
        count: Number(req.body.count) || undefined,
        minutes: req.body.minutes != null && req.body.minutes !== '' ? Number(req.body.minutes) : undefined,
        difficulty: arr(req.body.difficulty).map(Number).filter((d) => [1, 2, 3].includes(d)),
      });
      res.redirect(`/tests/${id}`);
    } catch (e) {
      send(req, res, { title: 'Test', active: 'tests', body: html`<div class="card"><h1>Could not create the test</h1><p>${e.message}</p><a class="btn" href="/tests">Back</a></div>` });
    }
  });

  function ownTest(req) {
    const t = db.get('SELECT * FROM tests WHERE id=?', Number(req.params.id));
    if (!t || t.user_id !== req.user.id) return null;
    return t;
  }

  r.get('/tests/:id', (req, res) => {
    if (req.user.role === 'admin') return res.redirect(`/admin/tests/${req.params.id}`);
    const t = ownTest(req);
    if (!t) return notFound(req, res);
    const items = db.all('SELECT * FROM test_items WHERE test_id=? ORDER BY position', t.id);
    const body = t.status === 'in_progress' ? takeView(req, db, t, items) : reviewView(req, db, t, items);
    send(req, res, { title: t.title, active: 'tests', body });
  });

  r.post('/tests/:id/save', (req, res) => {
    const t = ownTest(req);
    if (!t) return res.status(404).json({ ok: false });
    const ok = T.saveAnswers(db, t, req.body);
    res.json({ ok, savedAt: new Date().toISOString() });
  });

  r.post('/tests/:id/submit', (req, res) => {
    const t = ownTest(req);
    if (!t) return notFound(req, res);
    if (T.submitTest(db, t, req.body) && config.anthropicKey) {
      grader.gradeTest(db, config, t.id).catch((e) => console.error('[grader]', e.message));
    }
    res.redirect(`/tests/${t.id}`);
  });

  r.post('/tests/:id/self-assess', (req, res) => {
    const t = ownTest(req);
    if (!t || t.status === 'in_progress') return notFound(req, res);
    const it = db.get('SELECT * FROM test_items WHERE id=? AND test_id=?', Number(req.body.item), t.id);
    if (!it || it.admin_marks != null || it.ai_marks != null) return res.redirect(`/tests/${t.id}`);
    const rubric = T.renderItem(db, it).rubric;
    const pts = arr(req.body.pt).map(Number).filter((i) => Number.isInteger(i) && i >= 0 && i < rubric.length);
    const marks = Math.min(it.max_marks, pts.reduce((s, i) => s + rubric[i].marks, 0));
    db.run('UPDATE test_items SET self_marks=?, self_points=? WHERE id=?', marks, JSON.stringify([...new Set(pts)]), it.id);
    T.refreshTestScore(db, t.id);
    res.redirect(`/tests/${t.id}#item-${it.id}`);
  });

  // ---- Photos of handwritten working ----
  const fs = require('fs');
  const path = require('path');
  const crypto = require('crypto');
  const MAX_PHOTOS = 4;
  const ownItem = (req) => {
    const t = ownTest(req);
    if (!t) return {};
    const it = db.get('SELECT * FROM test_items WHERE id=? AND test_id=?', Number(req.params.itemId), t.id);
    return { t, it };
  };

  r.post('/tests/:id/items/:itemId/photos', (req, res) => {
    const { t, it } = ownItem(req);
    if (!it || t.status !== 'in_progress') return res.status(404).json({ ok: false, error: 'Not found' });
    const m = /^data:image\/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$/.exec(String(req.body.image || ''));
    if (!m) return res.status(400).json({ ok: false, error: 'Upload a JPEG, PNG or WebP image.' });
    const buf = Buffer.from(m[2], 'base64');
    if (buf.length > 4 * 1024 * 1024) return res.status(400).json({ ok: false, error: 'That photo is too large (max 4 MB).' });
    const photos = T.parseJSON(it.attachments, []);
    if (photos.length >= MAX_PHOTOS) return res.status(400).json({ ok: false, error: `Up to ${MAX_PHOTOS} photos per question.` });
    const name = `${crypto.randomBytes(16).toString('hex')}.${m[1] === 'jpeg' ? 'jpg' : m[1]}`;
    fs.mkdirSync(config.uploadsDir, { recursive: true });
    fs.writeFileSync(path.join(config.uploadsDir, name), buf);
    photos.push(name);
    db.run('UPDATE test_items SET attachments=? WHERE id=?', JSON.stringify(photos), it.id);
    res.json({ ok: true, name });
  });

  r.post('/tests/:id/items/:itemId/photos/delete', (req, res) => {
    const { t, it } = ownItem(req);
    if (!it || t.status !== 'in_progress') return res.status(404).json({ ok: false });
    const name = String(req.body.name || '');
    const photos = T.parseJSON(it.attachments, []);
    if (!photos.includes(name)) return res.status(404).json({ ok: false });
    db.run('UPDATE test_items SET attachments=? WHERE id=?', JSON.stringify(photos.filter((p) => p !== name)), it.id);
    fs.rm(path.join(config.uploadsDir, name), { force: true }, () => {});
    res.json({ ok: true });
  });

  // Photos are only visible to the student who took the test and the admin.
  r.get('/uploads/:name', (req, res) => {
    const name = req.params.name;
    if (!/^[a-f0-9]{32}\.(jpg|png|webp)$/.test(name)) return notFound(req, res);
    const row = db.get(`SELECT t.user_id FROM test_items ti JOIN tests t ON t.id=ti.test_id WHERE ti.attachments LIKE ?`, `%"${name}"%`);
    if (!row || (row.user_id !== req.user.id && req.user.role !== 'admin')) return notFound(req, res);
    res.set('Cache-Control', 'private, max-age=86400');
    res.sendFile(path.join(config.uploadsDir, name));
  });

  // ---- Progress ----
  r.get('/progress', (req, res) => {
    if (req.user.role === 'admin') return res.redirect('/admin/students');
    send(req, res, { title: 'Progress', active: 'progress', body: ctx.progressView(req, req.user) });
  });

  ctx.progressView = (req, user) => {
    const stats = T.studentStats(db, user.id);
    const subjects = user.role === 'admin' ? [] : db.all('SELECT s.* FROM subjects s JOIN enrollments e ON e.subject_id=s.id WHERE e.user_id=? AND s.active=1', user.id);
    const byKind = Object.keys(T.KINDS).map((k) => {
      const d = stats.done.filter((t) => t.kind === k);
      return { k, n: d.length, avg: d.length ? d.reduce((s, t) => s + t.score, 0) / d.length : null };
    });
    return html`
      <div class="page-head"><div><h1>${req.user.id === user.id ? 'Your progress' : `${user.name}'s progress`}</h1><p class="muted">${user.email} · joined ${fmtDate(user.created_at)}${user.last_login ? html` · last sign-in ${fmtDate(user.last_login, true)}` : ''}</p></div></div>
      <div class="grid grid-4">
        <div class="card stat"><span class="num">${stats.streak}</span><span class="lbl">day streak</span></div>
        <div class="card stat"><span class="num">${stats.completed}</span><span class="lbl">sections completed</span></div>
        <div class="card stat"><span class="num">${stats.done.length}</span><span class="lbl">tests completed</span></div>
        <div class="card stat"><span class="num">${stats.avg != null ? `${stats.avg.toFixed(0)}%` : '—'}</span><span class="lbl">average score</span></div>
      </div>
      <div class="grid grid-2" style="margin-top:1rem">
        <div class="card"><h3>Score trend</h3>${scoreChart(stats.tests)}</div>
        <div class="card"><h3>By test type</h3><table><tbody>${byKind.map((b) => html`<tr><td>${T.KINDS[b.k].label}</td><td>${b.n} taken</td><td>${b.avg != null ? `${b.avg.toFixed(0)}%` : '—'}</td></tr>`)}</tbody></table></div>
      </div>
      ${subjects.map((s) => {
    const sections = db.all(`SELECT s.*, p.status, p.updated_at AS seen FROM sections s LEFT JOIN progress p ON p.section_key=s.key AND p.user_id=? WHERE s.subject_id=? AND s.active=1 ORDER BY s.sort`, user.id, s.id);
    const m = T.sectionMastery(db, user.id, s.id);
    const weak = sections.filter((x) => m[x.key] && m[x.key].mastery < 0.6);
    return html`<h2>${s.name}</h2>
        ${weak.length ? html`<div class="alert warn">Focus next on: ${weak.map((w, i) => html`${i ? ', ' : ''}<a href="/study/${w.key}">${w.number} ${w.title}</a>`)}</div>` : ''}
        <div class="card table-wrap"><table><thead><tr><th>Section</th><th>Study</th><th>Mastery</th><th>Questions marked</th></tr></thead><tbody>
        ${sections.map((x) => html`<tr><td>${x.number} ${x.title}</td><td>${x.status === 'completed' ? html`<span class="chip good">Completed</span>` : x.status ? html`<span class="chip warn">Started</span>` : html`<span class="chip">Not started</span>`}</td>
          <td style="min-width:140px">${m[x.key] ? html`${Math.round(m[x.key].mastery * 100)}% ${bar(m[x.key].mastery)}` : '—'}</td><td>${m[x.key] ? m[x.key].attempts : 0}</td></tr>`)}
        </tbody></table></div>`;
  })}
      <h2>All tests</h2>${testTable(stats.tests, {})}`;
  };

  // ---- Settings (theme is stored per user, so it follows them to any device) ----
  r.get('/settings', (req, res) => {
    const u = req.user;
    const flash = { saved: { type: 'ok', text: 'Saved.' }, pw: { type: 'ok', text: 'Password changed.' }, bad: { type: 'err', text: req.query.e || 'Could not save.' } }[req.query.m];
    send(req, res, {
      title: 'Settings', active: 'settings', flash,
      body: html`<h1>Settings</h1>
      <div class="grid grid-2" style="margin-top:1rem;align-items:start">
        <form class="card" method="post" action="/settings/theme" id="theme-form">${csrfField(req)}
          <h3>Colour theme</h3><p class="muted">Your theme is saved to your account and follows you to any device.</p>
          <div class="swatches">
            ${THEMES.map((t) => html`<label class="swatch ${u.theme === t.id ? 'selected' : ''}"><input type="radio" name="theme" value="${t.id}" data-color="${t.color}" ${u.theme === t.id ? 'checked' : ''}><span class="dot" style="background:${t.color}"></span>${t.name}</label>`)}
            <label class="swatch ${u.theme === 'custom' ? 'selected' : ''}"><input type="radio" name="theme" value="custom" data-color="${u.custom_color || '#cfe3d4'}" ${u.theme === 'custom' ? 'checked' : ''}><span class="dot" id="custom-dot" style="background:${u.custom_color || '#cfe3d4'}"></span>Custom</label>
          </div>
          <label for="custom_color">Custom colour</label>
          <div class="row"><input type="color" id="custom_color" name="custom_color" value="${u.custom_color || '#cfe3d4'}" style="width:64px;height:44px;border:0;background:none;padding:0"><small class="muted">Pick any colour — lighter shades work best.</small></div>
          <div class="form-actions"><button type="submit">Save theme</button><span class="muted theme-status"></span></div>
        </form>
        <div class="grid">
          <form class="card" method="post" action="/settings/profile">${csrfField(req)}
            <h3>Profile</h3>
            <label for="name">Name</label><input id="name" type="text" name="name" value="${u.name}" maxlength="80" required>
            <label>Email</label><input type="email" value="${u.email}" disabled>
            <div class="form-actions"><button type="submit" class="ghost">Save profile</button></div>
          </form>
          <form class="card" method="post" action="/settings/password">${csrfField(req)}
            <h3>Change password</h3>
            <label for="current">Current password</label><input id="current" type="password" name="current" required autocomplete="current-password">
            <label for="password">New password</label><input id="password" type="password" name="password" required minlength="8" autocomplete="new-password">
            <label for="password2">Confirm new password</label><input id="password2" type="password" name="password2" required minlength="8" autocomplete="new-password">
            <div class="form-actions"><button type="submit" class="ghost">Change password</button><a href="/forgot">Forgot it?</a></div>
          </form>
        </div>
      </div>`,
    });
  });

  r.post('/settings/theme', (req, res) => {
    const theme = String(req.body.theme || '');
    const custom = String(req.body.custom_color || '');
    if (theme !== 'custom' && !THEMES.some((t) => t.id === theme)) return res.status(400).json({ ok: false });
    if (theme === 'custom' && !HEX.test(custom)) return res.status(400).json({ ok: false });
    db.run('UPDATE users SET theme=?, custom_color=COALESCE(?, custom_color) WHERE id=?', theme, HEX.test(custom) ? custom : null, req.user.id);
    const u = db.get('SELECT * FROM users WHERE id=?', req.user.id);
    if (req.get('accept') && req.get('accept').includes('application/json')) return res.json({ ok: true, color: themeColor(u) });
    res.redirect('/settings?m=saved');
  });

  r.post('/settings/profile', (req, res) => {
    const name = String(req.body.name || '').trim().slice(0, 80);
    if (name) db.run('UPDATE users SET name=? WHERE id=?', name, req.user.id);
    res.redirect('/settings?m=saved');
  });

  r.post('/settings/password', (req, res) => {
    const pw = String(req.body.password || '');
    const bad = (e) => res.redirect(`/settings?m=bad&e=${encodeURIComponent(e)}`);
    if (!A.verifyPassword(String(req.body.current || ''), req.user.password_hash)) return bad('Your current password is not correct.');
    const problem = A.passwordProblem(pw) || (pw !== req.body.password2 ? 'The two passwords do not match.' : null);
    if (problem) return bad(problem);
    db.run('UPDATE users SET password_hash=? WHERE id=?', A.hashPassword(pw), req.user.id);
    A.endAllSessions(db, req.user.id);
    A.startSession(db, res, req.user.id, config.secureCookies);
    res.redirect('/settings?m=pw');
  });

  return r;
};

module.exports.requireUser = requireUser;
