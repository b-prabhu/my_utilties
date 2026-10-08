import fs from 'fs';
const d = '/tmp/claude-0/-home-user-my-utilties/93483819-7895-56d3-83b9-ce3d5ad26b1e/scratchpad/page/';
const html = fs.readFileSync(d + 'index.html', 'utf8');
const a = html.indexOf('var ROLES =');
const b = html.indexOf('/* ===================== derived');
if (a < 0 || b < 0) throw new Error('markers not found');
const slice = html.slice(a, b);
const ctx = {};
const fn = new Function(slice + '\n return {ROLES:ROLES, C:C, VERDICT:VERDICT, FLAGS:FLAGS};');
const core = fn();
const q = new Function(fs.readFileSync(d + 'questions.js', 'utf8') +
  '\n return {QTOPICS:QTOPICS, QBANK:QBANK, QSTREAM:QSTREAM};')();
const r = new Function(fs.readFileSync(d + 'resumes.js', 'utf8') + '\n return RESUMES;')();
const out = {...core, ...q, RESUMES: r};
fs.writeFileSync('data.json', JSON.stringify(out, null, 1));
console.log('candidates', out.C.length, '| verdicts', Object.keys(out.VERDICT).length,
            '| flags', out.FLAGS.length, '| questions', out.QBANK.length,
            '| resumes', Object.keys(out.RESUMES).length);
