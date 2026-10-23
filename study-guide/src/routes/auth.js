'use strict';
const express = require('express');
const { html } = require('../html');
const { layout, csrfField } = require('../views/layout');
const A = require('../auth');

module.exports = function authRoutes(ctx) {
  const { db, config, mailer } = ctx;
  const r = express.Router();
  const limitLogin = A.rateLimiter({ windowMs: 15 * 60e3, max: 20 });
  const limitMail = A.rateLimiter({ windowMs: 60 * 60e3, max: 8 });

  const page = (req, res, title, active, body, flash, status = 200) =>
    res.status(status).send(String(layout(req, { title, active, body: html`<div class="narrow">${body}</div>`, flash })));

  const emailOk = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e) && e.length <= 200;
  const domainOk = (e) => !config.allowedDomains.length || config.allowedDomains.includes(e.split('@')[1]);

  async function sendVerify(user) {
    const token = A.createToken(db, { userId: user.id, type: 'verify', hours: 48 });
    await mailer.send(user.email, 'Confirm your Study Guide account',
      `Hi ${user.name},\n\nConfirm your email address to start studying:\n${config.appUrl}/verify?token=${token}\n\nThis link expires in 48 hours. If you did not register, ignore this email.`);
  }

  function enrollAll(userId) {
    if (!config.autoEnroll) return;
    for (const s of db.all('SELECT id FROM subjects WHERE active=1')) {
      db.run('INSERT OR IGNORE INTO enrollments (user_id, subject_id) VALUES (?,?)', userId, s.id);
    }
  }

  r.get('/', (req, res) => {
    if (req.user) return res.redirect(req.user.role === 'admin' ? '/admin' : '/dashboard');
    res.send(String(layout(req, {
      title: 'Welcome',
      body: html`
      <section class="grid grid-2" style="align-items:center;margin-top:2rem">
        <div>
          <span class="chip accent">Self-paced learning</span>
          <h1 style="font-size:2.2rem;margin-top:.8rem">Learn at your pace. Practise like it counts.</h1>
          <p class="muted" style="font-size:1.05rem">Clear explanations, worked examples and real-life applications for every topic — then daily, weekly, monthly and on-demand tests made of written and problem-solving questions, with feedback on every answer.</p>
          <div class="form-actions"><a class="btn" href="/register">Create your account</a><a class="btn ghost" href="/login">Sign in</a></div>
        </div>
        <div class="card tint">
          <h3>How it works</h3>
          <ol class="prose">
            <li>Work through each section of the study guide at your own speed.</li>
            <li>Try the self-check problems and reveal the full solutions.</li>
            <li>Take tests: a short daily set, a weekly test, a monthly exam, or build your own.</li>
            <li>Show your working — answers are marked against a rubric and you see the model solution.</li>
            <li>Track your progress by topic. Only you and your teacher can see your results.</li>
          </ol>
        </div>
      </section>`,
    })));
  });

  r.get('/login', (req, res) => {
    if (req.user) return res.redirect('/');
    const flash = req.query.m === 'verified' ? { type: 'ok', text: 'Email confirmed. Sign in to begin.' }
      : req.query.m === 'reset' ? { type: 'ok', text: 'Password updated. Sign in with your new password.' } : null;
    page(req, res, 'Sign in', 'login', loginForm(req, {}), flash);
  });

  function loginForm(req, { email = '', error }) {
    return html`<div class="card">
      <h1>Sign in</h1>
      ${error ? html`<div class="alert err">${error}</div>` : ''}
      <form method="post" action="/login">
        ${csrfField(req)}
        <label for="email">Email</label><input id="email" type="email" name="email" value="${email}" required autocomplete="email">
        <label for="password">Password</label><input id="password" type="password" name="password" required autocomplete="current-password">
        <div class="form-actions"><button type="submit">Sign in</button><a href="/forgot">Forgot password?</a></div>
      </form>
      <hr><p class="muted">New here? <a href="/register">Create an account</a></p>
    </div>`;
  }

  r.post('/login', async (req, res) => {
    const email = String(req.body.email || '').trim().toLowerCase();
    if (!limitLogin(`${req.ip}|${email}`)) return page(req, res, 'Sign in', 'login', loginForm(req, { email, error: 'Too many attempts. Wait 15 minutes and try again.' }), null, 429);
    const user = db.get('SELECT * FROM users WHERE email=?', email);
    if (!user || !A.verifyPassword(String(req.body.password || ''), user.password_hash)) {
      return page(req, res, 'Sign in', 'login', loginForm(req, { email, error: 'That email and password do not match.' }), null, 401);
    }
    if (!user.active) return page(req, res, 'Sign in', 'login', loginForm(req, { email, error: 'This account has been disabled. Contact your teacher.' }), null, 403);
    if (!user.email_verified) {
      if (limitMail(`verify|${email}`)) await sendVerify(user);
      return page(req, res, 'Confirm your email', 'login', html`<div class="card"><h1>Confirm your email</h1><p>We sent a confirmation link to <strong>${email}</strong>. Open it to activate your account, then sign in.</p><p class="muted">No email? Check spam, or ask your teacher to confirm your account.</p></div>`);
    }
    A.startSession(db, res, user.id, config.secureCookies);
    res.redirect(user.role === 'admin' ? '/admin' : '/dashboard');
  });

  r.post('/logout', (req, res) => { A.endSession(db, req, res); res.redirect('/login'); });

  function registerForm(req, { name = '', email = '', invite = '', error }) {
    return html`<div class="card">
      <h1>Create your account</h1>
      <p class="muted">Use your own email address — it is how you confirm your account and reset your password.</p>
      ${error ? html`<div class="alert err">${error}</div>` : ''}
      <form method="post" action="/register">
        ${csrfField(req)}<input type="hidden" name="invite" value="${invite}">
        <label for="name">Your name</label><input id="name" type="text" name="name" value="${name}" required maxlength="80" autocomplete="name">
        <label for="email">Email</label><input id="email" type="email" name="email" value="${email}" required ${invite ? 'readonly' : ''} autocomplete="email">
        <label for="password">Password</label><input id="password" type="password" name="password" required minlength="8" autocomplete="new-password">
        <small>At least 8 characters with letters and numbers.</small>
        <label for="password2">Confirm password</label><input id="password2" type="password" name="password2" required minlength="8" autocomplete="new-password">
        <div class="form-actions"><button type="submit">Create account</button><a href="/login">I already have an account</a></div>
      </form>
    </div>`;
  }

  r.get('/register', (req, res) => {
    if (req.user) return res.redirect('/');
    const invite = String(req.query.invite || '');
    if (invite) {
      const t = A.findToken(db, invite, 'invite');
      if (!t) return page(req, res, 'Register', 'register', html`<div class="card"><h1>Invite link expired</h1><p>Ask your teacher to send a new invite.</p></div>`);
      return page(req, res, 'Register', 'register', registerForm(req, { email: t.email, invite }));
    }
    if (config.registration === 'invite') {
      return page(req, res, 'Register', 'register', html`<div class="card"><h1>Registration is by invite</h1><p>Ask your teacher to send an invite to your email address.</p></div>`);
    }
    page(req, res, 'Register', 'register', registerForm(req, {}));
  });

  r.post('/register', async (req, res) => {
    const name = String(req.body.name || '').trim().slice(0, 80);
    const invite = String(req.body.invite || '');
    let email = String(req.body.email || '').trim().toLowerCase();
    const pw = String(req.body.password || '');
    const form = (error) => page(req, res, 'Register', 'register', registerForm(req, { name, email, invite, error }), null, 400);
    let inviteRow = null;
    if (invite) {
      inviteRow = A.findToken(db, invite, 'invite');
      if (!inviteRow) return form('This invite link has expired.');
      email = inviteRow.email;
    } else if (config.registration === 'invite') return form('Registration is by invite only.');
    if (!limitMail(`register|${req.ip}`)) return form('Too many registrations from this network. Try again later.');
    if (!name) return form('Enter your name.');
    if (!emailOk(email)) return form('Enter a valid email address.');
    if (!inviteRow && !domainOk(email)) return form('Use your school email address.');
    const problem = A.passwordProblem(pw);
    if (problem) return form(problem);
    if (pw !== req.body.password2) return form('The two passwords do not match.');
    const existing = db.get('SELECT * FROM users WHERE email=?', email);
    if (existing && existing.password_hash) return form('An account with this email already exists. Sign in or reset your password.');

    let userId;
    if (existing) {
      db.run('UPDATE users SET name=?, password_hash=? WHERE id=?', name, A.hashPassword(pw), existing.id);
      userId = existing.id;
    } else {
      userId = Number(db.run('INSERT INTO users (email, name, password_hash, role) VALUES (?,?,?,?)', email, name, A.hashPassword(pw), 'student').lastInsertRowid);
    }
    enrollAll(userId);
    const user = db.get('SELECT * FROM users WHERE id=?', userId);
    if (inviteRow) {
      // The invite link proves ownership of the email address.
      A.consumeToken(db, inviteRow.id);
      db.run('UPDATE users SET email_verified=1 WHERE id=?', userId);
      A.startSession(db, res, userId, config.secureCookies);
      return res.redirect('/dashboard');
    }
    await sendVerify(user);
    page(req, res, 'Check your email', 'register', html`<div class="card"><h1>Check your email</h1><p>We sent a confirmation link to <strong>${email}</strong>. Open it to activate your account.</p><p class="muted">The link expires in 48 hours.</p></div>`);
  });

  r.get('/verify', (req, res) => {
    const t = A.findToken(db, String(req.query.token || ''), 'verify');
    if (!t) return page(req, res, 'Link expired', '', html`<div class="card"><h1>That link has expired</h1><p>Sign in and we will send you a fresh confirmation link.</p><a class="btn" href="/login">Sign in</a></div>`);
    A.consumeToken(db, t.id);
    db.run('UPDATE users SET email_verified=1 WHERE id=?', t.user_id);
    res.redirect('/login?m=verified');
  });

  r.get('/forgot', (req, res) => page(req, res, 'Reset password', 'login', html`<div class="card">
    <h1>Reset your password</h1>
    <p class="muted">Enter the email you registered with and we will send you a reset link.</p>
    <form method="post" action="/forgot">${csrfField(req)}
      <label for="email">Email</label><input id="email" type="email" name="email" required autocomplete="email">
      <div class="form-actions"><button type="submit">Send reset link</button><a href="/login">Back to sign in</a></div>
    </form></div>`));

  r.post('/forgot', async (req, res) => {
    const email = String(req.body.email || '').trim().toLowerCase();
    if (limitMail(`reset|${req.ip}`) && limitMail(`reset|${email}`)) {
      const user = db.get('SELECT * FROM users WHERE email=? AND active=1', email);
      if (user) {
        const token = A.createToken(db, { userId: user.id, type: 'reset', hours: 2 });
        await mailer.send(user.email, 'Reset your Study Guide password',
          `Hi ${user.name},\n\nUse this link to choose a new password:\n${config.appUrl}/reset?token=${token}\n\nThe link expires in 2 hours. If you did not ask for this, you can ignore this email — your password will not change.`);
      }
    }
    // Same response whether or not the account exists.
    page(req, res, 'Check your email', 'login', html`<div class="card"><h1>Check your email</h1><p>If an account exists for <strong>${email}</strong>, a reset link is on its way. It expires in 2 hours.</p></div>`);
  });

  function resetForm(req, token, error) {
    return html`<div class="card"><h1>Choose a new password</h1>
      ${error ? html`<div class="alert err">${error}</div>` : ''}
      <form method="post" action="/reset">${csrfField(req)}<input type="hidden" name="token" value="${token}">
        <label for="password">New password</label><input id="password" type="password" name="password" required minlength="8" autocomplete="new-password">
        <label for="password2">Confirm new password</label><input id="password2" type="password" name="password2" required minlength="8" autocomplete="new-password">
        <div class="form-actions"><button type="submit">Update password</button></div>
      </form></div>`;
  }

  r.get('/reset', (req, res) => {
    const token = String(req.query.token || '');
    if (!A.findToken(db, token, 'reset')) return page(req, res, 'Link expired', '', html`<div class="card"><h1>That link has expired</h1><p>Request a new reset link.</p><a class="btn" href="/forgot">Reset password</a></div>`);
    page(req, res, 'New password', '', resetForm(req, token));
  });

  r.post('/reset', (req, res) => {
    const token = String(req.body.token || '');
    const t = A.findToken(db, token, 'reset');
    if (!t) return page(req, res, 'Link expired', '', html`<div class="card"><h1>That link has expired</h1><a class="btn" href="/forgot">Request a new link</a></div>`, null, 400);
    const pw = String(req.body.password || '');
    const problem = A.passwordProblem(pw) || (pw !== req.body.password2 ? 'The two passwords do not match.' : null);
    if (problem) return page(req, res, 'New password', '', resetForm(req, token, problem), null, 400);
    A.consumeToken(db, t.id);
    db.run('UPDATE users SET password_hash=?, email_verified=1 WHERE id=?', A.hashPassword(pw), t.user_id);
    A.endAllSessions(db, t.user_id);
    res.redirect('/login?m=reset');
  });

  return r;
};
