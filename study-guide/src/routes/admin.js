'use strict';
const express = require('express');
const fs = require('fs');
const path = require('path');
const { html, raw } = require('../html');
const { layout, csrfField, fmtDate, scoreChip } = require('../views/layout');
const { reviewView, TYPE_LABEL, DIFF_LABEL } = require('../views/testview');
const { renderMarkdown: md, syncContent } = require('../content');
const { buildScope, fill } = require('../expr');
const T = require('../tests');
const A = require('../auth');

module.exports = function adminRoutes(ctx) {
  const { db, config, mailer, grader } = ctx;
  const r = express.Router();
  r.use((req, res, next) => {
    if (!req.user) return res.redirect('/login');
    if (req.user.role !== 'admin') return res.status(403).send(String(layout(req, { title: 'No access', body: html`<div class="card"><h1>Teachers only</h1><p>This area is only for the admin.</p></div>` })));
    next();
  });
  const send = (req, res, opts) => res.send(String(layout(req, opts)));
  const flashFrom = (q) => (q.ok ? { type: 'ok', text: q.ok } : q.err ? { type: 'err', text: q.err } : null);
  const back = (res, url, msg, kind = 'ok') => res.redirect(`${url}${url.includes('?') ? '&' : '?'}${kind}=${encodeURIComponent(msg)}`);

  function studentRows() {
    return db.all(`SELECT u.*,
      (SELECT COUNT(*) FROM tests t WHERE t.user_id=u.id AND t.status!='in_progress') AS tests_done,
      (SELECT AVG(score) FROM tests t WHERE t.user_id=u.id AND t.score IS NOT NULL AND t.status!='in_progress') AS avg_score,
      (SELECT COUNT(*) FROM tests t WHERE t.user_id=u.id AND t.status='submitted') AS pending,
      (SELECT COUNT(*) FROM progress p WHERE p.user_id=u.id AND p.status='completed') AS sections_done,
      (SELECT MAX(x) FROM (SELECT MAX(updated_at) x FROM progress WHERE user_id=u.id UNION SELECT MAX(created_at) FROM tests WHERE user_id=u.id)) AS last_activity
      FROM users u WHERE u.role='student' ORDER BY u.name`);
  }

  r.get('/', (req, res) => {
    const students = studentRows();
    const pending = db.get("SELECT COUNT(*) n FROM tests WHERE status='submitted'").n;
    const week = db.get("SELECT COUNT(*) n FROM tests WHERE submitted_at >= datetime('now','-7 days')").n;
    const qcount = db.get('SELECT COUNT(*) n FROM questions WHERE active=1').n;
    const recent = db.all(`SELECT t.*, u.name AS student_name FROM tests t JOIN users u ON u.id=t.user_id WHERE t.status!='in_progress' ORDER BY t.submitted_at DESC LIMIT 10`);
    send(req, res, {
      title: 'Admin', active: 'admin', flash: flashFrom(req.query),
      body: html`
      <div class="page-head"><div><h1>Teacher overview</h1><p class="muted">Every student's history is visible only to them and to you.</p></div><a class="btn" href="/admin/review">Marking queue (${pending})</a></div>
      ${!mailer.configured ? html`<div class="alert warn">Email is not configured, so confirmation and reset links are not being delivered. They are kept in the <a href="/admin/outbox">outbox</a>; set SMTP settings in <code>.env</code> to send them.</div>` : ''}
      ${!config.anthropicKey ? html`<div class="alert">AI marking is off. Students self-assess against the rubric and you confirm marks in the queue. Set <code>ANTHROPIC_API_KEY</code> to turn on automatic rubric marking.</div>` : ''}
      <div class="grid grid-4">
        <div class="card stat"><span class="num">${students.length}</span><span class="lbl">students</span></div>
        <div class="card stat"><span class="num">${week}</span><span class="lbl">tests in the last 7 days</span></div>
        <div class="card stat"><span class="num">${pending}</span><span class="lbl">tests awaiting final marks</span></div>
        <div class="card stat"><span class="num">${qcount}</span><span class="lbl">questions in the bank</span></div>
      </div>
      <h2>Students</h2>${studentTable(students)}
      <h2>Latest submissions</h2>${ctx.testTable(recent, { showStudent: true })}`,
    });
  });

  function studentTable(students) {
    if (!students.length) return html`<div class="card"><p>No students yet. <a href="/admin/students">Invite students</a> or share the registration link: <code>${config.appUrl}/register</code></p></div>`;
    return html`<div class="card table-wrap"><table><thead><tr><th>Student</th><th>Sections done</th><th>Tests</th><th>Average</th><th>Last active</th><th></th></tr></thead><tbody>
      ${students.map((s) => html`<tr><td><a href="/admin/students/${s.id}">${s.name}</a><br><small class="muted">${s.email}</small>${!s.email_verified ? html` <span class="chip warn">unconfirmed</span>` : ''}${!s.active ? html` <span class="chip bad">disabled</span>` : ''}</td>
        <td>${s.sections_done}</td><td>${s.tests_done}${s.pending ? html` <span class="chip warn">${s.pending} to mark</span>` : ''}</td>
        <td>${s.avg_score != null ? scoreChip(s.avg_score, 'graded') : '—'}</td><td>${fmtDate(s.last_activity, true) || '—'}</td><td><a href="/admin/students/${s.id}">Open</a></td></tr>`)}
    </tbody></table></div>`;
  }

  r.get('/review', (req, res) => {
    const tests = db.all(`SELECT t.*, u.name AS student_name FROM tests t JOIN users u ON u.id=t.user_id WHERE t.status='submitted' ORDER BY t.submitted_at`);
    send(req, res, {
      title: 'Marking queue', active: 'review', flash: flashFrom(req.query),
      body: html`<h1>Marking queue</h1><p class="muted">Submitted tests that still need an official mark on at least one answer. Oldest first.</p>${ctx.testTable(tests, { showStudent: true })}`,
    });
  });

  const getTest = (id) => db.get('SELECT * FROM tests WHERE id=?', Number(id));

  r.get('/tests/:id', (req, res) => {
    const t = getTest(req.params.id);
    if (!t) return res.status(404).send('Not found');
    const student = db.get('SELECT * FROM users WHERE id=?', t.user_id);
    const items = db.all('SELECT * FROM test_items WHERE test_id=? ORDER BY position', t.id);
    if (t.status === 'in_progress') {
      return send(req, res, { title: t.title, active: 'review', body: html`<div class="card"><h1>${t.title}</h1><p>${student.name} started this test ${fmtDate(t.created_at, true)} and has not submitted it yet.</p><form method="post" action="/admin/tests/${t.id}/delete">${csrfField(req)}<button class="danger small" data-confirm="Delete this unfinished test?">Delete unfinished test</button></form></div>` });
    }
    send(req, res, {
      title: t.title, active: 'review', flash: flashFrom(req.query),
      body: html`${reviewView(req, db, t, items, { admin: true, student })}
      <div class="row no-print">${config.anthropicKey ? html`<form method="post" action="/admin/tests/${t.id}/ai">${csrfField(req)}<button class="ghost small">Run AI marking on unmarked answers</button></form>` : ''}
      <form method="post" action="/admin/tests/${t.id}/delete">${csrfField(req)}<button class="danger small" data-confirm="Delete this test and its answers permanently?">Delete test</button></form></div>`,
    });
  });

  r.post('/tests/:id/grade', (req, res) => {
    const t = getTest(req.params.id);
    if (!t) return res.status(404).send('Not found');
    const it = db.get('SELECT * FROM test_items WHERE id=? AND test_id=?', Number(req.body.item), t.id);
    if (!it) return res.status(404).send('Not found');
    const marks = Math.max(0, Math.min(it.max_marks, Math.round(Number(req.body.marks) * 2) / 2));
    if (!Number.isFinite(marks)) return back(res, `/admin/tests/${t.id}`, 'Enter a number of marks.', 'err');
    db.run("UPDATE test_items SET admin_marks=?, admin_feedback=?, graded_at=datetime('now') WHERE id=?", marks, String(req.body.feedback || '').slice(0, 5000) || null, it.id);
    T.refreshTestScore(db, t.id);
    res.redirect(`/admin/tests/${t.id}#item-${it.id}`);
  });

  r.post('/tests/:id/accept', (req, res) => {
    const t = getTest(req.params.id);
    if (!t) return res.status(404).send('Not found');
    db.run(`UPDATE test_items SET admin_marks=COALESCE(ai_marks, self_marks, 0), graded_at=datetime('now')
      WHERE test_id=? AND admin_marks IS NULL AND ai_marks IS NULL`, t.id);
    T.refreshTestScore(db, t.id);
    back(res, `/admin/tests/${t.id}`, 'Marks accepted.');
  });

  r.post('/tests/:id/ai', async (req, res) => {
    const t = getTest(req.params.id);
    if (!t) return res.status(404).send('Not found');
    await grader.gradeTest(db, config, t.id);
    back(res, `/admin/tests/${t.id}`, 'AI marking finished.');
  });

  r.post('/tests/:id/delete', (req, res) => {
    const t = getTest(req.params.id);
    if (t) db.run('DELETE FROM tests WHERE id=?', t.id);
    back(res, t ? `/admin/students/${t.user_id}` : '/admin', 'Test deleted.');
  });

  // ---- Students ----
  r.get('/students', (req, res) => {
    send(req, res, {
      title: 'Students', active: 'students', flash: flashFrom(req.query),
      body: html`<div class="page-head"><h1>Students</h1></div>
      <form class="card" method="post" action="/admin/students/invite" style="margin-bottom:1rem">${csrfField(req)}
        <h3>Invite students</h3><p class="muted">Enter one email per line. Each person gets a link to set their name and password (valid 7 days).${config.registration === 'open' ? html` Students can also register themselves at <code>${config.appUrl}/register</code>.` : ''}</p>
        <textarea name="emails" rows="3" placeholder="student1@example.com&#10;student2@example.com" style="min-height:80px"></textarea>
        <div class="form-actions"><button type="submit">Send invites</button></div>
      </form>
      ${studentTable(studentRows())}`,
    });
  });

  r.post('/students/invite', async (req, res) => {
    const emails = String(req.body.emails || '').split(/[\s,;]+/).map((e) => e.trim().toLowerCase()).filter((e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));
    let sent = 0;
    for (const email of [...new Set(emails)].slice(0, 200)) {
      const existing = db.get('SELECT * FROM users WHERE email=?', email);
      if (existing && existing.password_hash) continue;
      const token = A.createToken(db, { email, type: 'invite', hours: 24 * 7 });
      await mailer.send(email, 'You are invited to the Study Guide',
        `Hello,\n\nYou have been invited to join the Study Guide. Create your account here:\n${config.appUrl}/register?invite=${token}\n\nThis link expires in 7 days.`);
      sent++;
    }
    back(res, '/admin/students', `${sent} invite${sent === 1 ? '' : 's'} sent.${mailer.configured ? '' : ' (Email is not configured — copy the links from the outbox.)'}`);
  });

  const getStudent = (id) => db.get("SELECT * FROM users WHERE id=? AND role='student'", Number(id));

  r.get('/students/:id', (req, res) => {
    const u = getStudent(req.params.id);
    if (!u) return res.status(404).send('Not found');
    const subjects = db.all('SELECT s.*, e.user_id AS enrolled FROM subjects s LEFT JOIN enrollments e ON e.subject_id=s.id AND e.user_id=? WHERE s.active=1 ORDER BY s.name', u.id);
    send(req, res, {
      title: u.name, active: 'students', flash: flashFrom(req.query),
      body: html`${ctx.progressView(req, u)}
      <h2>Account</h2>
      <div class="grid grid-2">
        <form class="card" method="post" action="/admin/students/${u.id}/enroll">${csrfField(req)}
          <h3>Subjects</h3>${subjects.map((s) => html`<label class="check"><input type="checkbox" name="subjects" value="${s.id}" ${s.enrolled ? 'checked' : ''}> ${s.name}</label>`)}
          <div class="form-actions"><button class="small" type="submit">Save subjects</button></div>
        </form>
        <div class="card"><h3>Actions</h3><div class="grid" style="gap:.5rem">
          ${!u.email_verified ? html`<form method="post" action="/admin/students/${u.id}/verify">${csrfField(req)}<button class="ghost small">Confirm email manually</button></form>` : ''}
          <form method="post" action="/admin/students/${u.id}/reset">${csrfField(req)}<button class="ghost small">Email a password reset link</button></form>
          <form method="post" action="/admin/students/${u.id}/toggle">${csrfField(req)}<button class="${u.active ? 'danger' : ''} small">${u.active ? 'Disable account' : 'Re-enable account'}</button></form>
          <form method="post" action="/admin/students/${u.id}/delete">${csrfField(req)}<button class="danger small" data-confirm="Permanently delete ${u.name} and all their history? This cannot be undone.">Delete student and history</button></form>
        </div></div>
      </div>`,
    });
  });

  r.post('/students/:id/enroll', (req, res) => {
    const u = getStudent(req.params.id);
    if (!u) return res.status(404).send('Not found');
    const chosen = new Set([].concat(req.body.subjects || []).map(String));
    db.tx(() => {
      db.run('DELETE FROM enrollments WHERE user_id=?', u.id);
      for (const s of db.all('SELECT id FROM subjects WHERE active=1')) if (chosen.has(s.id)) db.run('INSERT INTO enrollments (user_id, subject_id) VALUES (?,?)', u.id, s.id);
    });
    back(res, `/admin/students/${u.id}`, 'Subjects updated.');
  });
  r.post('/students/:id/verify', (req, res) => {
    const u = getStudent(req.params.id);
    if (u) db.run('UPDATE users SET email_verified=1 WHERE id=?', u.id);
    back(res, `/admin/students/${req.params.id}`, 'Email confirmed.');
  });
  r.post('/students/:id/reset', async (req, res) => {
    const u = getStudent(req.params.id);
    if (!u) return res.status(404).send('Not found');
    const token = A.createToken(db, { userId: u.id, type: 'reset', hours: 24 });
    await mailer.send(u.email, 'Reset your Study Guide password', `Hi ${u.name},\n\nYour teacher sent you a link to set a new password:\n${config.appUrl}/reset?token=${token}\n\nThe link expires in 24 hours.`);
    back(res, `/admin/students/${u.id}`, 'Reset link sent.');
  });
  r.post('/students/:id/toggle', (req, res) => {
    const u = getStudent(req.params.id);
    if (!u) return res.status(404).send('Not found');
    db.run('UPDATE users SET active=? WHERE id=?', u.active ? 0 : 1, u.id);
    if (u.active) A.endAllSessions(db, u.id);
    back(res, `/admin/students/${u.id}`, u.active ? 'Account disabled.' : 'Account re-enabled.');
  });
  r.post('/students/:id/delete', (req, res) => {
    const u = getStudent(req.params.id);
    if (u) db.run('DELETE FROM users WHERE id=?', u.id);
    back(res, '/admin/students', 'Student deleted.');
  });

  // ---- Content ----
  r.get('/content', (req, res) => {
    const subjects = db.all('SELECT * FROM subjects ORDER BY name');
    send(req, res, {
      title: 'Content', active: 'content', flash: flashFrom(req.query),
      body: html`<div class="page-head"><div><h1>Content</h1><p class="muted">Study material lives in <code>content/&lt;subject&gt;/</code> as JSON. See <code>docs/CONTENT_FORMAT.md</code>.</p></div>
        <form method="post" action="/admin/content/reload">${csrfField(req)}<button type="submit">Reload content from disk</button></form></div>
      ${subjects.map((s) => {
    const secs = db.all(`SELECT s.*, (SELECT COUNT(*) FROM questions q WHERE q.section_key=s.key AND q.active=1) n FROM sections s WHERE s.subject_id=? ORDER BY s.sort`, s.id);
    return html`<div class="card" style="margin-bottom:1rem"><div class="row"><h3 style="margin:0">${s.name}</h3><code>${s.id}</code>${s.active ? '' : html`<span class="chip bad">retired</span>`}</div>
          <div class="table-wrap"><table><thead><tr><th>Section</th><th>Title</th><th>Questions</th><th></th></tr></thead><tbody>
          ${secs.map((x) => html`<tr><td>${x.number}</td><td>${x.title}${x.active ? '' : html` <span class="chip bad">retired</span>`}</td><td>${x.n}</td><td><a href="/study/${x.key}">Guide</a> · <a href="/admin/questions/${x.key}">Questions</a></td></tr>`)}
          </tbody></table></div></div>`;
  })}
      <form class="card" method="post" action="/admin/content/upload">${csrfField(req)}
        <h3>Upload a section or subject file</h3>
        <p class="muted">Paste or choose a <code>subject.json</code> or a section JSON file. A new section must also be listed in its subject's <code>chapters[].sections</code>.</p>
        <div class="grid grid-2"><div><label for="subject_id">Subject id</label><input id="subject_id" name="subject_id" type="text" placeholder="physics-11" required pattern="[a-z0-9-]+"></div>
        <div><label for="file_name">File</label><input id="file_name" name="file_name" type="text" placeholder="subject.json or 4-7.json" required pattern="[A-Za-z0-9._-]+\\.json"></div></div>
        <label for="json">JSON</label><input type="file" accept="application/json,.json" data-fill="#json"><textarea id="json" name="json" rows="8" required></textarea>
        <div class="form-actions"><button type="submit">Save and reload</button></div>
      </form>`,
    });
  });

  r.post('/content/reload', (req, res) => {
    const rep = syncContent(db, config.contentDir);
    if (rep.errors.length) return back(res, '/admin/content', `Loaded with problems: ${rep.errors.join('; ')}`, 'err');
    back(res, '/admin/content', `Loaded ${rep.subjects} subject(s), ${rep.sections} section(s), ${rep.questions} question(s).`);
  });

  r.post('/content/upload', (req, res) => {
    const sid = String(req.body.subject_id || '');
    const name = String(req.body.file_name || '');
    if (!/^[a-z0-9-]+$/.test(sid) || !/^[A-Za-z0-9._-]+\.json$/.test(name) || name.startsWith('.')) return back(res, '/admin/content', 'Invalid subject id or file name.', 'err');
    let data;
    try { data = JSON.parse(String(req.body.json || '')); } catch (e) { return back(res, '/admin/content', `Invalid JSON: ${e.message}`, 'err'); }
    const dir = path.join(config.contentDir, sid);
    const target = name === 'subject.json' ? path.join(dir, name) : path.join(dir, 'sections', name);
    if (name === 'subject.json') data.id = sid;
    else if (data.id !== name.replace(/\.json$/, '')) return back(res, '/admin/content', `The section "id" must be "${name.replace(/\.json$/, '')}".`, 'err');
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, `${JSON.stringify(data, null, 2)}\n`);
    const rep = syncContent(db, config.contentDir);
    back(res, '/admin/content', `Saved ${sid}/${name}. ${rep.sections} sections, ${rep.questions} questions loaded.${rep.errors.length ? ` Problems: ${rep.errors.join('; ')}` : ''}`);
  });

  r.get('/questions/:sid/:sec', (req, res) => {
    const key = `${req.params.sid}/${req.params.sec}`;
    const s = db.get('SELECT * FROM sections WHERE key=?', key);
    if (!s) return res.status(404).send('Not found');
    const qs = db.all('SELECT * FROM questions WHERE section_key=? ORDER BY id', key);
    const usage = {};
    for (const u of db.all(`SELECT question_id, COUNT(*) n, AVG(COALESCE(admin_marks, ai_marks, self_marks) * 1.0 / max_marks) avg FROM test_items WHERE question_id IN (SELECT id FROM questions WHERE section_key=?) GROUP BY question_id`, key)) usage[u.question_id] = u;
    send(req, res, {
      title: `Questions ${s.number}`, active: 'content',
      body: html`<div class="page-head"><div><small class="muted"><a href="/admin/content">Content</a></small><h1>${s.number} ${s.title} — question bank</h1><p class="muted">${qs.length} questions. Each preview shows one random set of values; refresh for another.</p></div></div>
      ${qs.map((q) => {
    const d = JSON.parse(q.data);
    const scope = buildScope(d);
    const u = usage[q.id];
    return html`<div class="card q-card"><div class="q-head"><code>${d.id}</code><span class="chip">${TYPE_LABEL[d.type] || d.type}</span><span class="chip">${DIFF_LABEL[d.difficulty]}</span><span class="chip accent">${q.marks} marks</span>${u ? html`<small class="muted">used ${u.n}× · avg ${u.avg != null ? Math.round(u.avg * 100) + '%' : '—'}</small>` : ''}${q.active ? '' : html`<span class="chip bad">retired</span>`}</div>
          <div class="prose">${raw(md(fill(d.text, scope)))}</div>
          ${(d.parts || []).length ? html`<ul class="prose" style="list-style:none;padding-left:0">${d.parts.map((p) => html`<li><strong>(${p.label})</strong> ${raw(md(fill(p.text, scope), { inline: true }))}</li>`)}</ul>` : ''}
          <details><summary>Model answer & rubric</summary><div class="prose">${raw(md(fill(d.modelAnswer, scope)))}</div><ul class="prose">${(d.rubric || []).map((x) => html`<li>${x.point} <small class="muted">(${x.marks})</small></li>`)}</ul></details></div>`;
  })}`,
    });
  });

  r.get('/outbox', (req, res) => {
    const rows = db.all('SELECT * FROM outbox ORDER BY id DESC LIMIT 100');
    send(req, res, {
      title: 'Outbox', active: 'admin',
      body: html`<h1>Email outbox</h1><p class="muted">The last 100 emails the app sent or tried to send.${mailer.configured ? '' : ' Email is not configured, so you can copy links from here and pass them on.'}</p>
      ${rows.map((m) => html`<details class="card"><summary>${m.subject} → ${m.to_email} <small class="muted">${fmtDate(m.created_at, true)}</small> ${m.delivered ? html`<span class="chip good">sent</span>` : m.error ? html`<span class="chip bad">failed</span>` : html`<span class="chip warn">not sent</span>`}</summary><div class="answer-box">${m.body}</div>${m.error ? html`<small class="muted">${m.error}</small>` : ''}</details>`)}`,
    });
  });

  return r;
};
