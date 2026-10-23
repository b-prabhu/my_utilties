#!/usr/bin/env node
'use strict';
// Validates every subject/section JSON file under content/ and renders each
// question template a few times to catch broken expressions.
// Usage: node scripts/validate-content.js [contentDir]
const fs = require('fs');
const path = require('path');
const { buildScope, fill, evaluate } = require('../src/expr');
const { renderPlot } = require('../src/plot');
const checkPlots = (txt) => { for (const m of String(txt || '').matchAll(/```plot\s*\n([\s\S]*?)```/g)) renderPlot(m[1]); };

const root = path.resolve(process.argv[2] || path.join(__dirname, '..', 'content'));
const only = process.argv[3] || null; // optional: limit to one subject id
const TYPES = new Set(['problem', 'conceptual', 'explain', 'analysis', 'design']);
let errors = 0;
let questionCount = 0;
const err = (where, msg) => { errors++; console.error(`✗ ${where}: ${msg}`); };

function seeded(seed) {
  let s = seed;
  return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; };
}

for (const subjectId of fs.readdirSync(root)) {
  const dir = path.join(root, subjectId);
  if (!fs.statSync(dir).isDirectory() || (only && subjectId !== only)) continue;
  const subjFile = path.join(dir, 'subject.json');
  if (!fs.existsSync(subjFile)) { err(subjectId, 'missing subject.json'); continue; }
  let subject;
  try { subject = JSON.parse(fs.readFileSync(subjFile, 'utf8')); } catch (e) { err(subjFile, e.message); continue; }
  if (subject.id !== subjectId) err(subjFile, `id "${subject.id}" should equal folder name "${subjectId}"`);
  const ids = new Set();
  for (const ch of subject.chapters || []) {
    for (const sid of ch.sections || []) {
      const f = path.join(dir, 'sections', `${sid}.json`);
      if (!fs.existsSync(f)) { err(subjectId, `section file ${sid}.json missing (listed in chapter ${ch.id})`); continue; }
      let s;
      try { s = JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { err(f, e.message); continue; }
      const where = `${subjectId}/${sid}`;
      if (s.id !== sid) err(where, `id "${s.id}" should be "${sid}"`);
      for (const k of ['number', 'title', 'overview']) if (!s[k]) err(where, `missing ${k}`);
      if (!Array.isArray(s.lessons) || !s.lessons.length) err(where, 'needs at least one lesson');
      try { for (const l of s.lessons || []) checkPlots(l.body); for (const e of s.workedExamples || []) { checkPlots(e.problem); (e.steps || []).forEach(checkPlots); } } catch (e) { err(where, `plot: ${e.message}`); }
      for (const q of s.questions || []) {
        questionCount++;
        const qw = `${where}#${q.id}`;
        if (!q.id || ids.has(q.id)) err(qw, 'missing or duplicate id');
        ids.add(q.id);
        if (!TYPES.has(q.type)) err(qw, `bad type "${q.type}"`);
        if (![1, 2, 3].includes(q.difficulty)) err(qw, 'difficulty must be 1, 2 or 3');
        if (!q.text) err(qw, 'missing text');
        if (!q.modelAnswer) err(qw, 'missing modelAnswer');
        if (!Array.isArray(q.rubric) || !q.rubric.length) err(qw, 'missing rubric');
        for (const r of q.rubric || []) if (!r.point || !(r.marks > 0)) err(qw, 'rubric items need point and marks > 0');
        for (let i = 0; i < 5; i++) {
          try {
            const scope = buildScope(q, seeded(i * 7919 + 1));
            fill(q.text, scope);
            if (/\{\{\{/.test(q.text + q.modelAnswer + JSON.stringify(q.parts || []))) throw new Error('ambiguous "{{{" – add a space after the LaTeX brace');
            checkPlots(fill(q.text, scope));
            checkPlots(fill(q.modelAnswer, scope));
            for (const p of q.parts || []) {
              fill(p.text, scope);
              if (p.answer) {
                const v = evaluate(p.answer.expr, scope);
                if (!Number.isFinite(v)) throw new Error(`part ${p.label} answer is ${v}`);
              }
            }
          } catch (e) { err(qw, e.message); break; }
        }
      }
    }
  }
}
console.log(`${questionCount} questions checked, ${errors} error(s).`);
process.exit(errors ? 1 : 0);
