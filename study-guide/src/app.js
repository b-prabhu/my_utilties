'use strict';
const path = require('path');
const express = require('express');
const { open } = require('./db');
const { syncContent } = require('./content');
const { createMailer } = require('./mail');
const A = require('./auth');
const grader = require('./grader');
const { html } = require('./html');
const { layout } = require('./views/layout');

function ensureAdmin(db, config) {
  if (!config.adminEmail) return;
  const existing = db.get('SELECT * FROM users WHERE email=?', config.adminEmail);
  if (existing) {
    if (existing.role !== 'admin') db.run("UPDATE users SET role='admin', email_verified=1 WHERE id=?", existing.id);
    return;
  }
  const hash = config.adminPassword ? A.hashPassword(config.adminPassword) : null;
  const r = db.run("INSERT INTO users (email, name, password_hash, role, email_verified) VALUES (?,?,?,'admin',1)",
    config.adminEmail, config.adminName, hash);
  if (!hash) {
    const token = A.createToken(db, { userId: Number(r.lastInsertRowid), type: 'reset', hours: 72 });
    console.log(`\nAdmin account created for ${config.adminEmail}. Set its password here:\n${config.appUrl}/reset?token=${token}\n`);
  }
}

function createApp(config) {
  const db = open(config.dbFile);
  const rep = syncContent(db, config.contentDir);
  if (!config.quiet) {
    console.log(`Content: ${rep.subjects} subjects, ${rep.sections} sections, ${rep.questions} questions.`);
    for (const e of rep.errors) console.warn(`Content problem: ${e}`);
  }
  ensureAdmin(db, config);
  const mailer = createMailer(db, config);
  const ctx = { db, config, mailer, grader };

  const app = express();
  app.disable('x-powered-by');
  if (config.trustProxy) app.set('trust proxy', 1);
  app.use((req, res, next) => {
    res.set('X-Content-Type-Options', 'nosniff');
    res.set('X-Frame-Options', 'DENY');
    res.set('Referrer-Policy', 'same-origin');
    next();
  });
  app.use('/static', express.static(path.join(__dirname, '..', 'public'), { maxAge: '1h' }));
  app.use('/vendor/katex', express.static(path.join(path.dirname(require.resolve('katex/package.json')), 'dist'), { maxAge: '7d' }));
  app.use(express.urlencoded({ extended: false, limit: '2mb' }));
  app.use(express.json({ limit: '8mb' }));
  app.use(A.sessionMiddleware(db));
  app.use(A.csrfGuard);

  app.use(require('./routes/auth')(ctx));
  app.use(require('./routes/student')(ctx));
  app.use('/admin', require('./routes/admin')(ctx));

  app.use((req, res) => res.status(404).send(String(layout(req, { title: 'Not found', body: html`<div class="card"><h1>Page not found</h1><p><a href="/">Go home</a></p></div>` }))));
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    console.error(err);
    res.status(500).send(String(layout(req, { title: 'Error', body: html`<div class="card"><h1>Something went wrong</h1><p>Please try again. If it keeps happening, tell your teacher.</p></div>` })));
  });

  // Hourly: tidy expired sessions/tokens.
  const timer = setInterval(() => {
    db.run('DELETE FROM sessions WHERE expires_at < ?', Date.now());
    db.run('DELETE FROM tokens WHERE expires_at < ?', Date.now() - 7 * 86400e3);
  }, 3600e3);
  timer.unref();

  return { app, db, ctx };
}

module.exports = { createApp };
