#!/usr/bin/env python3
"""
SEATCAP-2026-08-30 -- the anchor budget is a CAP, and `_forced` was never checked against it.

THE FAILURE (2026-08-30, reproduced at 17:17Z)
----------------------------------------------
Coby Mayo drifted 252 -> 260 for ONE build. Juan Soto's own price never moved (257 all day), but
that tick made him the 4th shortest, so CHALKBAN barred him and CHALKOFF evicted his two OPEN
moons. His BUILDER is a placed bet and stayed (LOCKNOREDRAFT-2026-08-29). The joint redraft seated
Esmerlyn Valdez in the freed seat, and five minutes later Valdez's builder locked too.

At 17:17Z Mayo settled back to 256 and Soto came out of the ban. Now TWO bats held a locked builder
and no locked moon, so SEAT-LOCK-2026-08-19 forced BOTH back into the joint draft:

    _cmA    [Murakami, Olson, Goodman]                       3 seats spent by locked MOONS
    _cmB    [Murakami, Olson, Goodman, Soto, Valdez]         locked builders
    _forced [Soto, Valdez]                                   locked builder, no locked moon
    _KT     max(0, 4 - 3 - 2) = 0

`_KT` is floored at zero, so the overflow vanished silently and searchBest seated both forced bats
on top of the three placed ones: **5 anchors, 10 moons, 17 tickets**, from 17:17Z until the board
was repaired by hand. replay_check flags it 23 consecutive builds -- TOO MANY ANCHORS: 5.

SEAT-LOCK is right that a locked builder is a placed bet sitting in an anchor seat. What was never
written down is that there are only FOUR seats. `Math.max(0, ...)` clamps the arithmetic; it does
not clamp `_forced`, and `_forced` is what searchBest actually seats.

WHY THIS SHAPE AND NOT ANOTHER
------------------------------
`chalkchurn-2026-08-29.md`, on the third patch in a row that failed the same way:

    Withholding an action in this engine leaves a hole, because the action is what triggers the
    repair. Any future fix here has to KEEP the eviction and make the refill cheaper -- not delay
    the eviction.

This one keeps the eviction untouched. CHALKBAN, CHALKOFF, LOCKNOREDRAFT and LOCKEVICT are not
read, not reordered and not weakened; the ban is still exactly the four shortest prices at every
instant. It acts only on the REFILL, and only when the refill would exceed the budget the board
has always had.

It is NOT CHALKHYST (reverted 08-28) and NOT CHALKSETTLE (rejected 08-29). Neither the ban nor any
previous build's ban is an input here. Nothing is held for an incumbent: when the claims outnumber
the seats they are ranked by `byS` -- the board's own strength order, the same key `candA` and
`searchBest` use -- so the seat goes to the bat the draft rates highest, which is the same answer
the joint search would give if the bat had not been reserved out of the candidate list by his own
builder.

The bat who yields KEEPS HIS LOCKED BUILDER. It is a placed bet and is emitted verbatim, exactly as
before; he simply does not also collect a pair of moons. That is the `builder:5 / moon:8` shape
LOCKNOREDRAFT-2026-08-29 already measured and described on 08-26 -- "The board is not short; it
carries one extra placed single."

This is the seat-releasing companion (`LOCKSEAT`) that was written on 08-29 and NOT shipped because
it measured as a no-op on that corpus. It is not a no-op here: 08-30 is the case it was written for.
"""
import re
import sys

BOARD = sys.argv[1] if len(sys.argv) > 1 else 'index.html'

OLD = """        return !_cmA[a] && P[a] && !P[a].out && !P[a].void && !chalk[a]; });
      var _KT=Math.max(0,4-Object.keys(_cmA).length-_forced.length);"""

NEW = """        return !_cmA[a] && P[a] && !P[a].out && !P[a].void && !chalk[a]; });
      /* SEATCAP-2026-08-30 -- FOUR SEATS, AND `_forced` HAS TO FIT IN THEM.
         SEAT-LOCK above is correct that a locked builder is a placed bet holding an anchor seat, but
         it never checked how many such claims exist. `_KT` below is floored at 0, which clamps the
         ARITHMETIC and not the LIST -- and the list is what searchBest seats. On 2026-08-30 Coby Mayo
         drifted 252->260 for one build, the ban took Juan Soto's two open moons (his builder stayed,
         placed), Esmerlyn Valdez was drafted into the freed seat and his builder locked as well. When
         Mayo settled back and Soto left the ban, BOTH held a locked builder and no locked moon, so
         both were forced: 3 placed seats + 2 forced = 5 anchors, 10 moons, 17 tickets, for the next
         23 builds. replay_check calls it TOO MANY ANCHORS and it is right.
         The eviction is untouched -- see chalkchurn-2026-08-29: withholding it leaves a hole, because
         the eviction is what triggers the repair. This caps the REFILL instead, which is the only
         direction that document leaves open. `byS` is the board's own strength order (the key candA
         and searchBest already rank on), so the seat goes to the bat the draft rates highest rather
         than to whoever happened to hold it -- no incumbency, nothing read back from a previous ban.
         The bat who yields keeps his locked builder verbatim; he just does not also take a pair of
         moons. That is the builder:5 / moon:8 shape LOCKNOREDRAFT-2026-08-29 already measured. */
      var _seats=Math.max(0,4-Object.keys(_cmA).length);
      if(_forced.length>_seats){
        var _drop=byS(_forced).slice(_seats);
        _forced=byS(_forced).slice(0,_seats);
        if(typeof console!=='undefined'&&console.log)console.log('[seatcap] '+Object.keys(_cmA).length+' seat(s) held by placed moons -> only '+_seats+' left; '+_drop.join(', ')+' keep(s) the locked builder without moons');
      }
      var _KT=Math.max(0,4-Object.keys(_cmA).length-_forced.length);"""

src = open(BOARD, encoding='utf-8').read()
if src.count(OLD) != 1:
    sys.exit(f'seatcap_fix: expected exactly 1 match, found {src.count(OLD)} -- refusing to patch')
open(BOARD, 'w', encoding='utf-8').write(src.replace(OLD, NEW, 1))
print('seatcap_fix: patched', BOARD)
