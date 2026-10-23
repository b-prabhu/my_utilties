'use strict';
const crypto = require('crypto');

const SESSION_DAYS = 14;
const COOKIE = 'sg_session';

function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$${salt.toString('hex')}$${hash.toString('hex')}`;
}

function verifyPassword(password, stored) {
  if (!stored || !stored.startsWith('scrypt$')) return false;
  const [, saltHex, hashHex] = stored.split('$');
  const expected = Buffer.from(hashHex, 'hex');
  const actual = crypto.scryptSync(password, Buffer.from(saltHex, 'hex'), expected.length, { N: 16384, r: 8, p: 1 });
  return crypto.timingSafeEqual(expected, actual);
}

const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');
const randomToken = () => crypto.randomBytes(32).toString('base64url');

function passwordProblem(pw) {
  if (typeof pw !== 'string' || pw.length < 8) return 'Password must be at least 8 characters.';
  if (pw.length > 200) return 'Password is too long.';
  if (!/[A-Za-z]/.test(pw) || !/[0-9]/.test(pw)) return 'Password must contain letters and numbers.';
  return null;
}

// One-time tokens for email verification, password reset and invites.
function createToken(db, { userId = null, email = null, type, hours }) {
  const token = randomToken();
  db.run('UPDATE tokens SET used=1 WHERE type=? AND ((user_id IS NOT NULL AND user_id=?) OR (email IS NOT NULL AND email=?)) AND used=0',
    type, userId, email);
  db.run('INSERT INTO tokens (user_id, email, type, token_hash, expires_at) VALUES (?,?,?,?,?)',
    userId, email, type, sha256(token), Date.now() + hours * 3600e3);
  return token;
}

function findToken(db, token, type) {
  if (!token) return null;
  const row = db.get('SELECT * FROM tokens WHERE token_hash=? AND type=?', sha256(String(token)), type);
  if (!row || row.used || row.expires_at < Date.now()) return null;
  return row;
}

function consumeToken(db, id) {
  db.run('UPDATE tokens SET used=1 WHERE id=?', id);
}

function parseCookies(header) {
  const out = {};
  for (const part of (header || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

function startSession(db, res, userId, secure) {
  const token = randomToken();
  const csrf = randomToken();
  const expires = Date.now() + SESSION_DAYS * 86400e3;
  db.run('INSERT INTO sessions (token_hash, user_id, csrf, expires_at) VALUES (?,?,?,?)', sha256(token), userId, csrf, expires);
  db.run("UPDATE users SET last_login=datetime('now') WHERE id=?", userId);
  res.cookie(COOKIE, token, { httpOnly: true, sameSite: 'lax', secure, maxAge: SESSION_DAYS * 86400e3, path: '/' });
}

function endSession(db, req, res) {
  const token = parseCookies(req.headers.cookie)[COOKIE];
  if (token) db.run('DELETE FROM sessions WHERE token_hash=?', sha256(token));
  res.clearCookie(COOKIE, { path: '/' });
}

function endAllSessions(db, userId) {
  db.run('DELETE FROM sessions WHERE user_id=?', userId);
}

// Attaches req.user and req.csrf. Anonymous visitors get a CSRF token in a
// separate cookie so login/register forms are protected too.
function sessionMiddleware(db) {
  return (req, res, next) => {
    const cookies = parseCookies(req.headers.cookie);
    req.user = null;
    const token = cookies[COOKIE];
    if (token) {
      const s = db.get('SELECT * FROM sessions WHERE token_hash=?', sha256(token));
      if (s && s.expires_at > Date.now()) {
        const u = db.get('SELECT * FROM users WHERE id=? AND active=1', s.user_id);
        if (u) { req.user = u; req.csrf = s.csrf; }
      } else if (s) {
        db.run('DELETE FROM sessions WHERE token_hash=?', s.token_hash);
      }
    }
    if (!req.user) {
      let anon = cookies.sg_csrf;
      if (!anon || !/^[A-Za-z0-9_-]{20,}$/.test(anon)) {
        anon = randomToken();
        res.cookie('sg_csrf', anon, { httpOnly: true, sameSite: 'lax', secure: req.secure, path: '/' });
      }
      req.csrf = anon;
    }
    next();
  };
}

function csrfGuard(req, res, next) {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
  const sent = (req.body && req.body._csrf) || req.get('x-csrf-token');
  if (!sent || !req.csrf || sent.length !== req.csrf.length ||
      !crypto.timingSafeEqual(Buffer.from(sent), Buffer.from(req.csrf))) {
    return res.status(403).send('Your session expired or the form was out of date. Go back, refresh the page and try again.');
  }
  next();
}

// Fixed-window limiter keyed by IP + bucket; enough to blunt password guessing.
function rateLimiter({ windowMs, max }) {
  const hits = new Map();
  return (key) => {
    const now = Date.now();
    const h = hits.get(key);
    if (!h || h.reset < now) { hits.set(key, { n: 1, reset: now + windowMs }); return true; }
    h.n++;
    if (hits.size > 10000) for (const [k, v] of hits) if (v.reset < now) hits.delete(k);
    return h.n <= max;
  };
}

module.exports = {
  hashPassword, verifyPassword, passwordProblem, createToken, findToken, consumeToken,
  startSession, endSession, endAllSessions, sessionMiddleware, csrfGuard, rateLimiter, sha256,
};
