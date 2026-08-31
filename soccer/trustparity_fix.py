"""
TRUSTPARITY-2026-08-31 -- the browser trusted a team sheet the server would have refused.

    owner, 2026-08-31: "and why did raphinha show up as benched for a bit? and then confirmed"

THE TWO STANDARDS

soccer_teamnews.py has required an ELEVEN-A-SIDE sheet since TRUST-2026-08-25:

    trusted = (st.get('xi_h') == 11 and st.get('xi_a') == 11)

soccer_live.js, running the same rules in the reader's browser, required only that both rosters
be NON-EMPTY:

    var complete = rs.length >= 2 && rs.every(function (r) { return ((r.roster) || []).length > 0; });

Its own comment says "Same standard soccer_payload.py applies." It was not the same standard.
This restores the parity the comment already claims.

WHY IT MATTERS -- ESPN PUBLISHES THE SQUAD BEFORE IT PUBLISHES THE XI

`rosters` fills with the matchday squad while every `starter` flag is still false, and only later
do the flags land. Measured on esp.1 401882903 (Barcelona v Rayo) at 19:12Z, after the XI
dropped: 22 named / 11 starters a side. In the window before that it is 22 named / ZERO
starters -- and the old predicate called that a complete sheet.

So every priced player in the match fell into

    else if (who && sq.bench[who]) { p.status = 'benched'; p.out = false; }

and the board read BENCHED for the whole pre-XI window. That is what the owner watched happen to
Raphinha, who was in fact starting (formationPlace 9) and flipped to `confirmed` the moment ESPN
set the flags. The board itself was never wrong: `p.out = false` on that branch, so all three
slips survived and no re-draft was triggered.

THE BRANCH BELOW IT IS THE REAL EXPOSURE, and it is why this is a fix and not a cosmetic:

    else if (!who && !p.hr && !surnameHits(n, sqAll)) { p.out = true; }

`out` REFUNDS the leg and pulls the slip off the board. On a stub sheet -- ESPN had Barcelona at
ONE name (Joan Garcia) as late as 18:54Z tonight -- any priced player who does not join and has
no surname on that one-name list is asserted ABSENT, in the reader's browser, off a board the
server publishes intact. That is UNMATCHED-2026-08-28's failure ("that deleted 'Back Post' from
a live board IN THE READER'S BROWSER") reached through a different door: that fix hardened the
JOIN, and this one hardens the thing the join is run against.

WHAT CHANGES, AND IN WHICH DIRECTION

Only the bar for believing a sheet at all. When it is not met, `sq.complete` is false and the
whole squad block is skipped: status stays `projected`, nobody is benched and nobody is
asserted out -- which is what "we have not seen the team sheet yet" should look like, and what
the server already does. It can never newly kill a leg; it can only decline to.

NOT a change to matchOne(), surnameHits(), the goal path, finality, or the live flag. A player
who SCORES is still confirmed whatever the sheet says -- that branch is downstream of this one
and untouched.
"""
import sys

F = 'soccer_live.js'
src = open(F, encoding='utf-8').read()

OLD = """  /* Squad sheet. `out` REFUNDS a leg at grading, so it is the strong claim and is asserted
   * only when BOTH teams published a non-empty roster -- absent from a sheet we never saw is
   * not the same fact as absent from the sheet. Same standard soccer_payload.py applies. */
  function squadOf(summary) {
    var rs = (summary && summary.rosters) || [];
    var complete = rs.length >= 2 && rs.every(function (r) { return ((r.roster) || []).length > 0; });"""

NEW = """  /* Squad sheet. `out` REFUNDS a leg at grading, so it is the strong claim and is asserted
   * only when BOTH teams published a sheet we are willing to believe -- absent from a sheet we
   * never saw is not the same fact as absent from the sheet.
   *
   * TRUSTPARITY-2026-08-31 -- ELEVEN A SIDE, the same bar soccer_teamnews.py has used since
   * TRUST-2026-08-25 (`trusted = (xi_h == 11 and xi_a == 11)`). This line used to ask only that
   * both rosters be NON-EMPTY, while its own comment claimed parity with the server. It was not
   * parity, and the gap is not theoretical: ESPN fills `rosters` with the matchday squad while
   * every `starter` flag is still false, so in the window before the XI lands a match reads 22
   * named / ZERO starters a side -- and the old predicate called that complete. Every priced
   * player in it then took the `sq.bench[who]` branch and the board showed him BENCHED (owner,
   * 2026-08-31: "why did raphinha show up as benched for a bit? and then confirmed" -- he was
   * starting, formationPlace 9, and flipped the moment the flags landed).
   *
   * That branch sets `p.out = false` and is survivable. The one below it is not: a stub sheet
   * (ESPN had Barcelona at ONE name at 18:54Z tonight) let `!who && !surnameHits` assert `out`
   * on a man who is playing, refunding his leg and pulling a live slip off the board IN THE
   * READER'S BROWSER -- UNMATCHED-2026-08-28's failure through a different door. That fix
   * hardened the JOIN; this hardens what the join is run against.
   *
   * Failing this bar skips the whole squad block, so status stays `projected`: it can never
   * newly kill a leg, only decline to. */
  function squadOf(summary) {
    var rs = (summary && summary.rosters) || [];
    var complete = rs.length >= 2 && rs.every(function (r) {
      var st = 0;
      ((r.roster) || []).forEach(function (pl) { if (pl.starter) st++; });
      return st === 11;
    });"""

n = src.count(OLD)
if n != 1:
    sys.exit(f'ABORT: expected exactly 1 match for squadOf(), found {n} -- the source moved')
src = src.replace(OLD, NEW, 1)
open(F, 'w', encoding='utf-8').write(src)
print(f'trustparity_fix: patched {F} ({len(src)} bytes)')
