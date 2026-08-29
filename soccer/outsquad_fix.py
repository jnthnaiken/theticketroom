"""
OUTSQUAD-2026-08-29 -- a man dropped from the squad was riding a LOCKED ticket.

    test_stage2_page.js, scenario 2 ("team news lands an hour before kickoff"), four failures,
    all one defect:

        FAIL  the board moved off the baked draft
        FAIL  the dead leg was replaced, not dropped
        FAIL  the dead leg is on no slip at all
        FAIL  every remaining leg is a confirmed starter
              [["Kylian Mbappe=confirmed","Dion Beljo=confirmed","Luka Jovic=confirmed!"], ...]

Read the last line. The `!` is the test printing `p.out`. So the page HAD already marked Luka
Jovic out of the squad -- team news landed, the sheet published without him, `pl.out=true` was
set, and the card showed it. The drafter simply did not care.

THE BUG, one missing clause

    function ticketIsLocked(t, D, nowUTCmin, koOf) {
      ...
      var allConf = legs.every(function (l) {
        var p = D.players[l.name];
        return p && p.status === 'confirmed';        <- out and void are never consulted
      });
      if (allConf) return true;

`status` is set to 'confirmed' when a player is first seen in a posted sheet and is never taken
back; being dropped is recorded on `out`, a separate flag. So a slip carrying a man who is NOT
IN THE SQUAD still read "every leg confirmed", locked, and became untouchable -- an hour before
kickoff, with a full replacement pool sitting there and nothing else wrong with the slip. The
leg-level repair below never got the chance to run, because repair only walks `open` and the slip
had been put in `frozen`.

CONFLOCK's own definition, from index.html where this rule came from:

    LOCK = the WHOLE ticket is confirmed (every leg in the posted lineup / game underway,
    NONE SCRATCHED)

and the baseball engine states it in code:

    function pinnedP(n){var p=P[n]; return !!(p && !p.out && !p.void && (p.status==='confirmed' || started(n)));}
    function frozenT(t){ ... t.players.every(function(l){return pinnedP(l.name);}) ... }

The soccer port dropped `!p.out && !p.void`. That is the entire difference, and it is restored
here in the same shape, so the two rooms state the rule identically.

WHAT THIS DOES NOT CHANGE, and why the third scenario still passes

  * `if (t.locked) return true` is untouched. The lock is a LATCH (2026-08-17): once a slip has
    locked it never unlocks, so nothing already placed can be unwound by a late team-news wobble
    -- a player marked out and then back in cannot flip a slip in and out of the board.
  * The KICKOFF branch is untouched. After kickoff a slip is frozen by the clock regardless of
    `allConf`, which is why scenario 3 ("thirty minutes after kickoff") keeps asserting, rightly,
    that "the out player is STILL on his slip -- a placed bet is not unwound, it is graded".
  * `redraft()`'s `alive[]` already excluded `p.out`. The repair machinery was correct all along;
    it was simply never reached. Nothing downstream needed changing.

So the window this touches is exactly the one it should: BEFORE kickoff, BEFORE the slip has ever
locked, when a bet has not yet been struck and the board still has every right to fix itself.

ONE SOURCE, ONE FIX. soccer/index.html carries an inlined copy of this file, but it is a BUILD
ARTIFACT -- soccer_live_seams.py line 175 prepends soccer_draft.js onto the live seam and
soccer_fork.py rebuilds the page each build. Patching soccer_draft.js is patching the page.

VERIFIED
    test_stage2_page.js   4 FAILURES -> ALL GREEN (the dead leg is replaced, the anchor and the
                          healthy partner stay pinned, the slip keeps its name, and after kickoff
                          the board is still frozen with the out player on it)
    test_redraft.js       ALL GREEN -- CONFLOCK and MINTGUARD hold
    test_draft_golden.js  ALL GREEN -- reproduces the 2026-08-26 board
    test_live.js          31/31
"""
import sys

F = 'soccer_draft.js'
src = open(F, encoding='utf-8').read()

OLD = """    var allConf = legs.every(function (l) {
      var p = D.players[l.name];
      return p && p.status === 'confirmed';
    });
    if (allConf) return true;"""

NEW = """    /* OUTSQUAD-2026-08-29 -- `!p.out && !p.void` IS PART OF THE RULE, and was missing.
       `status` is set to 'confirmed' the first time a player appears in a posted sheet and is
       never taken back; being DROPPED from the squad is recorded on `out`. Testing status alone
       therefore read "every leg confirmed" for a slip carrying a man who was not in the XI, so it
       locked, went into `frozen`, and the leg-level repair below -- which already excludes
       `p.out` via alive[] -- never saw it. 2026-08-29, test_stage2_page scenario 2: team news
       lands an hour before kickoff, the card correctly shows the dropped man as out, and his slip
       is untouchable anyway with a full replacement pool available.
       CONFLOCK's definition has always said otherwise ("every leg in the posted lineup / game
       underway, NONE SCRATCHED"), and the baseball engine says it in code -- pinnedP() is
       `!p.out && !p.void && (p.status==='confirmed' || started(n))`. This is that clause, in the
       same shape, so the two rooms state one rule.
       ⚠️ NOT AN UNLOCK. `t.locked` above is a latch and is untouched, and the KICKOFF branch
       below is untouched, so a placed bet is never unwound and a late team-news wobble cannot
       flip a slip on and off the board. This reaches only the window before a slip has ever
       locked, which is exactly when the board is still entitled to repair itself. */
    var allConf = legs.every(function (l) {
      var p = D.players[l.name];
      return p && p.status === 'confirmed' && !p.out && !p.void;
    });
    if (allConf) return true;"""

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 allConf block in {F}, found {n} -- the source moved, patch by hand")
src = src.replace(OLD, NEW, 1)
print("  patched: an out-of-squad leg no longer counts as confirmed for the FIRST lock")

if "return p && p.status === 'confirmed' && !p.out && !p.void;" not in src:
    sys.exit("ABORT: the restored clause is not present")
if "if (t.locked) return true;" not in src:
    sys.exit("ABORT: the lock LATCH is gone -- it must survive, a placed bet is never unwound")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
