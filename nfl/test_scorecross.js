#!/usr/bin/env node
/* test_scorecross.js -- SCORECROSS-2026-09-21.
 *
 * WHY. Owner, 2026-09-21, on the football board: "why wont it redraft? i dont understand why
 * its so hard to mimic the mlb board."
 *
 * He was right and the answer was one line. nfl_rebuild_cli.js crossed `out` from scored.json
 * into the prior board and nothing else -- while COUNTING what it was throwing away:
 *
 *     if (p.odds !== s.odds || p.TOTAL !== round1(s.TOTAL)) wouldMove++;
 *
 * redraft() ranks off D.players[n].TOTAL, and D is the PRIOR BOARD. So every five-minute
 * rebuild re-ran the anchor contest against the TOTALs baked at the first build of the morning.
 * ANCHORSET-2026-09-04 was working perfectly against a fossil -- the strengths could not move,
 * so the incumbents won every pass, and the only thing that could ever change the board was
 * somebody being ruled out.
 *
 * THE TWO RULES THAT WERE CONFLATED, and this test is here to keep them apart:
 *
 *     PRICEONCE   holds `odds`.   A price on the board is a price somebody could have taken.
 *     the MODEL   is not a price. TOTAL / blend / gate_z / wf must cross, or there is no draft.
 *
 * nfl-build.yml's own header has always said so -- "any changes in model total would be due to
 * live weather updates etc." -- and weather is refreshed every pass by nfl_wx.py specifically so
 * that it can move a TOTAL. It moved nothing, all day, on every football board since KICKLOCK.
 *
 * ⚠️ THE FIRST CUT OF THIS TEST PASSED AGAINST THE BUG. It inverted TOTAL alone and asserted the
 * board moved -- and it did not, even with the fix, because Z_GATE reads `gate_z` and gate_z had
 * not been inverted with it. Scenario 2 moves BOTH, the way a real re-score does. Run it against
 * `git show HEAD~1:nfl/nfl_rebuild_cli.js` and scenario 2 fails: the board comes back as the same
 * two slips with `[4 would have moved]` on stdout.
 *
 * THE FIXTURE IS THE REAL BOARD. fixtures/2026-09-21/ is the live 09-21 payload and its scored
 * rows, trimmed to the fields the engine reads. One game, kickoff 1215 ET, two singles.
 *
 *     node test_scorecross.js
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const CLI = path.join(__dirname, 'nfl_rebuild_cli.js');
const FIX = path.join(__dirname, 'fixtures', '2026-09-21');
const PRIOR = path.join(FIX, 'nfl_D.json');
const SCORED = JSON.parse(fs.readFileSync(path.join(FIX, 'scored.json'), 'utf8'));

const KO = 1215;                 /* the only kickoff on this slate, ET minutes past midnight */
const PREGAME = 595;             /* 9:55 ET */
const UNDERWAY = 1220;           /* 20:20 ET -- five minutes into the game */

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + String(detail).slice(0, 300)); }
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'scorecross-'));
function run(scored, now) {
  const sp = path.join(tmp, `s${Math.random().toString(36).slice(2)}.json`);
  const op = path.join(tmp, `t${Math.random().toString(36).slice(2)}.json`);
  fs.writeFileSync(sp, JSON.stringify(scored));
  /* exit 10 is "nothing moved", which is a SUCCESS and is half of what this test asserts. */
  let out;
  try {
    out = execFileSync(process.execPath, [CLI, PRIOR, sp, op, '--now', String(now)],
                       { encoding: 'utf8' });
  } catch (e) {
    if (e.status !== 10) throw e;
    out = String(e.stdout || '');
  }
  return { log: out, tickets: JSON.parse(fs.readFileSync(op, 'utf8')) };
}
const names = (ts) => ts.map(t => t.legs.map(l => l.name).join('+')).sort();

