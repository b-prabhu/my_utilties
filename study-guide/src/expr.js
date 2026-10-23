'use strict';
// Tiny, safe arithmetic evaluator for randomised question templates.
// Supports numbers, identifiers, + - * / ^, parentheses, unary minus and a
// small whitelist of functions. No access to JS globals.

const FUNCS = {
  sqrt: Math.sqrt,
  abs: Math.abs,
  min: Math.min,
  max: Math.max,
  round: Math.round,
  floor: Math.floor,
  ceil: Math.ceil,
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  asin: Math.asin,
  acos: Math.acos,
  atan: Math.atan,
  exp: Math.exp,
  ln: Math.log,
  log: Math.log10,
  logb: (b, x) => Math.log(x) / Math.log(b),
};
const CONSTS = { pi: Math.PI, e: Math.E };

function tokenize(src) {
  const tokens = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) { i++; continue; }
    if (/[0-9.]/.test(c)) {
      const m = /^(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/i.exec(src.slice(i));
      if (!m) throw new Error(`Bad number at ${i} in "${src}"`);
      tokens.push({ t: 'num', v: parseFloat(m[0]) });
      i += m[0].length;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
      tokens.push({ t: 'id', v: m[0] });
      i += m[0].length;
      continue;
    }
    if ('+-*/^(),'.includes(c)) { tokens.push({ t: c }); i++; continue; }
    throw new Error(`Unexpected "${c}" in "${src}"`);
  }
  return tokens;
}

function evaluate(src, scope = {}) {
  const tokens = tokenize(String(src));
  let pos = 0;
  const peek = () => tokens[pos];
  const take = (t) => {
    const tok = tokens[pos];
    if (!tok || (t && tok.t !== t)) throw new Error(`Expected ${t || 'token'} in "${src}"`);
    pos++;
    return tok;
  };

  function expr() {
    let v = term();
    while (peek() && (peek().t === '+' || peek().t === '-')) {
      const op = take().t;
      const r = term();
      v = op === '+' ? v + r : v - r;
    }
    return v;
  }
  function term() {
    let v = unary();
    while (peek() && (peek().t === '*' || peek().t === '/')) {
      const op = take().t;
      const r = unary();
      v = op === '*' ? v * r : v / r;
    }
    return v;
  }
  function unary() {
    if (peek() && peek().t === '-') { take(); return -unary(); }
    if (peek() && peek().t === '+') { take(); return unary(); }
    return power();
  }
  function power() {
    const base = atom();
    if (peek() && peek().t === '^') { take(); return Math.pow(base, unary()); }
    return base;
  }
  function atom() {
    const tok = take();
    if (tok.t === 'num') return tok.v;
    if (tok.t === '(') { const v = expr(); take(')'); return v; }
    if (tok.t === 'id') {
      if (peek() && peek().t === '(') {
        const fn = FUNCS[tok.v];
        if (!fn) throw new Error(`Unknown function ${tok.v}`);
        take('(');
        const args = [];
        if (peek() && peek().t !== ')') {
          args.push(expr());
          while (peek() && peek().t === ',') { take(); args.push(expr()); }
        }
        take(')');
        return fn(...args);
      }
      if (Object.prototype.hasOwnProperty.call(scope, tok.v)) return scope[tok.v];
      if (Object.prototype.hasOwnProperty.call(CONSTS, tok.v)) return CONSTS[tok.v];
      throw new Error(`Unknown variable ${tok.v} in "${src}"`);
    }
    throw new Error(`Unexpected token in "${src}"`);
  }

  const v = expr();
  if (pos !== tokens.length) throw new Error(`Trailing input in "${src}"`);
  return v;
}

// Round to significant digits and format without exponent for typical values.
function formatSig(value, sig) {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return '0';
  if (!sig) {
    return String(Math.round(value * 1e6) / 1e6);
  }
  const mag = Math.floor(Math.log10(Math.abs(value)));
  const decimals = sig - 1 - mag;
  const factor = Math.pow(10, decimals);
  const rounded = Math.round(value * factor) / factor;
  if (decimals > 0) return rounded.toFixed(Math.min(decimals, 10));
  return String(Math.round(rounded));
}

