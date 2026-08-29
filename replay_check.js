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
 * THE ASSERTIONS
 * --------------
 *   1. SEALED   a ticket that has locked never changes again -- not its legs, not its
 *               prices -- and only ever leaves the board for one of TWO lawful reasons:
 *               one of its own players is scratched, or one of them is in that build's
 *               chalk ban (CHALKOFF-2026-08-26: "if he's in the top 4 ban he needs to be
 *               taken off ... i dont care if they are locked"). Any other disappearance
 *               is a violation, and a locked slip that CHANGES always is -- CHALKOFF
 *               removes, it never rewrites.
 *               REPLAYCHALK-2026-08-28: the ban is READ FROM THE ENGINE (D.meta.chalk,
 *               published by CHALKOBS-2026-08-28), never recomputed here. A harness that
 *               reimplements the rule it is testing is the assemble_tickets.py mistake in
 *               the worst possible place. If the field is absent the set is empty and
 *               this assertion behaves exactly as it did before -- stricter, never
 *               looser, which is the only safe direction for a test to fail in.
 *   2. NO DUPES no bat sits on two OPEN slips. An anchor legitimately holds both of his
 *               moons and his builder, so anchor legs are exempt; every other leg is not.
 *   3. BAKED    once the slate's DATE has passed in ET the day is OVER, so replaying the final
 *               board the next morning must not change a single ticket. This is its own assertion
 *               because the chain above cannot reach it: the server stops building before midnight,
 *               so no chained build ever crosses the boundary. 2026-08-17 shipped a board that grew
 *               from 17 tickets to 19 at 12:05am -- MINTGUARD compares `gmin(t.lock) <= nowETMin()`,
 *               and `nowETMin()` is MINUTES SINCE ET MIDNIGHT, so a 7:40pm lock (1180) stopped being
 *               "late" the instant the clock read 5. Only a browser tab left open overnight saw it.
 *   5. ANCHORS  the board never carries more than four distinct moon anchors, never leads an OPEN
 *               moon with a scratched bat, and never ships an anchor with a single moon unless his
 *               other one is already a placed bet. This is the postcondition of REDRAFT-2026-08-18:
 *               a scratched anchor REDRAFTS the open board through the joint searchBest, it does not
 *               vacate a chair for the next bat in line. Before that fix, 2026-08-17 spent 72 of its
 *               129 builds on a THREE-anchor, six-moon board because Goodman died and the patch could
 *               not refill him.
 *   4. SHAPE    reports the kind-counts the board settles into. Not a hard failure --
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
  let violations = 0, shapes = {}, removals = [], prevAnchors = 0;

  /* REPLAYCARRY-2026-08-29: the meta fields regen15.py hands forward on a same-slate
     build. They were being discarded here, because `meta` was rebuilt from the archived
     snapshot while only `tickets` was carried -- so in replay every build looked like the
     first of the slate. meta.chalk is the previous ban (CHALKSETTLE-2026-08-29 intersects
     it with today's to decide what it EVICTS for) and meta.chalkever is the night's chalk
     union (LOCKEVICT-2026-08-29). Add a field here when regen15.py starts carrying it. */
  const CARRY_META = ['chalk', 'chalkever'];
  let carryMeta = {};
  for (let i = 1; i < snaps.length; i++) {
    const s = snaps[i];
    /* a build stamped 00:41Z belongs to the NEXT calendar day in UTC */
    const day = (+s.hh < 12)
      ? new Date(new Date(date + 'T00:00:00Z').getTime() + 864e5).toISOString().slice(0, 10)
      : date;
    const clock = `${day}T${s.hh}:${s.mm}:00Z`;
    const D = board(s);
    D.tickets = JSON.parse(JSON.stringify(carry));
    /* REPLAYCARRY-2026-08-29: and the meta production carries, or the chain silently
       replays a slate that never happened -- see CARRY_META above. */
    if (D.meta) for (const k of CARRY_META) if (carryMeta[k] != null) D.meta[k] = carryMeta[k];
    delete D.familyFloor;

    let T;
    try { T = runBuild(engine, D, clock).tickets || []; }
    catch (e) { console.log(`  ${s.hh}:${s.mm}Z  ENGINE ERROR: ${e.message}`); violations++; continue; }
    carry = T;
    if (D.meta) { carryMeta = {}; for (const k of CARRY_META) if (D.meta[k] != null) carryMeta[k] = D.meta[k]; }

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
        /* REPLAYCHALK-2026-08-28: the OTHER lawful removal. Read off the build that did it. */
        const bannedNow = new Set(((D.meta || {}).chalk) || []);
        const banned = sealed[nm].legs.filter(n => bannedNow.has(n));
        if (scratched.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- scratched: ${scratched.join(', ')}`);
        } else if (banned.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- now chalk (CHALKOFF): ${banned.join(', ')}`);
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

    /* (5) ANCHOR SET -- the postcondition of REDRAFT-2026-08-18. A scratched anchor must not leave a
       hole that gets patched: the open board is redrafted, so the board never carries more than four
       distinct moon anchors, never leads an OPEN moon with a dead bat, and never ships an anchor with
       one moon unless his other one is a placed bet (all-or-none). */
    {
      const anchors = {}, lockedAnchor = {};
      T.forEach(t => { if (t.kind !== 'moon' || !t.anchor) return;
        anchors[t.anchor] = (anchors[t.anchor] || 0) + 1;
        if (t.locked) lockedAnchor[t.anchor] = 1; });
      const names = Object.keys(anchors);
      if (names.length > 4) {
        violations++;
        console.log(`  ${s.hh}:${s.mm}Z  TOO MANY ANCHORS: ${names.length} -- ${names.join(', ')}`);
      }
      T.forEach(t => {
        if (t.kind !== 'moon' || t.locked || !t.anchor) return;
        const p = D.players[t.anchor];
        if (!p || p.out || p.void) {
          violations++;
          console.log(`  ${s.hh}:${s.mm}Z  DEAD ANCHOR ON AN OPEN MOON: "${t.name}" led by ${t.anchor}`);
        }
      });
      names.forEach(a => {
        if (anchors[a] !== 2 && !lockedAnchor[a]) {
          violations++;
          console.log(`  ${s.hh}:${s.mm}Z  SHORT ANCHOR: ${a} ships ${anchors[a]} moon(s), none placed`);
        }
      });
      /* THE 2026-08-17 SIGNATURE. A board that carried four anchors and now carries three, while moons are
         still open, means an anchor died and nothing took his seat -- the exact failure REDRAFT-2026-08-18
         exists to kill. Baseline 08-17 spent 72 straight builds here. Only checked while something is still
         open: at the end of the night every moon is locked and the count legitimately reflects what got
         placed, not what could be drafted. */
      const openMoon = T.some(t => t.kind === 'moon' && !t.locked);
      if (prevAnchors >= 4 && names.length < 4 && openMoon) {
        violations++;
        console.log(`  ${s.hh}:${s.mm}Z  ANCHOR SET SHRANK: ${prevAnchors} -> ${names.length} ` +
                    `(${names.join(', ')}) with open moons on the board -- a dead anchor left a hole`);
      }
      prevAnchors = Math.max(prevAnchors, names.length);
      ['late', 'lunch'].forEach(k => {
        const n = T.filter(t => t.kind === k).length;
        if (n > 1) { violations++; console.log(`  ${s.hh}:${s.mm}Z  ${n} ${k} tickets -- the board carries exactly one`); }
      });
    }

    /* (3) shape */
    const c = {};
    T.forEach(t => { c[t.kind] = (c[t.kind] || 0) + 1; });
    const key = Object.keys(c).sort().map(k => k + ':' + c[k]).join(' ');
    shapes[key] = (shapes[key] || 0) + 1;
    if (VERBOSE) console.log(`  ${s.hh}:${s.mm}Z  ${T.length} tickets  ${key}`);
  }

  /* ---- (3) BAKED: the day is over, nothing may move ---- */
  const nextDay = new Date(new Date(date + 'T00:00:00Z').getTime() + 864e5).toISOString().slice(0, 10);
  const lastSnap = snaps[snaps.length - 1];
  const sigList = T => JSON.stringify(T.map(t => [t.kind, t.name, (t.players || []).map(l => [l.name, l.odds])]));
  /* Two inputs, because they are genuinely different boards and only one of them reproduced the
     2026-08-17 incident. `carry` is where OUR chain ended; `archived` is the board the server actually
     committed and therefore the one a browser loads and re-derives overnight. The chained board had
     drifted to a state where the Family Meal had nothing left to add, so testing it alone reported a
     clean pass against the very engine that shipped the bug. Test what the tab holds. */
  const archived = (board(lastSnap).tickets) || [];
  for (const [label, base] of [['chain', carry], ['archived', archived]]) {
  const finalSig = sigList(base);
  /* The board bakes at 3AM ET on the day after the slate (2026-08-18: west coast games can still be
     in progress at 1am ET, so midnight was too early). These clocks must therefore be past 3am ET,
     which is 07:00Z under EDT -- NOT past 00:00Z, and not even past 04:00Z. Two earlier cuts of this
     list got it wrong in both directions: 00:05Z is 8:05pm ET on the slate's OWN day (board is
     supposed to move) and 04:30Z is 12:30am ET (inside the live west-coast window). 07:30Z = 3:30am
     ET is the first clock at which the day is genuinely closed. */
  for (const clock of ['07:30', '12:00', '16:00']) {
    const D2 = board(lastSnap);
    D2.tickets = JSON.parse(JSON.stringify(base));
    delete D2.familyFloor;
    let T2;
    try { T2 = runBuild(engine, D2, `${nextDay}T${clock}:00Z`).tickets || []; }
    catch (e) { violations++; console.log(`  BAKED ${clock}Z  ENGINE ERROR: ${e.message}`); continue; }
    if (sigList(T2) !== finalSig) {
      violations++;
      const was = new Set(base.map(t => t.kind + ':' + t.name));
      const now = new Set(T2.map(t => t.kind + ':' + t.name));
      const added = [...now].filter(x => !was.has(x)), gone = [...was].filter(x => !now.has(x));
      console.log(`  BAKED VIOLATION @ ${nextDay} ${clock}Z [${label}]: the finished board changed ` +
                  `(${base.length} -> ${T2.length} tickets)`);
      added.forEach(x => console.log(`      + ${x}`));
      gone.forEach(x => console.log(`      - ${x}`));
      if (!added.length && !gone.length) console.log('      (same tickets, different legs or prices)');
    }
  }
  }

  if (removals.length) {
    console.log(`  -- ${removals.length} lawful removal(s) (scratch or chalk ban), all accounted for:`);
    removals.forEach(r => console.log(`     ${r}`));
  }
  const shapeList = Object.entries(shapes).sort((a, b) => b[1] - a[1]);
  console.log(`  ${snaps.length - 1} chained builds + 6 post-midnight bake checks | ${violations} violation(s) | ${shapeList.length} board shape(s)`);
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
  ? `PASS -- ${builds} chained builds, no sealed ticket changed, no bat on two open slips, finished boards stay baked.`
  : `FAIL -- ${total} violation(s) across ${builds} chained builds.`);
process.exit(total ? 1 : 0);
