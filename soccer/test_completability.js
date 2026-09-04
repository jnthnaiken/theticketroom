/* test_completability.js -- COMPLETABILITY-2026-09-04.
 *
 * The 2026-08-13 baseball failure, rebuilt as the smallest slate that reproduces it. A screamer
 * takes the strongest legal partner; that partner pins the WIN window; no third leg from another
 * match is reachable any more. The moon stalls at two legs, SKIPUNFILLABLE strikes the anchor,
 * and the retry seats somebody weaker -- so the strongest player on the board comes back as a
 * PARTNER LEG under him. index.html's own words for it: "he was demoted, and the strongest
 * non-chalk bat on the board fell to a partner leg under a weaker anchor."
 *
 * ⚠️ THE SYMPTOM IS NOT AN EMPTY BOARD. It is the WRONG ANCHOR, which is why it can run for
 * months without anyone noticing: the board still ships a full set of legal screamers.
 *
 *   A m1 k=100   B m2 k=155   C m3 k=50   D m4 k=55   E m5 k=52     WIN = 60
 *
 *   A+B  span 55 -- legal, and then every other match is 100+ minutes from B. Dead end.
 *   A+C  span 50 -- then +D, span 50. Alive.
 *
 * B is the trap: strongest available, legal on its own, fatal to the ticket.
 *
 * WITHOUT canComplete() this drafts `C+A+D` -- C anchoring, A demoted to a leg.
 * WITH it, `A+C+D`. Delete the guard and the first assertion below fails.
 */
const SD = require('./soccer_draft.js');

const CFG = { WIN: 60, MOON_LEGS: 3, MOONS_PER_ANC: 1, ANCH: 1, ANCH_PER_GAME: 2,
              MOON_RISK: 2.0, SINGLE_STAKE: 1.0, Z_GATE: 0, GAME_CAP: 9 };
const POOL = [
  { name: 'A', match: 'm1', kickoff: 100, TOTAL: 200, odds: 150 },
  { name: 'B', match: 'm2', kickoff: 155, TOTAL: 190, odds: 160 },
  { name: 'C', match: 'm3', kickoff: 50,  TOTAL: 180, odds: 170 },
  { name: 'D', match: 'm4', kickoff: 55,  TOTAL: 170, odds: 180 },
  { name: 'E', match: 'm5', kickoff: 52,  TOTAL: 160, odds: 190 },
];

const out = SD.draftN(POOL, 1, CFG, {});
const t = out[0];
console.log('  drafted: ' + (out.length
  ? out.map(x => x.legs.map(l => l.name).join('+')).join(' , ')
  : '(no moon)'));
console.log('');

let fail = 0;
const chk = (label, ok) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`); if (!ok) fail++; };

chk('the strongest player anchors, and is not demoted by a trap partner', !!t && t.legs[0].name === 'A');
chk('the trap partner B was declined', !!t && t.legs.every(l => l.name !== 'B'));
chk('A does not appear as a partner leg', out.every(x => x.legs.slice(1).every(l => l.name !== 'A')));
chk('the moon has MOON_LEGS legs', !!t && t.legs.length === CFG.MOON_LEGS);
chk('from that many distinct matches', !!t && new Set(t.legs.map(l => l.match)).size === CFG.MOON_LEGS);
chk('inside WIN', !!t && SD.spanOk(t.legs, CFG));

console.log(fail ? `\n${fail} FAILURE(S)` : '\nALL GREEN -- the lookahead saves the slip a greedy pick strands');
process.exit(fail ? 1 : 0);
