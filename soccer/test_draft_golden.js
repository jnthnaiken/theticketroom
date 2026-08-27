/* test_draft_golden.js -- GOLDEN MASTER for soccer_draft.js.
 *
 * The claim this file has to earn: soccer_draft.js drafts the SAME board soccer_mock.py drafted
 * on 2026-08-25, from the same inputs. Not "a similar board" -- the same slips, same legs, same
 * order, same stakes. If the two ever disagree the soccer room has two drafters again, which is
 * the assemble_tickets.py failure the codebase already paid for once.
 *
 * Inputs are the COMMITTED artifacts of that night, not re-derived:
 *     scored.json    every priced player with TOTAL / gate_z / kickoff  (soccer_mock.py output)
 *     teamnews.json  the XI that night                                  (soccer_teamnews.py output)
 *     tickets.json   what the board actually shipped                    <- the assertion
 */
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');

const HERE = __dirname;
const J = n => JSON.parse(fs.readFileSync(path.join(HERE, n), 'utf8'));

const scored = J('scored.json');
const tn = J('teamnews.json');
const want = J('tickets.json');

const xi = SD.nameSet(Object.keys(tn.xi || {}));
const got = SD.draft(scored, {}, { xi });

let fail = 0;
const eq = (label, a, b) => {
  const ok = JSON.stringify(a) === JSON.stringify(b);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; console.log('   want ' + JSON.stringify(b) + '\n   got  ' + JSON.stringify(a)); }
};

console.log(`pool ${got.pool.length}  anchors ${got.anchors}${got.thin ? ' (thin)' : ''}  tickets ${got.tickets.length}`);
console.log('');

eq('ticket count', got.tickets.length, want.length);
eq('kinds', got.tickets.map(t => t.kind), want.map(t => t.kind));
eq('stakes', got.tickets.map(t => t.risk), want.map(t => t.risk));
eq('legs (name+odds, in order)',
  got.tickets.map(t => t.legs.map(l => [l.name, l.odds])),
  want.map(t => t.legs.map(l => [l.name, l.odds])));
eq('leg matches', got.tickets.map(t => t.legs.map(l => l.match)), want.map(t => t.legs.map(l => l.match)));

/* structural invariants that hold regardless of the golden file */
const inv = (label, ok) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`); if (!ok) fail++; };

const moons = got.tickets.filter(t => t.kind === 'moon');
const builders = got.tickets.filter(t => t.kind === 'builder');
const anchorNames = [...new Set(moons.map(t => t.legs[0].name))];

inv('every moon has exactly 3 legs', moons.every(t => t.legs.length === 3));
inv('no moon repeats a match', moons.every(t => new Set(t.legs.map(l => l.match)).size === 3));
inv('every moon fits WIN=180', moons.every(t => SD.spanOk(t.legs, SD.DEFAULTS)));
inv('each anchor ships exactly MOONS_PER_ANC',
  anchorNames.every(n => moons.filter(t => t.legs[0].name === n).length === SD.DEFAULTS.MOONS_PER_ANC));
inv('builders == moon anchors, one each',
  JSON.stringify(builders.map(t => t.legs[0].name).sort()) === JSON.stringify([...anchorNames].sort()));
inv('no partner used twice across the board', (() => {
  const seen = {};
  for (const t of moons) for (const l of t.legs.slice(1)) { if (seen[l.name]) return false; seen[l.name] = true; }
  return true;
})());
inv('no anchor appears as a partner', (() => {
  const A = SD.nameSet(anchorNames);
  return moons.every(t => t.legs.slice(1).every(l => !A[l.name]));
})());
inv('every drafted player was in the XI', got.tickets.every(t => t.legs.every(l => xi[l.name])));
inv('GAME_CAP respected in pool', (() => {
  const per = {};
  got.pool.forEach(p => { per[p.match] = (per[p.match] || 0) + 1; });
  return Object.values(per).every(v => v <= SD.DEFAULTS.GAME_CAP);
})());

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- soccer_draft.js reproduces the 2026-08-25 board');
process.exit(fail ? 1 : 0);
