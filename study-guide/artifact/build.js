#!/usr/bin/env node
'use strict';
// Builds the zero-infrastructure artifact edition into artifact/dist/:
//   index.html                 the page (app + styles + KaTeX CSS with inlined fonts)
//   content/subjects.json      subject list
//   content/<subject>/index.json      chapters and section metadata
//   content/<subject>/<section>.json  study material (no test questions)
//   content/<subject>/questions.json  the subject's test bank
// Usage: node artifact/build.js   (then publish dist/index.html with the files)
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const dist = path.join(__dirname, 'dist');
const contentDir = path.join(root, 'content');
const read = (p) => fs.readFileSync(p, 'utf8');

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(path.join(dist, 'content'), { recursive: true });

// ---- content ----
const marksOf = (q) => (q.rubric || []).reduce((s, r) => s + (Number(r.marks) || 0), 0);
const subjects = [];
const files = {};
for (const sid of fs.readdirSync(contentDir).sort()) {
  const sf = path.join(contentDir, sid, 'subject.json');
  if (!fs.existsSync(sf)) continue;
  const subject = JSON.parse(read(sf));
  const index = { id: sid, name: subject.name, description: subject.description || '', sections: [] };
  const questions = [];
  fs.mkdirSync(path.join(dist, 'content', sid), { recursive: true });
  for (const ch of subject.chapters || []) {
    const chapterTitle = ch.number != null ? `Chapter ${ch.number}: ${ch.title}` : ch.title;
    for (const secId of ch.sections || []) {
      const f = path.join(contentDir, sid, 'sections', `${secId}.json`);
      if (!fs.existsSync(f)) continue;
      const s = JSON.parse(read(f));
      const key = `${sid}/${secId}`;
      const { questions: qs = [], ...guide } = s;
      for (const q of qs) questions.push({ ...q, qid: `${sid}/${q.id}`, sectionKey: key, marks: marksOf(q) || 1 });
      index.sections.push({ key, number: String(s.number || secId), title: s.title || secId, chapter: ch.id, chapterTitle, minutes: s.estimatedMinutes || null, questions: qs.length });
      const out = `content/${key}.json`;
      fs.writeFileSync(path.join(dist, out), JSON.stringify(guide));
      files[out] = path.join(dist, out);
    }
  }
  if (!index.sections.length) continue;
  subjects.push({ id: sid, name: subject.name, description: subject.description || '' });
  for (const [name, data] of [['index.json', index], ['questions.json', questions]]) {
    const out = `content/${sid}/${name}`;
    fs.writeFileSync(path.join(dist, out), JSON.stringify(data));
    files[out] = path.join(dist, out);
  }
}
fs.writeFileSync(path.join(dist, 'content/subjects.json'), JSON.stringify(subjects));
files['content/subjects.json'] = path.join(dist, 'content/subjects.json');

// ---- KaTeX stylesheet with woff2 fonts as data URIs ----
const katexDist = path.join(path.dirname(require.resolve('katex/package.json')), 'dist');
let katexCss = read(path.join(katexDist, 'katex.min.css'));
katexCss = katexCss.replace(/src:([^;}]+)/g, (m, srcs) => {
  const woff2 = /url\((fonts\/[^)]+\.woff2)\)/.exec(srcs);
  if (!woff2) return m;
  const data = fs.readFileSync(path.join(katexDist, woff2[1])).toString('base64');
  return `src:url(data:font/woff2;base64,${data}) format("woff2")`;
});

// ---- shared modules (expr, plot) bundled for the browser ----
function mod(name, file) {
  return `SG.${name} = (function () { const module = { exports: {} }; const exports = module.exports;\n` +
    `const require = (p) => { if (p === './expr') return SG.expr; throw new Error('missing ' + p); };\n${read(file)}\nreturn module.exports; })();`;
}
const shared = `window.SG = window.SG || {};\n${mod('expr', path.join(root, 'src/expr.js'))}\n${mod('plot', path.join(root, 'src/plot.js'))}`;

const pkg = JSON.parse(read(path.join(root, 'node_modules/katex/package.json')));
const KATEX = pkg.version; // the CSS above comes from the same version as the script
const MARKED = '18.0.14';
const htmlOut = `<title>Study Guide</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500&display=swap">
<style>${katexCss}</style>
<style>${read(path.join(__dirname, 'app.css'))}</style>
<div id="app"><main class="wrap"><p class="muted">Loading the study guide…</p></main></div>
<script src="https://cdn.jsdelivr.net/npm/katex@${KATEX}/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@${MARKED}/lib/marked.umd.js"></script>
<script>${shared}</script>
<script>${read(path.join(__dirname, 'app.js'))}</script>
`;
fs.writeFileSync(path.join(dist, 'index.html'), htmlOut);
fs.writeFileSync(path.join(dist, 'files.json'), JSON.stringify(Object.fromEntries(Object.keys(files).map((k) => [k, path.relative(path.join(root, '..'), files[k])])), null, 1));
const size = (p) => (fs.statSync(p).size / 1024).toFixed(0);
console.log(`index.html ${size(path.join(dist, 'index.html'))} KB, ${Object.keys(files).length} content files, ${subjects.length} subjects`);
