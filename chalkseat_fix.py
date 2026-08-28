"""
CHALKSEAT-2026-08-28 -- two correct fixes cancelling each other, and the board loses an anchor.

WHAT THE OWNER SAW
    "its a friday and we cant find 4 anchors and 8 moons for baseball?"

The slate was never thin. 15 games, 387 bats, 45 in the pool. Drafted FRESH off the very same
19:17Z data the live build used, the engine seats four anchors and eight moons without effort:

    fresh draft, 19:17Z data:  4 anchors / 8 moons  (Murakami, Goodman, Encarnacion-Strand, OHTANI)
    what shipped at 19:17Z:    3 anchors / 6 moons

WHAT ACTUALLY HAPPENED, to the cent

Junior Caminero -- Tampa Bay, 7:10 PM, on no ticket and in a different game from anybody
involved -- drifted +241 -> +250 between the 19:12Z and 19:17Z builds. CHALK_N is 4 and the ban
is the four SHORTEST PRICES (CHALKODDS-2026-08-20), so that nine-cent move swapped two bats
across the ban line:

    19:12Z chalk:  Alonso 205 · Olson 213 · Schwarber 234 · CAMINERO 241     Mayo 246 = 5th, draftable
    19:17Z chalk:  Alonso 205 · Olson 213 · Schwarber 234 · MAYO 246         Caminero 250 = 6th, free

Coby Mayo was an anchor with two moons and a builder. He became chalk without his own price
moving at all, and the board went 4/8/4 -> 3/6/3 and stayed there for the rest of the night.
Bisected one field at a time over the two builds: reverting Caminero's price alone -- and
nothing else -- restores all fourteen tickets.

WHY NOTHING REFILLED THE SEAT

Both of the relevant rules are right on their own. They collide.

  CHALKOFF-2026-08-26 (owner: "yea no if he's in the top 4 ban he needs to be taken off")
      removes any slip carrying a chalk bat, locked or not, at all three doors -- and the first
      of those doors is the `prior` filter, the very first thing assembleClient does with the
      board it was handed.

  REDRAFT-2026-08-18 ("A DEAD ANCHOR REDRAFTS THE BOARD, IT DOES NOT VACATE A SEAT")
      re-runs the full joint four-anchor draft when a still-open moon's anchor is no longer
      draftable. Its predicate lists exactly this case, in these words:

          else if(chalk[a])r='now chalk (top-'+CHALK_N+' cannot anchor)';

      -- and it walks `prior`.

So CHALKOFF deletes the evidence REDRAFT needs, three hundred lines before REDRAFT looks for it.
`chalk[a]` in that predicate has been unreachable since 2026-08-26: a chalked anchor's moons are
never in `prior` to be found. Instrumented on the real 19:17Z board -- eleven slips reach
`prior`, and none of the three Mayo slips is among them:

    [dbg] moon anchor=Munetaka Murakami ...          <- 11 lines
    (no Coby Mayo line at all)                        <- his moons were already gone

This is the same shape as the bug REDRAFT-2026-08-18 was written to kill, quoting its own
comment: "The board just shrank instead: 2026-08-18 19:43Z Byron Buxton was scratched and the
board went 4 anchors / 8 moons / 4 builders -> 3 / 6 / 3 and stayed there." A scratch triggers a
redraft because a scratched bat stays in `prior`. A chalk eviction does not, because it does not.

THE FIX

Record what CHALKOFF evicts, at the moment it evicts it, and let REDRAFT read that. The
eviction is unchanged -- the slip still comes off the board, locked or not, exactly as the owner
asked. The only change is that the empty anchor seat is now VISIBLE to the joint redraft, which
is the thing that knows how to fill it.

Deliberately narrow: only a MOON eviction arms the trigger. That is the case that leaves an
anchor seat empty and a pair of moons missing. A builder-only or leg-only chalk eviction takes a
slip off the board without vacating a seat, and re-running the joint draft for that would be
churn, not repair.

Verified on the real board, same data, same clock:
    before:  14 prior -> 11 tickets   {moon 6, builder 3, lunch 1, late 1}
    after:   14 prior -> 14 tickets   {moon 8, builder 4, lunch 1, late 1}
             [redraft] Coby Mayo: now chalk (top-4 cannot anchor, slip evicted by CHALKOFF)
             Mayo is NOT re-seated -- he is chalk. Ohtani takes the seat, as the fresh draft says.

Line comments are forbidden inside this script block (2026-08-08: a `//` swallowed a `var`
declaration and cost a live slate) -- everything below uses the block form.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD_PRIOR = ("    var prior=(D.tickets||[]).filter(function(t){"
             "return !retiredKind(t.kind)&&!chalkBanned(t);});")

NEW_PRIOR = (
    "    /* CHALKSEAT-2026-08-28: remember the anchor seats CHALKOFF empties. The eviction is\n"
    "       unchanged -- a chalk slip comes off the board, locked or not. But REDRAFT-2026-08-18's\n"
    "       `chalk[a]` trigger walks `prior`, and this filter runs first, so a chalked anchor's\n"
    "       moons were gone before anything could notice the seat was empty and the board simply\n"
    "       shrank (2026-08-28: Caminero +241->+250 made Coby Mayo the 4th shortest price and took\n"
    "       4 anchors / 8 moons down to 3 / 6 for the night). Only a MOON eviction arms it: that is\n"
    "       the one that vacates a seat. */\n"
    "    var _chalkSeat={};\n"
    "    var prior=(D.tickets||[]).filter(function(t){\n"
    "      if(retiredKind(t.kind))return false;\n"
    "      if(chalkBanned(t)){\n"
    "        /* The NAME is spent, same rule and same map as REDRAFT-2026-08-18's scratch kill: this\n"
    "           slip was on the board under it. Without this the joint redraft below re-mints under\n"
    "           the dead slip's own name and the board shows one ticket that was two bets -- measured,\n"
    "           not assumed: replaying 2026-08-26 19:34Z, \"Full Fathom\" came back as Pete Alonso\n"
    "           after Hunter Goodman was evicted. Exactly the 2026-08-17 \"Nightfall\" failure. */\n"
    "        _killed[t.name]=1;\n"
    "        if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;\n"
    "        return false; }\n"
    "      return true;});")

OLD_TRIG = """      if(!prior.length)return false;
      return prior.some(function(t){"""

NEW_TRIG = """      if(!prior.length)return false;
      /* CHALKSEAT-2026-08-28: a seat emptied by CHALKOFF above is never visible in `prior`.
         Same fact, same consequence, read from where it is still knowable. */
      var _cs=Object.keys(_chalkSeat);
      if(_cs.length){ _redraftWhy=_cs[0]+': now chalk (top-'+CHALK_N+' cannot anchor, slip evicted by CHALKOFF)'; return true; }
      return prior.some(function(t){"""

for old, new, label in ((OLD_PRIOR, NEW_PRIOR, 'prior filter -> record the emptied seat'),
                        (OLD_TRIG, NEW_TRIG, '_redraft trigger -> read it')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
