"""
CHALKLOCK-2026-08-29 -- chalk does not reach into a bet that is already struck.

    owner: "caminero whole ticket was locked. no, thats not how that works.
            nothing shouldve moved except corbin if he ended up being benched"

He is right, and the archive backs him completely. At 23:08 EVERY slip on the board was locked,
and Corbin Carroll was `confirmed` and never benched -- at 23:08, at 23:12, and now. So nothing
should have moved. Two placed bets were deleted anyway.

WHERE IT CAME FROM, and it is a misquote

CHALKOFF-2026-08-26 evicts any slip carrying a chalk bat, locked or not, and cites:

    "Same treatment, and the same three doors, as the Dingers retirement
     (owner then: 'i dont care if they are locked')"

But that quote is from the DINGERS retirement, and the Dingers block says the opposite of how it
has been applied here, in its own words:

    "This stops NEW dingers only. A dinger already LOCKED on a placed board is still carried
     verbatim by the prior-board path -- A PLACED BET IS A PLACED BET"

Dingers stops minting and carries the locked ones. CHALKOFF borrowed the sentence and inverted
the rule.

And the case the owner actually ruled on was an ANCHOR, not a partner. CHALKOFF's own account:

    "Goodman (+280, price unchanged) became the 4th shortest ... his LOCKED builder stayed,
     leaving A BANNED BAT SITTING ALONE IN AN ANCHOR SEAT ... the board showed 5 anchors, one
     of them leading nothing."

That is a chalk bat occupying an anchor seat. It is not "a partner's price drifted, so delete the
parlay". The line that generalised it --

    ⚠️ ANY LEG, not just the anchor

-- is what cost Murakami two locked slips tonight when Caminero, a PARTNER, moved 258 -> 231.
Murakami never moved. Muncy, Chaparro, Bauers never moved.

THE RULE

The ban stops a chalk bat being DRAFTED. It does not unwind a bet already placed.

  OPEN slip    unchanged: any chalk leg evicts it. Nothing is drafted onto a banned bat, and an
               open slip is not yet a bet.
  LOCKED slip  evicted ONLY if the chalk bat is the slip's own ANCHOR -- the 08-26 case, a banned
               bat sitting in an anchor seat. A chalk PARTNER on a placed parlay changes nothing:
               the bet was struck at the price it was struck at, and the market moving afterwards
               is not a reason to delete it.

VERIFIED, both directions, against real archived transitions:
  2026-08-28 23:08 -> 23:12   nothing moves. All 14 slips carried verbatim.
  2026-08-26 19:34Z           Goodman's locked builder still comes off -- the anchor case the
                              owner ruled on is preserved.

Block comments only -- 2026-08-08, a `//` swallowed a `var` declaration and cost a live slate.
"""
import sys
BOARD='index.html'
src=open(BOARD,encoding='utf-8').read()

OLD = """    function chalkBanned(t){ var lg=(t&&t.players)||[];
      for(var i=0;i<lg.length;i++){ if(chalk[lg[i].name]) return true; } return false; }"""

NEW = """    /* CHALKLOCK-2026-08-29 -- A LOCKED SLIP IS A PLACED BET AND CHALK DOES NOT REACH IT.
       The "ANY LEG" rule above is right for an OPEN slip: nothing should be drafted onto a
       banned bat. It is wrong for a placed one. 2026-08-28 23:12Z, Caminero -- a PARTNER, not
       the anchor -- drifted 258 -> 231 into the ban and took two of Murakami's LOCKED moons
       with him. Murakami never moved. Muncy, Chaparro and Bauers never moved. Every slip on
       that board was locked and nobody was scratched.
       The "i dont care if they are locked" CHALKOFF cites is from the DINGERS retirement, and
       that block says the opposite of how it was applied: "This stops NEW dingers only. A
       dinger already LOCKED on a placed board is still carried verbatim -- a placed bet is a
       placed bet." And the case the owner did rule on was an ANCHOR: Goodman "sitting ALONE IN
       AN ANCHOR SEAT" on 08-26, not a partner leg on someone else's parlay.
       So: a locked slip is evicted only when the chalk bat is its own ANCHOR. That keeps 08-26
       exactly (a banned bat does not hold an anchor seat) and stops the market unwinding bets
       that were already struck. */
    function chalkBanned(t){ var lg=(t&&t.players)||[];
      if(t&&t.locked) return !!(lg.length&&chalk[lg[0].name]);
      for(var i=0;i<lg.length;i++){ if(chalk[lg[i].name]) return true; } return false; }"""

n=src.count(OLD)
if n!=1:
    sys.exit(f'ABORT: expected exactly 1 chalkBanned definition, found {n} -- patch by hand')
src=src.replace(OLD,NEW,1)
print('  patched: chalk evicts a locked slip only when the chalk bat is its anchor')
open(BOARD,'w',encoding='utf-8').write(src)
print(f'wrote {BOARD} ({len(src)} bytes)')
