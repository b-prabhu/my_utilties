'use strict';
const fs = require('fs');
const path = require('path');
const { marked } = require('marked');
const katex = require('katex');
const { renderPlot } = require('./plot');

marked.setOptions({ gfm: true, breaks: false });

// Render markdown with $inline$ and $$display$$ maths. Maths is pulled out
// before markdown parsing so underscores and backslashes survive intact.
function renderMarkdown(src, { inline = false } = {}) {
  if (!src) return '';
  const math = [];
  // A literal dollar sign is written \$ (e.g. prices); keep it out of maths.
  src = String(src).replace(/\\\$/g, '@@DOLLAR@@');
  // ```plot blocks become inline SVG graphs.
  let text = String(src).replace(/```plot\s*\n([\s\S]*?)```/g, (m, body) => {
    let svg;
    try { svg = renderPlot(body); } catch (e) { svg = `<div class="alert err">Graph error: ${String(e.message).replace(/</g, '&lt;')}</div>`; }
    math.push(svg);
    return `\n\n@@MATH${math.length - 1}@@\n\n`;
  });
  text = text.replace(/\$\$([\s\S]+?)\$\$|\$([^\n$]+?)\$/g, (m, display, inl) => {
    const tex = display != null ? display : inl;
    let html;
    try {
      html = katex.renderToString(tex.trim(), { displayMode: display != null, throwOnError: false, output: 'html' });
    } catch {
      html = m;
    }
    math.push(html);
    return `@@MATH${math.length - 1}@@`;
  });
  text = inline ? marked.parseInline(text) : marked.parse(text);
  text = text.replace(/@@DOLLAR@@/g, '$');
  return text.replace(/<p>\s*(@@MATH\d+@@)\s*<\/p>/g, '$1').replace(/@@MATH(\d+)@@/g, (_, i) => math[Number(i)]);
}

function renderTex(tex) {
  return katex.renderToString(String(tex), { displayMode: true, throwOnError: false, output: 'html' });
}

function marksOf(q) {
  return (q.rubric || []).reduce((s, r) => s + (Number(r.marks) || 0), 0);
}

// Load content/<subject>/ folders into the database. Existing user data
// (progress, tests) is keyed by section/question id so it survives reloads.
function syncContent(db, contentDir) {
  const report = { subjects: 0, sections: 0, questions: 0, errors: [] };
  if (!fs.existsSync(contentDir)) return report;
  const seenSubjects = new Set();
  const seenSections = new Set();
  const seenQuestions = new Set();

  db.tx(() => {
    for (const subjectId of fs.readdirSync(contentDir).sort()) {
      const dir = path.join(contentDir, subjectId);
      const subjFile = path.join(dir, 'subject.json');
      if (!fs.statSync(dir).isDirectory() || !fs.existsSync(subjFile)) continue;
      let subject;
      try { subject = JSON.parse(fs.readFileSync(subjFile, 'utf8')); } catch (e) {
        report.errors.push(`${subjectId}/subject.json: ${e.message}`);
        continue;
      }
      subject.id = subjectId;
      seenSubjects.add(subjectId);
      report.subjects++;
      db.run(`INSERT INTO subjects (id, name, description, data, active) VALUES (?,?,?,?,1)
              ON CONFLICT(id) DO UPDATE SET name=excluded.name, description=excluded.description, data=excluded.data, active=1`,
      subjectId, subject.name || subjectId, subject.description || '', JSON.stringify(subject));

      let sort = 0;
      for (const ch of subject.chapters || []) {
        for (const sid of ch.sections || []) {
          sort++;
          const f = path.join(dir, 'sections', `${sid}.json`);
          if (!fs.existsSync(f)) continue; // listed but not written yet
          let s;
          try { s = JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) {
            report.errors.push(`${subjectId}/sections/${sid}.json: ${e.message}`);
            continue;
          }
          const key = `${subjectId}/${sid}`;
          seenSections.add(key);
          report.sections++;
          const chapterTitle = ch.number != null ? `Chapter ${ch.number}: ${ch.title}` : ch.title;
          db.run(`INSERT INTO sections (key, subject_id, section_id, chapter_id, chapter_title, number, title, sort, minutes, data, active)
                  VALUES (?,?,?,?,?,?,?,?,?,?,1)
                  ON CONFLICT(key) DO UPDATE SET chapter_id=excluded.chapter_id, chapter_title=excluded.chapter_title,
                    number=excluded.number, title=excluded.title, sort=excluded.sort, minutes=excluded.minutes,
                    data=excluded.data, active=1`,
          key, subjectId, sid, ch.id, chapterTitle, String(s.number || sid), s.title || sid, sort,
          s.estimatedMinutes || null, JSON.stringify(s));

          for (const q of s.questions || []) {
            const qid = `${subjectId}/${q.id}`;
            if (seenQuestions.has(qid)) { report.errors.push(`duplicate question id ${q.id}`); continue; }
            seenQuestions.add(qid);
            report.questions++;
            db.run(`INSERT INTO questions (id, subject_id, section_key, type, difficulty, marks, data, active)
                    VALUES (?,?,?,?,?,?,?,1)
                    ON CONFLICT(id) DO UPDATE SET section_key=excluded.section_key, type=excluded.type,
                      difficulty=excluded.difficulty, marks=excluded.marks, data=excluded.data, active=1`,
            qid, subjectId, key, q.type || 'problem', q.difficulty || 2, marksOf(q) || 1, JSON.stringify(q));
          }
        }
      }
    }
    // Retire anything no longer on disk without deleting student history.
    for (const r of db.all('SELECT id FROM subjects')) if (!seenSubjects.has(r.id)) db.run('UPDATE subjects SET active=0 WHERE id=?', r.id);
    for (const r of db.all('SELECT key FROM sections')) if (!seenSections.has(r.key)) db.run('UPDATE sections SET active=0 WHERE key=?', r.key);
    for (const r of db.all('SELECT id FROM questions')) if (!seenQuestions.has(r.id)) db.run('UPDATE questions SET active=0 WHERE id=?', r.id);
  });
  return report;
}

module.exports = { renderMarkdown, renderTex, syncContent, marksOf };
