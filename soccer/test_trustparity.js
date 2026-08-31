/* test_trustparity.js -- TRUSTPARITY-2026-08-31.
 *
 * soccer_live.js runs in the reader's browser and may assert `p.out`, which REFUNDS the leg and
 * pulls the slip off the board. It must apply the same bar to a team sheet that
 * soccer_teamnews.py applies on the server: ELEVEN STARTERS A SIDE (TRUST-2026-08-25).
 *
 * The three shapes ESPN actually serves, in the order it serves them:
 *
 *   1. STUB          rosters present, one name, no starters       -- 18:54Z tonight (Barcelona)
 *   2. PRE-XI SQUAD  full matchday squad, every starter flag off  -- the ~hour before kickoff
 *   3. PUBLISHED XI  22 named, 11 starters a side                 -- 19:12Z tonight
 *
 * Only (3) is a team sheet. Under the old predicate (`roster.length > 0`) all three counted, so
 * in (1) a priced player who did not join a ONE-NAME list was asserted out, and in (2) every
 * priced player in the match read BENCHED. That is what the owner watched happen to Raphinha,
 * who was starting.
 *
 * A retirement nothing tests is a retirement that gets undone -- test_draft_golden.js, on the
 * leftover section. Same reasoning here: squadOf().complete had no test at all, which is how a
 * comment claiming "Same standard soccer_payload.py applies" sat above a predicate that did not.
 */
const SL = require('./soccer_live.js');

let fail = 0;
const ok = (label, got, want) => {
  const good = JSON.stringify(got) === JSON.stringify(want);
  console.log(`${good ? 'PASS' : 'FAIL'}  ${label}`);
  if (!good) { fail++; console.log('   want ' + JSON.stringify(want) + '\n   got  ' + JSON.stringify(got)); }
};

const player = (name, starter) => ({ athlete: { displayName: name }, starter: starter });
const side = (names, nStart) => ({ roster: names.map((n, i) => player(n, i < nStart)) });

const XI_H = ['Joan Garcia', 'Kounde', 'Christensen', 'Cubarsi', 'Espart', 'Pedri', 'Bernal',
              'Raphinha', 'Yamal', 'Olmo', 'Gordon'];
const BENCH_H = ['Rodri', 'J. Cancelo', 'W. Szczesny', 'F. Lopez', 'K. Adeyemi', 'E. Garcia',
                 'E. Aller', 'H. Abdelkarim', 'A. Balde', 'G. Martin', 'B. Farinas'];
const AWAY = Array.from({ length: 22 }, (_, i) => 'Rayo ' + (i + 1));

const STUB     = { rosters: [side(['Joan Garcia'], 1), side(AWAY.slice(0, 1), 1)] };
const PRE_XI   = { rosters: [side(XI_H.concat(BENCH_H), 0), side(AWAY, 0)] };
const FULL     = { rosters: [side(XI_H.concat(BENCH_H), 11), side(AWAY, 11)] };
const HALF     = { rosters: [side(XI_H.concat(BENCH_H), 11), side(AWAY, 0)] };
const NONE     = { rosters: [] };

ok('a one-name stub is NOT a team sheet',            SL.squadOf(STUB).complete,   false);
ok('a squad with no starter flags is NOT a sheet',   SL.squadOf(PRE_XI).complete, false);
ok('one side published, the other not, is NOT',      SL.squadOf(HALF).complete,   false);
ok('no rosters at all is NOT',                       SL.squadOf(NONE).complete,   false);
ok('eleven a side IS a team sheet',                  SL.squadOf(FULL).complete,   true);

/* THE ONE THAT MATTERS. On the published XI he is confirmed; on everything short of it the
   board must not have an opinion, because the alternatives are `benched` (what the owner saw)
   and `out` (which would delete his three live slips). */
ok('Raphinha is a starter on the published XI',   !!SL.squadOf(FULL).xi['Raphinha'],   true);
ok('...and is NOT read as benched there',         !!SL.squadOf(FULL).bench['Raphinha'], false);
ok('pre-XI, the sheet is not believed at all',    SL.squadOf(PRE_XI).complete,          false);

/* Guard against the failure re-entering by the other route: a full sheet must still be able to
   say someone is on the bench, or the fix would have bought safety by going blind. */
ok('a real bench is still a bench',               !!SL.squadOf(FULL).bench['A. Balde'], true);
ok('...and is not mistaken for the XI',           !!SL.squadOf(FULL).xi['A. Balde'],    false);

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- squadOf() holds the server\'s eleven-a-side bar');
process.exit(fail ? 1 : 0);
