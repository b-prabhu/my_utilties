'use strict';
// Test generation, scoring and per-student analytics.
const { buildScope, varValues, fill, evaluate, checkNumeric, formatSig } = require('./expr');

const KINDS = {
  daily: { label: 'Daily practice', count: 4, minutes: 25, difficulty: [1, 2] },
  weekly: { label: 'Weekly test', count: 8, minutes: 60, difficulty: [1, 2, 3] },
  monthly: { label: 'Monthly exam', count: 12, minutes: 100, difficulty: [1, 2, 3] },
  ondemand: { label: 'On-demand test', count: 6, minutes: 45, difficulty: [1, 2, 3] },
};

// Calendar keys use the server's local time zone (set TZ in the environment).
function periodKey(kind, date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  if (kind === 'daily') return `${y}-${m}-${d}`;
  if (kind === 'monthly') return `${y}-${m}`;
  if (kind === 'weekly') {
    const t = new Date(Date.UTC(y, date.getMonth(), date.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    const week = Math.ceil(((t - yearStart) / 86400e3 + 1) / 7);
    return `${t.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
  }
  return null;
}

function parseJSON(s, fallback) {
  try { const v = JSON.parse(s); return v == null ? fallback : v; } catch { return fallback; }
}

function itemScore(item) {
  if (item.admin_marks != null) return { marks: item.admin_marks, source: 'teacher' };
  if (item.ai_marks != null) return { marks: item.ai_marks, source: 'ai' };
  if (item.self_marks != null) return { marks: item.self_marks, source: 'self' };
  return { marks: null, source: null };
}

function refreshTestScore(db, testId) {
  const items = db.all('SELECT * FROM test_items WHERE test_id=?', testId);
  const t = db.get('SELECT * FROM tests WHERE id=?', testId);
  if (!t || t.status === 'in_progress') return;
  let got = 0; let max = 0; let allOfficial = true; let anyScore = false;
  for (const it of items) {
    max += it.max_marks;
    const s = itemScore(it);
    if (s.marks != null) { got += s.marks; anyScore = true; }
    if (s.source !== 'teacher' && s.source !== 'ai') allOfficial = false;
  }
  const pct = anyScore && max ? Math.round((got / max) * 1000) / 10 : null;
  if (allOfficial && items.length) {
    db.run("UPDATE tests SET score=?, status='graded', graded_at=COALESCE(graded_at, datetime('now')) WHERE id=?", pct, testId);
  } else {
    db.run("UPDATE tests SET score=?, status='submitted', graded_at=NULL WHERE id=?", pct, testId);
  }
}

// Mastery 0..1 per section from the student's scored items (latest 10 each).
function sectionMastery(db, userId, subjectId) {
  const rows = db.all(`SELECT ti.*, t.submitted_at FROM test_items ti JOIN tests t ON t.id=ti.test_id
    WHERE t.user_id=? AND t.subject_id=? AND t.status!='in_progress' ORDER BY t.submitted_at DESC`, userId, subjectId);
  const acc = {};
  for (const r of rows) {
    const s = itemScore(r);
    if (s.marks == null) continue;
    const a = (acc[r.section_key] ||= { got: 0, max: 0, n: 0 });
    if (a.n >= 10) continue;
    a.got += s.marks; a.max += r.max_marks; a.n++;
  }
  const out = {};
  for (const [k, a] of Object.entries(acc)) out[k] = { mastery: a.max ? a.got / a.max : 0, attempts: a.n };
  return out;
}

function sectionsForKind(db, userId, subjectId, kind, chosen) {
  const all = db.all('SELECT key, title, number, sort FROM sections WHERE subject_id=? AND active=1 ORDER BY sort', subjectId);
  const valid = new Set(all.map((s) => s.key));
  if (kind === 'ondemand') {
    const picked = (chosen || []).filter((k) => valid.has(k));
    return picked.length ? picked : all.map((s) => s.key);
  }
  if (kind === 'monthly') return all.map((s) => s.key);
  const studied = db.all(`SELECT p.section_key FROM progress p JOIN sections s ON s.key=p.section_key
    WHERE p.user_id=? AND s.subject_id=? AND s.active=1 ORDER BY p.updated_at DESC`, userId, subjectId).map((r) => r.section_key);
  if (kind === 'daily') {
    if (studied.length) return studied.slice(0, 3);
    return all.slice(0, 1).map((s) => s.key);
  }
  // weekly
  if (studied.length) return studied;
  return all.slice(0, 2).map((s) => s.key);
}

function weightedPick(cands, rand) {
  const total = cands.reduce((s, c) => s + c.w, 0);
  let r = rand() * total;
  for (let i = 0; i < cands.length; i++) {
    r -= cands[i].w;
    if (r <= 0) return i;
  }
  return cands.length - 1;
}

function chooseQuestions(db, userId, subjectId, sectionKeys, count, difficulty, rand = Math.random) {
  const placeholders = sectionKeys.map(() => '?').join(',');
  let qs = db.all(`SELECT id, section_key, difficulty, marks, data FROM questions
    WHERE active=1 AND subject_id=? AND section_key IN (${placeholders})`, subjectId, ...sectionKeys);
  const filtered = qs.filter((q) => difficulty.includes(q.difficulty));
  if (filtered.length >= count) qs = filtered;
  if (!qs.length) return [];

  const seen = {};
  for (const r of db.all(`SELECT ti.question_id, MAX(t.created_at) AS last FROM test_items ti JOIN tests t ON t.id=ti.test_id
      WHERE t.user_id=? GROUP BY ti.question_id`, userId)) seen[r.question_id] = r.last;
  const mastery = sectionMastery(db, userId, subjectId);
  const twoWeeksAgo = new Date(Date.now() - 14 * 86400e3).toISOString().replace('T', ' ').slice(0, 19);

  const bySection = {};
  for (const q of qs) {
    let w = 1;
    if (!seen[q.id]) w *= 3;
    else if (seen[q.id] > twoWeeksAgo) w *= 0.3;
    const m = mastery[q.section_key];
    if (m) w *= 1 + (1 - m.mastery) * 1.5;
    (bySection[q.section_key] ||= []).push({ q, w });
  }
  // Round-robin across sections so a test covers its whole scope.
  const order = Object.keys(bySection).sort(() => rand() - 0.5);
  const picked = [];
  while (picked.length < count && order.some((k) => bySection[k].length)) {
    for (const k of order) {
      if (picked.length >= count) break;
      const list = bySection[k];
      if (!list.length) continue;
      const i = weightedPick(list, rand);
      picked.push(list[i].q);
      list.splice(i, 1);
    }
  }
  return picked;
}

function createTest(db, { userId, subjectId, kind, sectionKeys: chosen, count, difficulty, minutes }) {
  const cfg = KINDS[kind];
  if (!cfg) throw new Error('Unknown test type');
  const pk = periodKey(kind);
  if (pk) {
    const existing = db.get('SELECT id FROM tests WHERE user_id=? AND subject_id=? AND kind=? AND period_key=?', userId, subjectId, kind, pk);
    if (existing) return existing.id;
  }
  const sectionKeys = sectionsForKind(db, userId, subjectId, kind, chosen);
  const n = kind === 'ondemand' ? Math.max(1, Math.min(20, count || cfg.count)) : cfg.count;
  const diff = kind === 'ondemand' && difficulty && difficulty.length ? difficulty : cfg.difficulty;
  const qs = chooseQuestions(db, userId, subjectId, sectionKeys, n, diff);
  if (!qs.length) throw new Error('There are no questions for the selected topics yet.');
  const limit = kind === 'ondemand' ? (minutes === 0 ? null : Math.max(5, Math.min(240, minutes || cfg.minutes))) : cfg.minutes;
  const subject = db.get('SELECT name FROM subjects WHERE id=?', subjectId);
  const title = `${cfg.label} · ${subject ? subject.name : subjectId}`;

  return db.tx(() => {
    const total = qs.reduce((s, q) => s + q.marks, 0);
    const r = db.run(`INSERT INTO tests (user_id, subject_id, kind, period_key, title, section_keys, time_limit_min, total_marks)
      VALUES (?,?,?,?,?,?,?,?)`, userId, subjectId, kind, pk, title, JSON.stringify(sectionKeys), limit, total);
    const testId = Number(r.lastInsertRowid);
    qs.forEach((q, i) => {
      const data = JSON.parse(q.data);
      const scope = buildScope(data);
      db.run(`INSERT INTO test_items (test_id, question_id, section_key, position, vars, max_marks) VALUES (?,?,?,?,?,?)`,
        testId, q.id, q.section_key, i + 1, JSON.stringify(varValues(data, scope)), q.marks);
    });
    return testId;
  });
}

// Fully materialised question (numbers filled in) for display and grading.
function renderItem(db, item) {
  const q = db.get('SELECT * FROM questions WHERE id=?', item.question_id);
  if (!q) return null;
  const data = JSON.parse(q.data);
  const scope = buildScope(data, Math.random, parseJSON(item.vars, {}));
  const parts = (data.parts || []).map((p) => {
    let expected = null;
    if (p.answer) {
      const v = evaluate(p.answer.expr, scope);
      expected = { value: v, display: formatSig(v, p.answer.sig || 3), unit: p.answer.unit || '', tol: p.answer.tol || 0.02 };
    }
    return { label: p.label, text: fill(p.text, scope), expected };
  });
  return {
    question: data,
    type: data.type,
    difficulty: data.difficulty,
    text: fill(data.text, scope),
    parts,
    modelAnswer: fill(data.modelAnswer, scope),
    rubric: data.rubric || [],
  };
}

function autoCheck(rendered, finalAnswers) {
  const out = {};
  for (const p of rendered.parts) {
    if (!p.expected) continue;
    const given = finalAnswers[p.label];
    out[p.label] = given == null || String(given).trim() === '' ? null : checkNumeric(p.expected.value, given, p.expected.tol);
  }
  return out;
}

function saveAnswers(db, test, body) {
  if (test.status !== 'in_progress') return false;
  const items = db.all('SELECT * FROM test_items WHERE test_id=?', test.id);
  db.tx(() => {
    for (const it of items) {
      const text = body[`answer_${it.id}`];
      const finals = {};
      for (const [k, v] of Object.entries(body)) {
        const m = /^final_(\d+)_(.+)$/.exec(k);
        if (m && Number(m[1]) === it.id) finals[m[2]] = String(v).slice(0, 100);
      }
      if (text != null || Object.keys(finals).length) {
        db.run('UPDATE test_items SET answer_text=?, final_answers=? WHERE id=?',
          text != null ? String(text).slice(0, 20000) : it.answer_text,
          Object.keys(finals).length ? JSON.stringify(finals) : it.final_answers, it.id);
      }
    }
  });
  return true;
}

function submitTest(db, test, body) {
  if (test.status !== 'in_progress') return false;
  saveAnswers(db, test, body || {});
  const items = db.all('SELECT * FROM test_items WHERE test_id=?', test.id);
  let overtime = 0;
  if (test.time_limit_min) {
    const started = new Date(test.created_at.replace(' ', 'T') + 'Z').getTime();
    if (Date.now() - started > (test.time_limit_min + 2) * 60e3) overtime = 1;
  }
  db.tx(() => {
    for (const it of items) {
      const r = renderItem(db, it);
      if (!r) continue;
      const checks = autoCheck(r, parseJSON(it.final_answers, {}));
      db.run('UPDATE test_items SET auto_checks=? WHERE id=?', JSON.stringify(checks), it.id);
    }
    db.run("UPDATE tests SET status='submitted', submitted_at=datetime('now'), overtime=? WHERE id=?", overtime, test.id);
  });
  refreshTestScore(db, test.id);
  return true;
}

// Summary numbers shown on dashboards (student's own, or admin views).
function studentStats(db, userId) {
  const tests = db.all(`SELECT t.*, s.name AS subject_name FROM tests t LEFT JOIN subjects s ON s.id=t.subject_id
    WHERE t.user_id=? ORDER BY t.created_at DESC`, userId);
  const done = tests.filter((t) => t.status !== 'in_progress' && t.score != null);
  const avg = done.length ? done.reduce((s, t) => s + t.score, 0) / done.length : null;
  // Study streak: consecutive days (ending today or yesterday) with any activity.
  const days = new Set([
    ...db.all('SELECT substr(updated_at,1,10) d FROM progress WHERE user_id=?', userId).map((r) => r.d),
    ...tests.filter((t) => t.submitted_at).map((t) => t.submitted_at.slice(0, 10)),
  ]);
  let streak = 0;
  const d = new Date();
  const key = (x) => x.toISOString().slice(0, 10);
  if (!days.has(key(d))) d.setUTCDate(d.getUTCDate() - 1);
  while (days.has(key(d))) { streak++; d.setUTCDate(d.getUTCDate() - 1); }
  const completed = db.get("SELECT COUNT(*) n FROM progress WHERE user_id=? AND status='completed'", userId).n;
  return { tests, done, avg, streak, completed, pending: tests.filter((t) => t.status === 'submitted').length };
}

module.exports = {
  KINDS, periodKey, createTest, renderItem, saveAnswers, submitTest, refreshTestScore,
  itemScore, sectionMastery, studentStats, parseJSON, chooseQuestions,
};
