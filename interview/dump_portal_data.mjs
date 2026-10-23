/* Dumps the portal's own data files to data.json, which the workbook build
   then reads, so the two cannot drift apart. */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const d = path.dirname(fileURLToPath(import.meta.url)) + '/';
const html = fs.readFileSync(d + 'pipeline_page.html', 'utf8');
const a = html.indexOf('var ROLES =');
const b = html.indexOf('/* ===================== derived');
if (a < 0 || b < 0) throw new Error('markers not found');
const slice = html.slice(a, b);
const ctx = {};
const fn = new Function(slice + '\n return {ROLES:ROLES, C:C, VERDICT:VERDICT, FLAGS:FLAGS};');
const core = fn();
const q = new Function(fs.readFileSync(d + 'pipeline_questions.js', 'utf8') +
  '\n return {QTOPICS:QTOPICS, QBANK:QBANK, QSTREAM:QSTREAM};')();
const r = new Function(fs.readFileSync(d + 'pipeline_resumes.js', 'utf8') + '\n return RESUMES;')();
const out = {...core, ...q, RESUMES: r};
fs.writeFileSync(d + 'data.json', JSON.stringify(out, null, 1));
console.log('candidates', out.C.length, '| verdicts', Object.keys(out.VERDICT).length,
            '| flags', out.FLAGS.length, '| questions', out.QBANK.length,
            '| resumes', Object.keys(out.RESUMES).length);
