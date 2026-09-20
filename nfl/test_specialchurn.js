#!/usr/bin/env node
/* test_specialchurn.js -- SPECIALNOTANCHOR-2026-09-20.
 *
 * WHY. The live football board, eight consecutive builds, 22:09Z -> 22:38Z on 2026-09-20.
 * Thirteen locked slips never moved a leg. The nightcap did this:
 *
 *     Sunday Night -> Under Lights -> Sunday Night -> Under Lights -> ...
 *
 * with Tyler Warren on it every single time. One bet, one leg, a new title every five minutes,
 * and a commit each pass to publish the churn. Owner: "it still redrafting tickets when theyre
 * locked and in progress."
 *
 * THE CAUSE. redraft()'s grouping loop filed every non-moon slip under groups[anchor].builders
 * -- `else` catches 'builder', 'lunch' AND 'late'. An open special became a one-man zero-moon
 * group, entered the anchor-seat contest, lost it, was DEMOTED, and had its title burnt by the
 * `demoted` sweep. SHAPEREPAIR then re-minted the same player into the same empty section with
 * priorName = null, so it took the next free title. Ping-pong, forever.
 *
 * THE FIXTURE IS THE REAL BOARD. fixtures/2026-09-20/nfl_D.json is the 18:38 ET payload,
 * trimmed to the fields the engine reads, with its meta.ko intact: thirteen slips locked behind
 * kickoffs of 780/965/985 and one open nightcap on the 20:20 game. Two earlier cuts of this
 * test tried to synthesise the shape on soccer's 2026-08-26 fixture and BOTH PASSED AGAINST THE
 * UNFIXED ENGINE -- on that board the seeded special is always absorbed by a builder, so the
 * demote-burn-remint path is never walked. A regression test that does not fail on the bug is
 * not a regression test. This one does: run it against the pre-fix soccer_draft.js and
 * scenario 2 fails on the first comparison.
 *
 *     node test_specialchurn.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SD = require(path.join(__dirname, '..', 'soccer', 'soccer_draft.js'));
const { CFG, applyVocabulary } = require(path.join(__dirname, 'nfl_cfg.js'));
applyVocabulary(SD);

const FIX = path.join(__dirname, 'fixtures', '2026-09-20', 'nfl_D.json');
const base = JSON.parse(fs.readFileSync(FIX, 'utf8'));
const NOW = 1121;                 /* 18:41 ET -- 780/965/985 are underway, the 20:20 is not */

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
}
const board = () => JSON.parse(JSON.stringify(base));
const sig = ts => ts.map(t => `${t.kind}:${t.name}:${t.players.map(l => l.name).join('+')}`)
                    .sort().join(' | ');
function feedback(D, r) {
  const N = JSON.parse(JSON.stringify(D));
  N.tickets = r.tickets.map(t => ({
    kind: t.kind, name: t.name, locked: !!t.locked, anchor: t.anchor,
    players: t.players.map(l => ({ name: l.name, game: (D.players[l.name] || {}).game })),
  }));
  return N;
}

console.log('=== the pinned board ===');
{
  const D = board();
  const lk = D.tickets.filter(t => t.locked).length;
  console.log(`  ${Object.keys(D.players).length} players, ${D.tickets.length} slips, ${lk} locked`);
  D.tickets.filter(t => !t.locked).forEach(t =>
    console.log(`    open: ${t.kind.padEnd(7)} ${t.name.padEnd(16)} ${t.players.map(l => l.name).join(' + ')}`));
  console.log('');
}

/* 1 -- the open special is not an anchor and is never demoted. */
{
  const r = SD.redraft(board(), { nowUTCmin: NOW, cfg: CFG });
  chk('nothing is demoted -- the nightcap is not in the anchor contest',
      (r.demoted || []).length === 0, { demoted: r.demoted });
  chk('no shape repair fires -- the nightcap section was never emptied',
      (r.shaped || []).length === 0, { shaped: r.shaped });
  chk('the thirteen locked slips stay locked', r.locked === 13, { locked: r.locked });
}

/* 2 -- THE FIXED POINT. This is the assertion the bug breaks. */
{
  let D = board();
  const seen = [];
  for (let i = 0; i < 5; i++) {
    const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG });
    seen.push(sig(r.tickets));
    D = feedback(D, r);
  }
  chk('redraft is a fixed point across five passes (titles included)',
      seen.every(s => s === seen[0]),
      seen.map((s, i) => i + ': ' + s.slice(0, 120)));
  const titles = seen.map(s => (s.match(/late:([^:]+):/) || [])[1]);
  chk('the nightcap title never oscillates', new Set(titles).size === 1, { titles });
  const men = seen.map(s => (s.match(/late:[^:]+:(.+?)(?: \||$)/) || [])[1]);
  chk('and its man never changes', new Set(men).size === 1, { men });
}

/* 3 -- an empty section is still minted into: SHAPEREPAIR is not disabled, only unneeded. */
{
  const D = board();
  D.tickets = D.tickets.filter(t => t.kind !== 'late');
  const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG });
  chk('an empty nightcap section is still filled',
      r.tickets.filter(t => t.kind === 'late').length === 1,
      { late: r.tickets.filter(t => t.kind === 'late').map(t => t.name) });
}

/* 4 -- a special whose man is ruled out does not ride; the section refills. */
{
  const D = board();
  const t = D.tickets.find(x => x.kind === 'late');
  const man = t.players[0].name;
  D.players[man].out = true;
  const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG });
  const late = r.tickets.filter(x => x.kind === 'late');
  chk('a nightcap whose man is out does not ride',
      late.every(x => x.players.every(l => l.name !== man)),
      { man, late: late.map(x => x.players.map(l => l.name)) });
}

console.log('');
if (fail) { console.error(`${fail} FAILED`); process.exit(1); }
console.log('ALL GREEN -- a special is not an anchor, and redraft is a fixed point');