function pickVar(spec, rand) {
  if (Array.isArray(spec.choices)) return spec.choices[Math.floor(rand() * spec.choices.length)];
  const step = spec.step || 1;
  const n = Math.floor((spec.max - spec.min) / step + 1e-9);
  const v = spec.min + Math.floor(rand() * (n + 1)) * step;
  return Math.round(v * 1e9) / 1e9;
}

// Build a scope of variable values for a question. `fixed` lets us reproduce
// a previously generated instance.
const DECIMALS = Symbol('decimals');
const decimalsOf = (n) => { const m = /\.(\d+)/.exec(String(n)); return m ? m[1].length : 0; };

function buildScope(question, rand = Math.random, fixed = null) {
  const scope = {};
  const vars = question.vars || {};
  const dec = {};
  for (const [k, spec] of Object.entries(vars)) {
    scope[k] = fixed && k in fixed ? fixed[k] : pickVar(spec, rand);
    // Show a randomised value with the precision its range implies (2.0 not 2).
    dec[k] = Array.isArray(spec.choices) ? Math.max(0, ...spec.choices.map(decimalsOf))
      : Math.max(decimalsOf(spec.step || 1), decimalsOf(spec.min), spec.decimals || 0);
  }
  Object.defineProperty(scope, DECIMALS, { value: dec });
  for (const [k, ex] of Object.entries(question.derived || {})) {
    scope[k] = evaluate(ex, scope);
  }
  return scope;
}

function varValues(question, scope) {
  const out = {};
  for (const k of Object.keys(question.vars || {})) out[k] = scope[k];
  return out;
}

function fill(text, scope) {
  if (!text) return text;
  return String(text).replace(/\{\{([^}:]+)(?::(\d+))?\}\}/g, (_, ex, sig) => {
    const name = ex.trim();
    const v = evaluate(name, scope);
    const dec = scope[DECIMALS] && scope[DECIMALS][name];
    if (!sig && dec) return v.toFixed(dec);
    return formatSig(v, sig ? parseInt(sig, 10) : 0);
  });
}

// Read a student's typed final answer. Exact forms such as "3/4", "-√3/2",
// "2π/3" or "sqrt(2)/2" are evaluated; otherwise the first number is used, so
// "4.9 N [up]" -> 4.9, "1.2e3" -> 1200 and "6 000 N" -> 6000.
function parseNumber(input) {
  if (input == null) return null;
  const s = String(input).trim().replace(/(\d)[\s,](?=\d{3}\b)/g, '$1').replace(/×\s*10\^?\s*(-?\d+)/, 'e$1');
  const exact = s.replace(/[−–]/g, '-').replace(/√\s*\(?([0-9.]+)\)?/g, 'sqrt($1)').replace(/π/g, 'pi')
    .replace(/(\d|\))\s*(pi|sqrt)/g, '$1*$2').replace(/×|·/g, '*').replace(/\s+/g, '');
  if (/^[-+*/^().\d]*(?:(?:pi|sqrt)[-+*/^().\d]*)*$/.test(exact) && /\d|pi/.test(exact)) {
    try {
      const v = evaluate(exact);
      if (Number.isFinite(v)) return v;
    } catch { /* fall through to first number */ }
  }
  const m = /-?\d*\.?\d+(?:e[+-]?\d+)?/i.exec(s);
  return m ? parseFloat(m[0]) : null;
}

function checkNumeric(expected, input, tol = 0.02) {
  const got = parseNumber(input);
  if (got == null) return false;
  if (expected === 0) return Math.abs(got) < 1e-9;
  // Accept magnitude when a direction is written in words instead of a sign.
  return Math.abs(got - expected) <= Math.abs(expected) * tol ||
    Math.abs(Math.abs(got) - Math.abs(expected)) <= Math.abs(expected) * tol;
}

module.exports = { evaluate, formatSig, buildScope, varValues, fill, parseNumber, checkNumeric };
