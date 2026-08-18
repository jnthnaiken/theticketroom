#!/usr/bin/env node
/*
 * replay_check.js -- regression test for the client draft/lock engine in index.html.
 *
 *   node replay_check.js                     # yesterday and today
 *   node replay_check.js 2026-08-17          # one date
 *   node replay_check.js 2026-08-17 2026-08-16
 *   node replay_check.js --verbose 2026-08-17
 *
 * WHY THIS EXISTS
 * ---------------
 * 2026-08-17. Four separate bugs shipped or survived because every diagnosis was a
 * plausible story nobody measured. This replays REAL boards through the REAL engine and
 * turns the stories into numbers. On the day it was written it found:
 *   - the shrink guard fired 94 times in 58 builds, and 93 of those restores put a bat on
 *     the board that was already on another slip
 *   - 64 changes to tickets that were already showing the lock badge, on 2026-08-16 alone
 *   - and that a fix I was about to ship (FAMLOCK) changed nothing at all
 *
 * HOW IT WORKS
 * ------------
 * Every board build is committed as `D_<date>.json`, so git history IS the test corpus.
 * The engine is `assembleClient()` inside index.html's big <script>; this pulls that block
 * out, runs it in a `vm` sandbox with DOM stubs and a frozen Date, and calls it directly.
 *
 * The replay is CHAINED: build N's output becomes build N+1's prior board, which is how
 * production actually works -- regen15.py takes the prior board from index.html's `const D`,
 * NOT from D_<date>.json (that file is an output). Testing each build against the archived
 * prior would hide exactly the drift this is looking for.
 *
 * Player data (lineups, odds, TOTALs, scratches) comes from each snapshot, so the replay
 * sees the same live inputs the build saw.
 *
 * THE THREE ASSERTIONS
 * --------------------
 *   1. SEALED   a ticket that has locked never changes again -- not its legs, not its
 *               prices -- and only ever leaves the board when one of its own players is
 *               scratched. Any other disappearance is a violation.
 *   2. NO DUPES no bat sits on two OPEN slips. An anchor legitimately holds both of his
 *               moons and his builder, so anchor legs are exempt; every other leg is not.
 *   3. SHAPE    reports the kind-counts the board settles into. Not a hard failure --
 *               `family` is a leftovers section and is supposed to vary, and scratches
 *               legitimately remove slips -- but churn here means something is wrong.
 *               2026-08-16 runs all 170 builds on ONE shape. That is what healthy looks like.
 *
 * Exit code 0 = clean, 1 = violations, 2 = could not run. Safe to wire into CI.
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const { execSync } = require('child_process');

const args = process.argv.slice(2);
const VERBOSE = args.includes('--verbose');
let dates = args.filter(a => /^\d{4}-\d{2}-\d{2}$/.test(a));
if (!dates.length) {
  const d = new Date();
  const iso = t => t.toISOString().slice(0, 10);
  dates = [iso(d), iso(new Date(d.getTime() - 864e5))];
}

/* ---------- pull assembleClient out of index.html ---------- */
function loadEngine(file) {
  const html = fs.readFileSync(file, 'utf8');
  let best = null;
  const re = /<script[^>]*>/g;
  let m;
  while ((m = re.exec(html))) {
    const st = m.index + m[0].length;
    const en = html.indexOf('</script>', st);
    if (en < 0) continue;
    if (!best || en - st > best[1] - best[0]) best = [st, en];
  }
  if (!best) throw new Error('no <script> block found in ' + file);
  const src = html.slice(best[0], best[1]);
  /* assembleClient is nested inside an IIFE, so it is not a global. Function
     declarations hoist within their own scope, so an assignment placed just
     before the declaration captures it as soon as that scope runs. */
  const decl = '  function assembleClient(D){';
  const at = src.indexOf(decl);
  if (at < 0) throw new Error('assembleClient not found -- did the indentation change?');
  return src.slice(0, at) + '  try{globalThis.__ac=assembleClient;}catch(e){}\n' + src.slice(at);
}

