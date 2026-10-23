'use strict';
const { html, raw } = require('../html');
const { renderMarkdown: md, renderTex } = require('../content');

const cache = new Map();

// Render a section's study material once per content version.
function renderSectionBody(key, dataJson) {
  const hit = cache.get(key);
  if (hit && hit.src === dataJson) return hit.out;
  const s = JSON.parse(dataJson);
  const toc = [];
  const add = (id, label, cond) => { if (cond) toc.push({ id, label }); };
  add('overview', 'Overview & goals', s.overview || (s.objectives || []).length);
  for (const l of s.lessons || []) add(`lesson-${l.id}`, l.title, true);
  add('terms', 'Key terms', (s.keyTerms || []).length);
  add('formulas', 'Formulas', (s.formulas || []).length);
  add('examples', 'Worked examples', (s.workedExamples || []).length);
  add('misconceptions', 'Common mistakes', (s.misconceptions || []).length);
  add('realworld', 'In real life', (s.realWorld || []).length);
  add('practice', 'Check yourself', (s.practice || []).length);
  add('summary', 'Summary', (s.summary || []).length);

  const body = html`
    ${s.overview || (s.objectives || []).length ? html`<section id="overview" class="card tint lesson">
      <h2>Overview</h2>
      <div class="prose">${raw(md(s.overview))}</div>
      ${(s.objectives || []).length ? html`<h3>By the end of this section you can</h3><ul class="prose">${s.objectives.map((o) => html`<li>${raw(md(o, { inline: true }))}</li>`)}</ul>` : ''}
    </section>` : ''}

    ${(s.lessons || []).map((l, i) => html`<section id="lesson-${l.id}" class="card lesson">
      <span class="chip">Lesson ${i + 1}</span>
      <h2 style="margin-top:.5rem">${l.title}</h2>
      <div class="prose">${raw(md(l.body))}</div>
    </section>`)}

    ${(s.keyTerms || []).length ? html`<section id="terms" class="card lesson"><h2>Key terms</h2>
      ${s.keyTerms.map((t) => html`<div class="term"><strong>${t.term}</strong><div class="prose">${raw(md(t.definition))}</div></div>`)}
    </section>` : ''}

    ${(s.formulas || []).length ? html`<section id="formulas" class="card lesson"><h2>Formulas</h2>
      ${s.formulas.map((f) => html`<div class="formula"><strong>${f.name}</strong>${raw(renderTex(f.latex))}<div class="prose muted">${raw(md(f.meaning || ''))}</div></div>`)}
    </section>` : ''}

    ${(s.workedExamples || []).length ? html`<section id="examples" class="card lesson"><h2>Worked examples</h2>
      ${s.workedExamples.map((e, i) => html`<div class="example">
        <h3>Example ${i + 1}: ${e.title}</h3>
        <div class="prose">${raw(md(e.problem))}</div>
        <details><summary>Show the step-by-step solution</summary>
          ${(e.steps || []).map((st) => html`<div class="step prose">${raw(md(st))}</div>`)}
          ${e.answer ? html`<div class="alert ok prose" style="margin-top:.6rem">${raw(md(e.answer))}</div>` : ''}
        </details>
      </div>`)}
    </section>` : ''}

    ${(s.misconceptions || []).length ? html`<section id="misconceptions" class="card lesson"><h2>Common mistakes</h2>
      ${s.misconceptions.map((m) => html`<div class="myth"><div class="no"><small>Myth</small><div class="prose">${raw(md(m.myth))}</div></div><div class="yes"><small>Physics says</small><div class="prose">${raw(md(m.fact))}</div></div></div>`)}
    </section>` : ''}

    ${(s.realWorld || []).length ? html`<section id="realworld" class="card lesson"><h2>In real life</h2>
      <div class="grid grid-2">${s.realWorld.map((r) => typeof r === 'string'
    ? html`<div class="card tint prose">${raw(md(r))}</div>`
    : html`<div class="card tint"><h3>${r.title}</h3><div class="prose">${raw(md(r.body))}</div></div>`)}</div>
    </section>` : ''}

    ${(s.practice || []).length ? html`<section id="practice" class="card lesson"><h2>Check yourself</h2>
      <p class="muted">Work each problem on paper first. Then open the hint or the full solution and tick it off.</p>
      ${s.practice.map((p, i) => html`<div class="q-card" data-practice="${i}">
        <div class="q-head"><span class="q-num">${i + 1}</span><label class="check" style="margin:0"><input type="checkbox" class="practice-done" data-index="${i}"> Done</label></div>
        <div class="prose">${raw(md(p.question))}</div>
        ${p.hint ? html`<details><summary>Hint</summary><div class="prose">${raw(md(p.hint))}</div></details>` : ''}
        <details><summary>Full solution</summary><div class="prose">${raw(md(p.solution))}</div></details>
      </div>`)}
    </section>` : ''}

    ${(s.summary || []).length ? html`<section id="summary" class="card tint lesson"><h2>Summary</h2>
      <ul class="prose">${s.summary.map((x) => html`<li>${raw(md(x, { inline: true }))}</li>`)}</ul>
    </section>` : ''}`;

  const out = { toc, body, questionCount: (s.questions || []).length };
  cache.set(key, { src: dataJson, out });
  return out;
}

module.exports = { renderSectionBody };
