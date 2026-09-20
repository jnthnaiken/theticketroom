#!/usr/bin/env node
/* test_nfl_kicklock.js -- KICKLOCK-2026-09-20.
 *
 * WHY. On 2026-09-20 the football board shipped `locked: false` on every ticket of every build,
 * and the four 1:00 PM slips were re-drafted 23 minutes after kickoff -- different legs on a
 * card somebody was already holding (claude/nfl-anchorwave-2026-09-20.md).
 *
 * The cause is not a missing freeze rule, it is a freeze rule football can never satisfy.
 * index.html states the rule in one line:
 *
 *     pinnedP(n) = !p.out && !p.void && (p.status === 'confirmed' || started(n))
 *
 * Soccer runs it with the `started` half switched off (STANDASIS-2026-08-29) because a published
 * XI is the better signal there. Football has no team sheet at all -- every player is 'projected'
 * on every build -- so with `started` off as well, nothing on that board can ever lock.
 *
 * This file proves the flag restores the baseball shape for football WITHOUT moving soccer:
 *   1. flag OFF, underway            -> nothing locks          (soccer is untouched)
 *   2. flag ON,  before kickoff      -> nothing locks          (the repair window is intact)
 *   3. flag ON,  at/after kickoff    -> frozen, legs VERBATIM   (the placed bet survives)
 *   4. flag ON,  underway + dead leg -> NOT frozen              (`alive` guard: repairable)
 *
 * Scenario 4 is the one that matters. It is the Kean/Richarlison/Osula/Pinamonti failure of
 * 2026-08-29 -- three out-of-squad men riding live moons -- and the guard that stops it is
 * `!out && !void`, not the absence of a kickoff test.
 *
 * Runs on the shared engine against soccer's pinned 2026-08-26 fixture, because the engine is
 * the thing under test and that is the board every other redraft test is written against.
 *
 *     node test_nfl_kicklock.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SD = require(path.join(__dirname, '..', 'soccer', 'soccer_draft.js'));

SD.DEFAULTS.TOP_SINGLES = 0;      /* anchors + moons, which is what football drafts */
SD.DEFAULTS.MIN_ODDS = null;      /* the fixture predates the floor; test_plusmoney owns it */

const FIXTURE = path.join(__dirname, '..', 'soccer', 'fixtures', '2026-08-26', 'soccer_D.json');
const base = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
const KO = 19 * 60;

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
}

/* A football board: same engine, same slate, but NOBODY is ever confirmed. */
function board() {
  const D = JSON.parse(JSON.stringify(base));
  D.meta.ko = {};
  Object.keys(D.players).forEach(n => { D.meta.ko[String(D.players[n].game)] = KO; });
  D.meta.finals = []; D.meta.gs = {};
  Object.keys(D.players).forEach(n => {
    const p = D.players[n];
    p.status = 'projected';       /* football has no team sheet -- this is the whole point */
    p.hr = false; p.goalmins = [];
  });
  (D.tickets || []).forEach(t => { delete t.locked; });
  return D;
}
const sig = ts => ts.map(t => `${t.kind}:${t.players.map(l => l.name).join('+')}`).sort().join(' | ');
const NFL = extra => Object.assign({ TOP_SINGLES: 0, LOCK_ON_KICKOFF: true }, extra || {});

console.log('=== board under test (all legs projected, kickoff ' + KO + ') ===');
{
  const D = board();
  D.tickets.forEach(t => console.log(`    ${t.kind.padEnd(8)} ${t.players.map(l => l.name).join(' + ')}`));
  console.log('');
}

/* 1 -- soccer is untouched. Flag off, match underway, nothing may freeze on the clock. */
{
  const D = board();
  const r = SD.redraft(D, { nowUTCmin: KO + 5, cfg: { TOP_SINGLES: 0, LOCK_ON_KICKOFF: false } });
  chk('flag OFF + underway -> nothing locks (soccer keeps CONFLOCK as its only rule)',
      r.locked === 0, { locked: r.locked });
}

/* 2 -- the pre-kickoff repair window is intact. */
{
  const D = board();
  const r = SD.redraft(D, { nowUTCmin: KO - 5, cfg: NFL() });
  chk('flag ON + 5 min BEFORE kickoff -> nothing locks yet',
      r.locked === 0, { locked: r.locked });
}

/* 3 -- at kickoff the slip is a placed bet and is carried VERBATIM. */
{
  const D = board();
  const before = sig(D.tickets);
  const n = D.tickets.length;
  const r = SD.redraft(D, { nowUTCmin: KO, cfg: NFL() });
  chk('flag ON + AT kickoff -> every slip frozen',
      r.locked === n, { locked: r.locked, of: n });
  chk('flag ON + AT kickoff -> legs are carried verbatim',
      sig(r.tickets) === before, { before, after: sig(r.tickets) });
  chk('flag ON + AT kickoff -> redraft reports no change',
      r.changed === false, { changed: r.changed });
}

/* 3b -- and it still holds well past kickoff, which is where 09-20 actually broke. */
{
  const D = board();
  const before = sig(D.tickets);
  const r = SD.redraft(D, { nowUTCmin: KO + 23, cfg: NFL() });
  chk('flag ON + 23 min INTO the game -> legs still verbatim (the 2026-09-20 case)',
      sig(r.tickets) === before, { after: sig(r.tickets) });
}

/* 4 -- THE GUARD. A dead leg keeps the slip repairable even with the game underway. */
{
  const D = board();
  const victim = D.tickets.find(t => t.players.length > 1) || D.tickets[0];
  const deadLeg = victim.players[victim.players.length - 1].name;
  D.players[deadLeg].out = true;
  const r = SD.redraft(D, { nowUTCmin: KO + 5, cfg: NFL() });
  const still = (r.tickets || []).filter(t => t.players.some(l => l.name === deadLeg));
  chk('flag ON + underway + a leg flagged out -> that slip is NOT frozen',
      r.locked < D.tickets.length, { locked: r.locked, of: D.tickets.length });
  chk('flag ON + underway + a leg flagged out -> the dead man is off the board',
      still.length === 0, { deadLeg, stillOn: still.map(t => t.name) });
}

console.log('');
if (fail) { console.error(`${fail} FAILED`); process.exit(1); }
console.log('ALL GREEN -- football locks on kickoff, soccer does not, and a dead leg never freezes');
