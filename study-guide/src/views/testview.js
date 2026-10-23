'use strict';
const { html, raw } = require('../html');
const { renderMarkdown: md } = require('../content');
const { csrfField, fmtDate, scoreChip } = require('./layout');
const { renderItem, itemScore, parseJSON, KINDS } = require('../tests');

const TYPE_LABEL = { problem: 'Problem solving', conceptual: 'Concept', explain: 'Explain', analysis: 'Analysis', design: 'Design / investigate' };
const DIFF_LABEL = { 1: 'Foundation', 2: 'Standard', 3: 'Challenge' };

function questionBlock(r, it) {
  return html`
    <div class="q-head">
      <span class="q-num">${it.position}</span>
      <span class="chip">${TYPE_LABEL[r.type] || r.type}</span>
      <span class="chip">${DIFF_LABEL[r.difficulty] || ''}</span>
      <span class="chip accent">${it.max_marks} mark${it.max_marks === 1 ? '' : 's'}</span>
    </div>
    <div class="prose">${raw(md(r.text))}</div>
    ${r.parts.length ? html`<ol class="prose" style="list-style:none;padding-left:0">${r.parts.map((p) => html`<li><strong>(${p.label})</strong> ${raw(md(p.text, { inline: true }))}</li>`)}</ol>` : ''}`;
}

function photoBlock(test, it, editable) {
  const photos = parseJSON(it.attachments, []);
  if (!editable && !photos.length) return '';
  return html`<div class="photos" data-item="${it.id}" data-upload="/tests/${test.id}/items/${it.id}/photos">
    ${photos.map((p) => html`<figure class="photo"><a href="/uploads/${p}" target="_blank" rel="noopener"><img src="/uploads/${p}" alt="Photo of working" loading="lazy"></a>${editable ? html`<button type="button" class="ghost small photo-remove" data-name="${p}">Remove</button>` : ''}</figure>`)}
    ${editable ? html`<label class="btn ghost small photo-add">📷 Add photo of working<input type="file" accept="image/*" capture="environment" hidden></label>` : ''}
  </div>`;
}

function takeView(req, db, test, items) {
  const startedMs = new Date(test.created_at.replace(' ', 'T') + 'Z').getTime();
  const deadline = test.time_limit_min ? startedMs + test.time_limit_min * 60e3 : 0;
  return html`
  <div class="page-head">
    <div><h1>${test.title}</h1><p class="muted">${items.length} questions · ${test.total_marks} marks${test.time_limit_min ? ` · ${test.time_limit_min} minutes` : ' · untimed'}</p></div>
    ${deadline ? html`<div class="timer" data-deadline="${deadline}"><span>Time left</span><strong class="timer-val">--:--</strong></div>` : ''}
  </div>
  <div class="alert">Show your full working: the method or equation you use, each step, units where they apply, and a final statement. For explain questions, answer in full sentences using the correct vocabulary. You can also attach photos of handwritten working or sketches. Your answers save automatically.</div>
  <form method="post" action="/tests/${test.id}/submit" id="test-form" data-save="/tests/${test.id}/save">
    ${csrfField(req)}
    ${items.map((it) => {
    const r = renderItem(db, it);
    if (!r) return '';
    const finals = parseJSON(it.final_answers, {});
    const numeric = r.parts.filter((p) => p.expected);
    return html`<div class="card q-card">
      ${questionBlock(r, it)}
      <label for="a${it.id}">Your working and answer</label>
      <textarea id="a${it.id}" name="answer_${it.id}" rows="8" placeholder="Show each step of your working and finish with a clear final answer or statement.">${it.answer_text}</textarea>
      ${photoBlock(test, it, true)}
      ${numeric.length ? html`<div class="finals">${numeric.map((p) => html`<div><label for="f${it.id}${p.label}">(${p.label}) final answer${p.expected.unit ? html` <small>in ${p.expected.unit}</small>` : ''}</label>
        <input id="f${it.id}${p.label}" type="text" name="final_${it.id}_${p.label}" value="${finals[p.label] || ''}" autocomplete="off"></div>`)}</div>` : ''}
    </div>`;
  })}
    <div class="form-actions">
      <button type="submit" data-confirm="Submit your test? You cannot change answers afterwards.">Submit test</button>
      <span class="muted save-status"></span>
    </div>
  </form>`;
}