/* ---------- run one build ---------- */
function runBuild(engine, D, isoClock) {
  const RealDate = Date;
  const FIXED = new RealDate(isoClock).getTime();
  class FakeDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(FIXED); else super(...a); }
    static now() { return FIXED; }
  }
  const el = () => new Proxy(function () {}, {
    get(t, k) {
      if (k === 'style') return {};
      if (k === 'classList') return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
      if (k === 'children' || k === 'childNodes') return [];
      if (k === 'dataset') return {};
      if (typeof k === 'symbol') return undefined;
      if (k === 'innerHTML' || k === 'textContent' || k === 'value' ||
          k === 'id' || k === 'className' || k === 'innerText') return '';
      return el();
    },
    set() { return true; },
    apply() { return el(); },
  });
  const document = {
    getElementById: () => el(), querySelector: () => el(), querySelectorAll: () => [],
    createElement: () => el(), createTextNode: () => el(), addEventListener() {},
    body: el(), documentElement: el(), head: el(), cookie: '',
  };
  const noStore = { getItem: () => null, setItem() {}, removeItem() {} };
  const ctx = {
    console: { log() {}, warn() {}, error() {} },
    Date: FakeDate, document, navigator: { userAgent: 'node' },
    location: { href: 'https://theticketroom.live/', search: '', hash: '' },
    localStorage: noStore, sessionStorage: noStore,
    fetch: () => Promise.reject(new Error('offline')),
    setTimeout() {}, setInterval() {}, clearTimeout() {}, clearInterval() {},
    requestAnimationFrame() {}, alert() {},
    Math, JSON, parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
  };
  ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
  vm.createContext(ctx);
  /* the page's top-level render code runs too and may throw against the DOM stubs --
     harmless, the hook has already captured the function we want */
  try { vm.runInContext(engine, ctx, { filename: 'index.html' }); }
  catch (e) { if (!ctx.__ac) throw e; }
  if (typeof ctx.__ac !== 'function') throw new Error('assembleClient never initialised');
  ctx.__ac(D);
  return D;
}

/* ---------- board snapshots, oldest first, straight out of git ---------- */
function snapshots(date) {
  const file = 'D_' + date + '.json';
  let log;
  try { log = execSync(`git log --format=%h%x09%s -- ${file}`, { encoding: 'utf8', maxBuffer: 1 << 26 }); }
  catch (e) { return []; }
  const out = [];
  for (const line of log.split('\n')) {
    if (!line.trim()) continue;
    const [sha, subject] = line.split('\t');
    const m = /\((\d{2}):(\d{2})Z\)/.exec(subject || '');
    if (!m) continue;                       // only automated builds carry a timestamp
    out.push({ sha, hh: m[1], mm: m[2] });
  }
  out.reverse();                            // git log is newest-first
  return out;
}

const sigOf = t => JSON.stringify([
  t.kind, (t.players || []).map(l => [l.name, l.odds]),
]);

