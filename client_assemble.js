#!/usr/bin/env node
/*
 * client_assemble.js -- run the BOARD'S OWN draft engine server-side.
 *
 *   node client_assemble.js <D.json> <index.html>
 *
 * WHY THIS EXISTS
 * ---------------
 * There are two drafters in this repo: assemble_tickets.py (server) and __assembleClient()
 * inside index.html (browser). They implement the same rules, but only the client one decides
 * what a person actually SEES: it re-runs on every page load, locks any ticket whose legs are
 * all confirmed/in-progress, and re-drafts everything else against the current odds, lineups
 * and weather.
 *
 * grade_night.py, meanwhile, grades D_<date>.json -- the SERVER's draft. So any night where the
 * two engines disagreed, the ledger scored legs nobody was shown. That happened on 2026-08-03:
 * a bad rain reading reached one build, the client dropped the three shortest Chef's Table
 * prices, and the archive still said Schwarber/Rice.
 *
 * Rather than keep two implementations in sync by hand forever, the server now runs the client's
 * engine. index.html is the single source of truth for the draft; this file is just a Node shim
 * that gives it the handful of browser globals it touches, hands it the board, and writes the
 * result back. If anything here fails, regen15.py falls back to assemble_tickets.assemble().
 *
 * The engine is pure with respect to the board -- assembleClient(D) reads D and rewrites
 * D.tickets / D.pool. Every network call in index.html lives in liveUpdate()/buildCache(), which
 * we never invoke. Time matters, though: "confirmed / in-progress" is evaluated against the
 * clock, so this must run at build time, not be cached.
 */
'use strict';
const fs = require('fs');

const [, , DJSON, BOARD] = process.argv;
if (!DJSON || !BOARD) { console.error('usage: client_assemble.js <D.json> <index.html>'); process.exit(64); }

// ---- minimal browser surface. Everything is inert: no rendering, no storage, no network. ----
const noop = function () {};
function el() {
  return { addEventListener: noop, removeEventListener: noop, querySelector: el, querySelectorAll: () => [],
    appendChild: noop, removeChild: noop, setAttribute: noop, getAttribute: () => null, removeAttribute: noop,
    insertAdjacentHTML: noop, closest: () => null, click: noop, focus: noop, blur: noop, remove: noop,
    style: {}, dataset: {}, classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    get innerHTML() { return ''; }, set innerHTML(v) {},
    get textContent() { return ''; }, set textContent(v) {},
    get value() { return ''; }, set value(v) {},
    children: [], parentElement: null, firstChild: null, checked: false, options: [] };
}
global.window = {};
global.self = global.window;
global.document = { querySelector: el, querySelectorAll: () => [], getElementById: el, createElement: el,
  createElementNS: el, addEventListener: noop, removeEventListener: noop,
  documentElement: el(), body: el(), head: el(), cookie: '', readyState: 'loading' };
// saveLock()/loadLock() persist ticket locks per browser. Server-side the lock must be derived
// FRESH from the live lineup every build, never inherited -- so this stays a black hole on purpose.
global.localStorage = { getItem: () => null, setItem: noop, removeItem: noop, key: () => null, length: 0, clear: noop };
global.sessionStorage = global.localStorage;
// `navigator` and `fetch` are getter-only builtins on modern Node -- defineProperty past them.
const force = (k, v) => { try { Object.defineProperty(global, k, { value: v, writable: true, configurable: true }); } catch (e) { global[k] = v; } };
force('navigator', { userAgent: 'node' });
force('fetch', () => Promise.reject(new Error('network disabled in server-side draft')));
global.location = { href: 'https://theticketroom.live/', search: '', hash: '', reload: noop, protocol: 'https:' };
force('setTimeout', () => 0); force('clearTimeout', noop);     // kill the liveUpdate refresh loop
force('setInterval', () => 0); force('clearInterval', noop);
global.requestAnimationFrame = () => 0;
global.alert = noop; global.matchMedia = () => ({ matches: false, addEventListener: noop });
global.URL = { createObjectURL: () => '', revokeObjectURL: noop };
global.Blob = function () {};

// ---- pull the board's script block and evaluate it ----
const html = fs.readFileSync(BOARD, 'utf8');
let src = null;
const re = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
for (let m; (m = re.exec(html)); ) if (m[1].indexOf('__assembleClient') >= 0) src = m[1];
if (!src) { console.error('client_assemble: no <script> block defining __assembleClient in ' + BOARD); process.exit(65); }

let bootErr = null;
try { new Function(src)(); } catch (e) { bootErr = e; }   // boot() is DOM-driven and no-ops on the shim

const assemble = global.window.__assembleClient;
if (typeof assemble !== 'function') {
  console.error('client_assemble: __assembleClient not exported' + (bootErr ? ' (' + String(bootErr).slice(0, 120) + ')' : ''));
  process.exit(66);
}

// ---- run it on the real board ----
const D = JSON.parse(fs.readFileSync(DJSON, 'utf8'));
const before = (D.tickets || []).length;
assemble(D);
const after = (D.tickets || []).length;
if (!after) { console.error('client_assemble: engine returned 0 tickets -- refusing to write'); process.exit(67); }

fs.writeFileSync(DJSON, JSON.stringify(D, null, 1));
const locked = (D.tickets || []).filter(t => t.locked).length;
console.log('  client engine: ' + before + ' prior -> ' + after + ' tickets (' + locked + ' locked/confirmed, ' +
  (after - locked) + ' re-drafted)' + (bootErr ? '  [boot noise: ' + String(bootErr).slice(0, 60) + ']' : ''));