/* The prior board, for reference: Skattebo (TOTAL 131.1, gate_z 1.036) and Corum (118.7, 0.623)
   are the only two men above Z_GATE. Nabers (114.0, 0.466) and Parkinson (110.5, 0.349) are the
   next two and are below it. */
const INVERTED = JSON.parse(JSON.stringify(SCORED));
INVERTED.forEach(p => {
  if (p.name === 'Malik Nabers')      { p.TOTAL = 145.0; p.gate_z = 1.20; }
  if (p.name === 'Colby Parkinson')   { p.TOTAL = 140.0; p.gate_z = 1.10; }
  if (p.name === 'Cam Skattebo')      { p.TOTAL =  95.0; p.gate_z = 0.10; }
  if (p.name === 'Blake Corum')       { p.TOTAL =  90.0; p.gate_z = 0.05; }
});

/* 1 -- NO CHURN. The same scores rebuild to the same board. This is the half KICKLOCK bought
       and it must survive the fix: re-scoring is not licence to shuffle for its own sake. */
{
  const r = run(SCORED, PREGAME);
  chk('identical scores -> the board does not move',
      JSON.stringify(names(r.tickets)) === JSON.stringify(['Blake Corum', 'Cam Skattebo']), names(r.tickets));
  chk('...and it says so', /-> unchanged/.test(r.log), r.log);
  chk('...with nothing re-scored', /model: 0 re-scored/.test(r.log), r.log);
}

/* 2 -- THE BUG. A real re-score, before kickoff, must redraft. Pre-fix this returns the same
       two slips and prints "[4 would have moved]". */
{
  const r = run(INVERTED, PREGAME);
  const n = names(r.tickets);
  chk('a moved model redrafts the board before kickoff',
      n.indexOf('Malik Nabers') >= 0 && n.indexOf('Colby Parkinson') >= 0, n);
  chk('...and the outranked incumbents are gone',
      n.indexOf('Cam Skattebo') < 0 && n.indexOf('Blake Corum') < 0, n);
  chk('...demoted for the stated reason, not silently dropped',
      /demoted Cam Skattebo: outranked for an anchor seat/.test(r.log), r.log);
  chk('...and the re-score is reported', /model: 4 re-scored/.test(r.log), r.log);
}

/* 3 -- KICKLOCK IS NOT WEAKENED BY ANY OF THIS. Same inverted model, five minutes after
       kickoff: the slips are placed bets and nothing may touch them. */
{
  const r = run(INVERTED, UNDERWAY);
  chk('past kickoff a moved model changes NOTHING',
      JSON.stringify(names(r.tickets)) === JSON.stringify(['Blake Corum', 'Cam Skattebo']), names(r.tickets));
  chk('...the slips are locked', r.tickets.every(t => t.locked === true),
      r.tickets.map(t => t.name + ':' + t.locked));
  chk('...and PRICEFREEZE stops the cross at the door, so nothing is re-scored either',
      /model: 0 re-scored/.test(r.log) && /24 frozen \(underway\)/.test(r.log), r.log);
}

/* 4 -- PRICEONCE SURVIVES. The model crosses; the PRICE never does. A scored file quoting a
       different number must leave every leg on the board at the price it was drafted at. */
{
  const REPRICED = JSON.parse(JSON.stringify(SCORED));
  REPRICED.forEach(p => { if (p.odds != null) p.odds = p.odds + 55; });
  const r = run(REPRICED, PREGAME);
  const odds = {};
  r.tickets.forEach(t => t.legs.forEach(l => { odds[l.name] = l.odds; }));
  chk('a re-priced scored.json never moves a leg on the board',
      odds['Cam Skattebo'] === 125 && odds['Blake Corum'] === 220, JSON.stringify(odds));
  chk('...and the hold is counted, not hidden', /\[24 would have moved\]/.test(r.log), r.log);
}

console.log('');
if (fail) { console.error(`${fail} FAILED`); process.exit(1); }
console.log('ALL GREEN -- the model crosses, the price is held, and a locked slip is untouchable');