function itemReview(req, db, test, it, { admin }) {
  const r = renderItem(db, it);
  if (!r) return '';
  const finals = parseJSON(it.final_answers, {});
  const checks = parseJSON(it.auto_checks, {});
  const s = itemScore(it);
  const selfPoints = parseJSON(it.self_points, []);
  const official = it.admin_marks != null || it.ai_marks != null;
  const canSelf = !admin && test.user_id === req.user.id && it.admin_marks == null;
  const sourceLabel = { teacher: 'marked by teacher', ai: 'AI-marked', self: 'self-assessed' }[s.source];

  return html`<div class="card q-card" id="item-${it.id}">
    ${questionBlock(r, it)}
    <div class="row" style="margin:.4rem 0 .8rem">
      ${s.marks != null ? html`<span class="chip ${s.marks >= it.max_marks * 0.75 ? 'good' : s.marks >= it.max_marks * 0.5 ? 'warn' : 'bad'}">${s.marks} / ${it.max_marks}</span><small class="muted">${sourceLabel}</small>`
    : html`<span class="chip warn">Not marked yet</span>`}
    </div>
    <h3>${admin ? 'Student answer' : 'Your answer'}</h3>
    <div class="answer-box">${it.answer_text || '(no written answer)'}</div>
    ${photoBlock(test, it, false)}
    ${r.parts.some((p) => p.expected) ? html`<div class="finals">${r.parts.filter((p) => p.expected).map((p) => html`<div class="card tint" style="padding:.6rem .8rem">
      <small>(${p.label}) final answer</small><div>${finals[p.label] || '—'} ${checks[p.label] === true ? html`<span class="chip good">matches</span>` : checks[p.label] === false ? html`<span class="chip bad">check this</span>` : ''}</div>
      <small class="muted">Expected ≈ ${p.expected.display} ${p.expected.unit}</small></div>`)}</div>` : ''}

    ${it.admin_feedback ? html`<h3>Teacher feedback</h3><div class="feedback">${it.admin_feedback}</div>` : ''}
    ${it.ai_feedback ? html`<h3>${admin ? 'AI marking notes' : 'Feedback'}</h3><div class="feedback">${it.ai_feedback}</div>` : ''}

    <details ${admin ? 'open' : ''}><summary>Model answer</summary><div class="prose">${raw(md(r.modelAnswer))}</div></details>
    <details ${admin || canSelf ? 'open' : ''}><summary>Marking rubric</summary>
      ${canSelf && !official ? html`<form method="post" action="/tests/${test.id}/self-assess">
        ${csrfField(req)}<input type="hidden" name="item" value="${it.id}">
        <p class="muted">Compare your answer with the model answer and tick each point you earned honestly. Your teacher can review this.</p>
        ${r.rubric.map((p, i) => html`<label class="check"><input type="checkbox" name="pt" value="${i}" ${selfPoints.includes(i) ? 'checked' : ''}> <span>${raw(md(p.point, { inline: true }))} <small class="muted">(${p.marks})</small></span></label>`)}
        <div class="form-actions"><button class="small" type="submit">Save self-assessment</button></div>
      </form>` : html`<ul class="rubric prose">${r.rubric.map((p, i) => html`<li>${raw(md(p.point, { inline: true }))} <small class="muted">(${p.marks})</small>${selfPoints.includes(i) ? html` <span class="chip">self ✓</span>` : ''}</li>`)}</ul>`}
    </details>

    ${admin ? html`<form method="post" action="/admin/tests/${test.id}/grade" class="card tint" style="margin-top:.8rem">
      ${csrfField(req)}<input type="hidden" name="item" value="${it.id}">
      <div class="row">
        <div style="width:140px"><label for="m${it.id}">Marks (max ${it.max_marks})</label>
        <input id="m${it.id}" type="number" name="marks" min="0" max="${it.max_marks}" step="0.5" value="${it.admin_marks != null ? it.admin_marks : (it.ai_marks != null ? it.ai_marks : (it.self_marks != null ? it.self_marks : ''))}" required></div>
        <div class="spacer"><label for="fb${it.id}">Feedback to student</label><textarea id="fb${it.id}" name="feedback" rows="2" style="min-height:60px">${it.admin_feedback || ''}</textarea></div>
      </div>
      <div class="form-actions"><button class="small" type="submit">${it.admin_marks != null ? 'Update mark' : 'Save mark'}</button>${it.ai_marks != null ? html`<small class="muted">AI suggested ${it.ai_marks}</small>` : ''}${it.self_marks != null ? html`<small class="muted">Student self-assessed ${it.self_marks}</small>` : ''}</div>
    </form>` : ''}
  </div>`;
}

function reviewView(req, db, test, items, { admin = false, student = null } = {}) {
  const official = items.filter((i) => i.admin_marks != null || i.ai_marks != null).length;
  return html`
  <div class="page-head">
    <div>
      <h1>${test.title}</h1>
      <p class="muted">${student ? html`${student.name} · ` : ''}${KINDS[test.kind].label} · submitted ${fmtDate(test.submitted_at, true)}${test.overtime ? ' · submitted after the time limit' : ''}</p>
    </div>
    <div class="row">${scoreChip(test.score, test.status)}<a class="btn ghost small no-print" href="javascript:print()">Print</a></div>
  </div>
  ${test.status === 'submitted' ? html`<div class="alert warn">${official}/${items.length} answers have an official mark. ${admin ? 'Mark the rest below, or accept the student\'s self-assessment.' : 'Use the rubric under each answer to self-assess now; your teacher will confirm the final marks.'}</div>` : ''}
  ${admin && test.status === 'submitted' ? html`<form method="post" action="/admin/tests/${test.id}/accept" class="no-print" style="margin-bottom:1rem">${csrfField(req)}<button class="ghost small" type="submit">Accept remaining AI/self marks as final</button></form>` : ''}
  ${items.map((it) => itemReview(req, db, test, it, { admin }))}`;
}

module.exports = { takeView, reviewView, TYPE_LABEL, DIFF_LABEL };
