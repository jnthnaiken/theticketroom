/* test_draft_golden.js -- GOLDEN MASTER for soccer_draft.js.
 *
 * The claim: given the exact inputs of 2026-08-26, soccer_draft.js still produces the board that
 * actually shipped that night. Not "a similar board" -- the same slips, same legs, same order,
 * same stakes.
 *
 * TESTPIN-2026-08-28. Two things were wrong with this file.
 *
 * 1. THE INPUTS WERE NOT PINNED. It read scored.json / teamnews.json / tickets.json from the
 *    soccer root -- all three rewritten by every build, several times an hour. A golden master
 *    whose golden is overwritten is not a golden master. They now come from
 *    fixtures/2026-08-26/, committed from dea662c1 and immutable. (The old header said
 *    2026-08-25; the board's own meta.date is 2026-08-26.)
 *
 * 2. THE PREMISE WAS OBSOLETE. It said this file exists so soccer_draft.js and soccer_mock.py
 *    cannot drift into "two drafters again". soccer_mock.py no longer drafts -- its own comment
 *    records it ("`draft()`, `span_ok()` and the THINSLATE loop above are gone ... scoring is
 *    not drafting, and scored.json is the interface") and it now shells out to
 *    soccer_draft_cli.js and reads tickets.json back. There is no second drafter to disagree
 *    with. What this file is still worth is a REGRESSION PIN, and that is what it now is.
 *
 * ⚠️ THE COMPARISON IS SPLIT, and the split now doubles as the retirement guard.
 * LEFTOVERS-2026-08-28 briefly added a leftover-singles section after this golden was cut; it was
 * a section SCREAMERS-2026-08-26 had already retired, and UNLEFTOVER-2026-08-28 backed it out.
 * `core` is the moons and the builders that back them -- compared strictly against what shipped
 * that night. `leftovers` is everything else, and it MUST BE EMPTY: a single-leg builder whose
 * player anchors no moon is the retired section coming back under a new name, which is exactly
 * how it got past every existing check the first time.
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
const FIXTURE = path.join(HERE, 'fixtures', '2026-08-26');
const J = n => JSON.parse(fs.readFileSync(path.join(FIXTURE, n), 'utf8'));

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

/* THE HISTORICAL CLAIM -- moons and the builders that back them, against what shipped.
   Leftover singles (LEFTOVERS-2026-08-28) postdate the golden and are excluded here; they are
   asserted structurally below. `core` is every slip whose player anchors a moon, which is
   exactly the set that existed when the golden was cut. */
const wantAnchors = SD.nameSet(want.filter(t => t.kind === 'moon').map(t => t.legs[0].name));
const core = got.tickets.filter(t => t.kind === 'moon' || wantAnchors[t.legs[0].name]);
const leftovers = got.tickets.filter(t => core.indexOf(t) < 0);

eq('ticket count (moons + anchor builders)', core.length, want.length);
eq('kinds', core.map(t => t.kind), want.map(t => t.kind));
eq('stakes', core.map(t => t.risk), want.map(t => t.risk));
eq('legs (name+odds, in order)',
  core.map(t => t.legs.map(l => [l.name, l.odds])),
  want.map(t => t.legs.map(l => [l.name, l.odds])));
eq('leg matches', core.map(t => t.legs.map(l => l.match)), want.map(t => t.legs.map(l => l.match)));

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

/* UNLEFTOVER-2026-08-28 -- THE LEFTOVER SECTION STAYS RETIRED, and this is the guard that says so.
   SCREAMERS-2026-08-26 retired it to match the MLB Dingers retirement ("its just bleeding money" --
   family went 11-80, -33.34u, -36.6% ROI). LEFTOVERS-2026-08-28 brought it back as `kind: builder`
   instead of `kind: family`, which is why every existing retirement check looked straight past it
   and why it took the owner noticing to catch it: "bro there is no leftover section anymore".
   A retirement nothing tests is a retirement that gets undone. So: on this fixture the drafter
   ships MOONS and their ANCHOR BUILDERS and nothing else. A single-leg builder whose player
   anchors no moon is the section coming back, whatever it is called. */
inv('no ticket beyond the moons and their anchor builders (the leftover section stays retired)',
  leftovers.length === 0);
inv('every builder backs a moon anchor',
  builders.every(t => anchorNames.indexOf(t.legs[0].name) >= 0));
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
console.log(fail ? `${fail} FAILURE(S)`
  : `ALL GREEN -- soccer_draft.js reproduces the 2026-08-26 board (${core.length} shipped slips)`);
process.exit(fail ? 1 : 0);