/* ---------- replay one date ---------- */
function replay(engine, date) {
  const snaps = snapshots(date);
  if (snaps.length < 2) {
    console.log(`${date}: ${snaps.length} board(s) in git history -- nothing to chain, skipped`);
    return { violations: 0, builds: 0, skipped: true };
  }
  const board = s => JSON.parse(execSync(`git show ${s.sha}:D_${date}.json`, { encoding: 'utf8', maxBuffer: 1 << 28 }));

  let carry = board(snaps[0]).tickets || [];
  const sealed = {};        // name -> { sig, legs }
  let violations = 0, shapes = {}, removals = [];

  for (let i = 1; i < snaps.length; i++) {
    const s = snaps[i];
    /* a build stamped 00:41Z belongs to the NEXT calendar day in UTC */
    const day = (+s.hh < 12)
      ? new Date(new Date(date + 'T00:00:00Z').getTime() + 864e5).toISOString().slice(0, 10)
      : date;
    const clock = `${day}T${s.hh}:${s.mm}:00Z`;
    const D = board(s);
    D.tickets = JSON.parse(JSON.stringify(carry));
    delete D.familyFloor;

    let T;
    try { T = runBuild(engine, D, clock).tickets || []; }
    catch (e) { console.log(`  ${s.hh}:${s.mm}Z  ENGINE ERROR: ${e.message}`); violations++; continue; }
    carry = T;

    const live = {};
    T.forEach(t => { live[t.name] = t; });

    /* (1) sealed tickets */
    for (const nm of Object.keys(sealed)) {
      const x = live[nm];
      if (!x) {
        const scratched = sealed[nm].legs.filter(n => {
          const p = D.players[n];
          return !p || p.out || p.void;
        });
        if (scratched.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- scratched: ${scratched.join(', ')}`);
        } else {
          violations++;
          console.log(`  ${s.hh}:${s.mm}Z  SEALED TICKET VANISHED: "${nm}" -- every leg still alive`);
        }
        delete sealed[nm];
        continue;
      }
      if (sigOf(x) !== sealed[nm].sig) {
        violations++;
        console.log(`  ${s.hh}:${s.mm}Z  SEALED TICKET CHANGED: "${nm}"`);
        console.log(`             was ${sealed[nm].sig}`);
        console.log(`             now ${sigOf(x)}`);
        sealed[nm].sig = sigOf(x);           // report once, keep going
      }
    }
    T.forEach(t => {
      if (t.locked && !(t.name in sealed)) {
        sealed[t.name] = { sig: sigOf(t), legs: (t.players || []).map(l => l.name) };
      }
    });

    /* (2) a bat on two open slips (anchors are exempt on their own slips) */
    const seen = {};
    T.forEach(t => {
      if (t.locked) return;
      (t.players || []).forEach(l => {
        if (l.name === t.anchor) return;
        (seen[l.name] = seen[l.name] || []).push(t.name);
      });
    });
    const dupes = Object.keys(seen).filter(n => seen[n].length > 1);
    if (dupes.length) {
      violations++;
      dupes.forEach(n => console.log(`  ${s.hh}:${s.mm}Z  DUPLICATE: ${n} on ${seen[n].join(' + ')}`));
    }

    /* (3) shape */
    const c = {};
    T.forEach(t => { c[t.kind] = (c[t.kind] || 0) + 1; });
    const key = Object.keys(c).sort().map(k => k + ':' + c[k]).join(' ');
    shapes[key] = (shapes[key] || 0) + 1;
    if (VERBOSE) console.log(`  ${s.hh}:${s.mm}Z  ${T.length} tickets  ${key}`);
  }

  if (removals.length) {
    console.log(`  -- ${removals.length} scratch-driven removal(s), all accounted for:`);
    removals.forEach(r => console.log(`     ${r}`));
  }
  const shapeList = Object.entries(shapes).sort((a, b) => b[1] - a[1]);
  console.log(`  ${snaps.length - 1} chained builds | ${violations} violation(s) | ${shapeList.length} board shape(s)`);
  shapeList.slice(0, 5).forEach(([k, n]) => console.log(`     ${String(n).padStart(4)}x  ${k}`));
  if (shapeList.length > 5) console.log(`     ... and ${shapeList.length - 5} more`);
  return { violations, builds: snaps.length - 1 };
}

/* ---------- main ---------- */
try {
  execSync('git rev-parse --git-dir', { stdio: 'ignore' });
} catch (e) {
  console.error('replay_check: not inside the repo -- run it from the repo root.');
  process.exit(2);
}
if (!fs.existsSync('index.html')) {
  console.error('replay_check: index.html not found -- run it from the repo root.');
  process.exit(2);
}

let engine;
try { engine = loadEngine('index.html'); }
catch (e) { console.error('replay_check: ' + e.message); process.exit(2); }

console.log('replay_check -- chained replay of the live engine over archived boards\n');
let total = 0, builds = 0;
for (const d of dates) {
  console.log(d + ':');
  const r = replay(engine, d);
  total += r.violations; builds += r.builds;
  console.log('');
}
if (!builds) {
  console.log('No boards to replay. Pass a date that has D_<date>.json commits, e.g.');
  console.log('  node replay_check.js 2026-08-17');
  process.exit(0);
}
console.log(total === 0
  ? `PASS -- ${builds} chained builds, no sealed ticket changed, no bat on two open slips.`
  : `FAIL -- ${total} violation(s) across ${builds} chained builds.`);
process.exit(total ? 1 : 0);
