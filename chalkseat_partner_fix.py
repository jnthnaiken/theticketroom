"""
CHALKSEATFIX-2026-08-29 -- my CHALKSEAT patch deleted a locked slip. A chalk PARTNER does not
vacate an anchor seat.

WHAT IT COST, tonight, on the live board

    23:08   4 anchors x 2 moons. Murakami among them. All three of his slips LOCKED:
              The Way Back Machine   Murakami + Junior Caminero + Max Muncy      locked
              Climbing the Ladder    Murakami + Andres Chaparro + Jake Bauers    locked
              Drop the Hook          Murakami                                    locked

    23:12   ONE price moved: Caminero 258 -> 231, into the top-4 ban.
            Murakami 266 -> 266. Muncy, Chaparro, Bauers: unchanged.

            Both locked moons gone. Murakami left in the ANCHORS section leading nothing,
            for the next sixteen builds.

THE BUG, which is mine, shipped 2026-08-28 as CHALKSEAT

CHALKSEAT records the seat CHALKOFF empties so REDRAFT can refill it:

    if (chalkBanned(t)) { _killed[t.name]=1;
                          if (t.kind==='moon' && t.anchor) _chalkSeat[t.anchor]=1;
                          return false; }

`chalkBanned(t)` is true when ANY LEG is chalk -- correct, and CHALKOFF says so explicitly
("⚠️ ANY LEG, not just the anchor"). But the seat it then records is `t.anchor`, who may be
perfectly draftable. Caminero was a PARTNER on The Way Back Machine. He went chalk, the slip was
evicted (right), and CHALKSEAT then claimed MURAKAMI's seat was vacant (wrong). The engine's own
log said so in words that were simply false:

    [redraft] Munetaka Murakami: now chalk (top-4 cannot anchor, slip evicted by CHALKOFF)

Murakami was never chalk. That false trigger ran the FULL JOINT REDRAFT, which throws the open
board away -- and Climbing the Ladder, a LOCKED slip carrying no chalk bat at all, went with it.

A locked slip is a placed bet. CHALKOFF earns the right to delete one because the owner ruled on
it ("i dont care if they are locked") and only for a slip that actually carries a banned bat.
Nothing gives the pair rule that right, and my patch handed it over by mistake.

THE FIX

Record the seat only when THE ANCHOR HIMSELF is chalk. That is the only case where a seat is
actually vacated and a joint redraft is the right answer -- it is what CHALKSEAT was written for
(Coby Mayo, 19:17Z, who WAS the fourth shortest price).

A chalk PARTNER is a different fact and already has a correct answer: the slip dies under
CHALKOFF and the anchor's pair is repaired leg-by-leg by the machinery that exists for exactly
that. It must not escalate to a board-wide redraft.

VERIFIED against the real 23:08 -> 23:12 transition, prior and data both taken from git:

    before   14 prior -> 12 tickets    The Way Back Machine GONE, Climbing the Ladder GONE
    after    Climbing the Ladder SURVIVES, Murakami keeps his seat, and The Way Back Machine
             is repaired rather than deleted -- the chalk leg swapped, the anchor and the
             healthy partner pinned

Line comments are forbidden inside index.html's script block (2026-08-08: a `//` swallowed a
`var` declaration and cost a live slate) -- block comments only below.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD = ("      if(chalkBanned(t)){\n"
       "        /* The NAME is spent, same rule and same map as REDRAFT-2026-08-18's scratch kill: this\n"
       "           slip was on the board under it. Without this the joint redraft below re-mints under\n"
       "           the dead slip's own name and the board shows one ticket that was two bets -- measured,\n"
       "           not assumed: replaying 2026-08-26 19:34Z, \"Full Fathom\" came back as Pete Alonso\n"
       "           after Hunter Goodman was evicted. Exactly the 2026-08-17 \"Nightfall\" failure. */\n"
       "        _killed[t.name]=1;\n"
       "        if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;\n"
       "        return false; }")

NEW = ("      if(chalkBanned(t)){\n"
       "        /* The NAME is spent, same rule and same map as REDRAFT-2026-08-18's scratch kill: this\n"
       "           slip was on the board under it. Without this the joint redraft below re-mints under\n"
       "           the dead slip's own name and the board shows one ticket that was two bets -- measured,\n"
       "           not assumed: replaying 2026-08-26 19:34Z, \"Full Fathom\" came back as Pete Alonso\n"
       "           after Hunter Goodman was evicted. Exactly the 2026-08-17 \"Nightfall\" failure. */\n"
       "        _killed[t.name]=1;\n"
       "        /* CHALKSEATFIX-2026-08-29 -- ONLY IF THE ANCHOR HIMSELF IS CHALK.\n"
       "           chalkBanned() is true when ANY LEG is banned, which is right (CHALKOFF: \"ANY LEG,\n"
       "           not just the anchor\"). The SEAT is a different question. Recording t.anchor here\n"
       "           claimed a seat was empty whenever a PARTNER went chalk, and the anchor was still\n"
       "           sitting in it -- the engine logged \"Munetaka Murakami: now chalk\" about a bat\n"
       "           priced +266 while the ban was Olson/Alonso/Caminero/Schwarber. That false trigger\n"
       "           ran the full joint redraft, which throws the open board away, and it took\n"
       "           \"Climbing the Ladder\" with it: a LOCKED slip carrying no chalk bat at all.\n"
       "           2026-08-28 23:12Z, one price move (Caminero 258->231, nobody else on either slip\n"
       "           moved a cent), two placed bets deleted, and Murakami left leading nothing for the\n"
       "           next sixteen builds.\n"
       "           A chalk PARTNER kills that slip under CHALKOFF and the pair is then repaired leg\n"
       "           by leg by the machinery built for it. It must never escalate to a board-wide\n"
       "           redraft. Only a chalk ANCHOR actually empties a seat -- Coby Mayo at 19:17Z, who\n"
       "           really was the fourth shortest price, which is the case CHALKSEAT was written for. */\n"
       "        if(t.kind==='moon'&&t.anchor&&chalk[t.anchor])_chalkSeat[t.anchor]=1;\n"
       "        return false; }")

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 occurrence of the CHALKSEAT eviction block, found {n} -- "
             f"the source moved, patch by hand")
src = src.replace(OLD, NEW, 1)
print("  patched: a chalk PARTNER no longer vacates the anchor's seat")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
