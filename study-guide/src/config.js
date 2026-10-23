'use strict';
const path = require('path');
const fs = require('fs');

// Minimal .env loader (KEY=VALUE lines) so no extra dependency is needed.
function loadDotEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
    if (!m || line.trim().startsWith('#')) continue;
    let v = m[2];
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    if (!(m[1] in process.env)) process.env[m[1]] = v;
  }
}

function loadConfig(overrides = {}) {
  const root = path.join(__dirname, '..');
  loadDotEnv(path.join(root, '.env'));
  const env = process.env;
  const port = Number(env.PORT || 3000);
  const cfg = {
    port,
    appUrl: (env.APP_URL || `http://localhost:${port}`).replace(/\/$/, ''),
    dbFile: env.DB_FILE || path.join(env.DATA_DIR || path.join(root, 'data'), 'study-guide.db'),
    uploadsDir: env.UPLOADS_DIR || path.join(env.DATA_DIR || path.join(root, 'data'), 'uploads'),
    contentDir: env.CONTENT_DIR || path.join(root, 'content'),
    adminEmail: (env.ADMIN_EMAIL || '').trim().toLowerCase(),
    adminPassword: env.ADMIN_PASSWORD || '',
    adminName: env.ADMIN_NAME || 'Admin',
    registration: (env.REGISTRATION || 'open').toLowerCase(), // open | invite
    allowedDomains: (env.ALLOWED_EMAIL_DOMAINS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean),
    autoEnroll: env.AUTO_ENROLL !== 'false',
    smtpUrl: env.SMTP_URL || '',
    smtpHost: env.SMTP_HOST || '',
    smtpPort: Number(env.SMTP_PORT || 587),
    smtpUser: env.SMTP_USER || '',
    smtpPass: env.SMTP_PASS || '',
    mailFrom: env.MAIL_FROM || 'Study Guide <no-reply@localhost>',
    anthropicKey: env.ANTHROPIC_API_KEY || '',
    aiModel: env.AI_MODEL || 'claude-sonnet-5-5',
    trustProxy: env.TRUST_PROXY === 'true',
    secureCookies: env.COOKIE_SECURE ? env.COOKIE_SECURE === 'true' : (env.APP_URL || '').startsWith('https://'),
    quiet: false,
    ...overrides,
  };
  return cfg;
}

module.exports = { loadConfig };
