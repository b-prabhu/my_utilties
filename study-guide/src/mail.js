'use strict';
// Sends email through SMTP when configured. Every message is also written to
// the outbox table so the admin can see (and resend) what went out – handy
// when SMTP is not set up yet.
const nodemailer = require('nodemailer');

function createMailer(db, config) {
  let transport = null;
  if (config.smtpUrl) transport = nodemailer.createTransport(config.smtpUrl);
  else if (config.smtpHost) {
    transport = nodemailer.createTransport({
      host: config.smtpHost,
      port: config.smtpPort,
      secure: config.smtpPort === 465,
      auth: config.smtpUser ? { user: config.smtpUser, pass: config.smtpPass } : undefined,
    });
  }

  async function send(to, subject, text) {
    const row = db.run('INSERT INTO outbox (to_email, subject, body) VALUES (?,?,?)', to, subject, text);
    if (!transport) {
      if (!config.quiet) console.log(`\n[mail:not-configured] To: ${to}\nSubject: ${subject}\n${text}\n`);
      return { delivered: false };
    }
    try {
      await transport.sendMail({ from: config.mailFrom, to, subject, text });
      db.run('UPDATE outbox SET delivered=1 WHERE id=?', row.lastInsertRowid);
      return { delivered: true };
    } catch (e) {
      db.run('UPDATE outbox SET error=? WHERE id=?', String(e.message).slice(0, 500), row.lastInsertRowid);
      console.error('[mail] failed:', e.message);
      return { delivered: false, error: e.message };
    }
  }

  return { send, configured: !!transport };
}

module.exports = { createMailer };
