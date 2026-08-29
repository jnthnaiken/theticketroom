"""
Revert CHALKLOCK-2026-08-29. It broke the chalk ban and it was never needed.

THE RULE, as written down before today:

  CHALKOFF-2026-08-26, owner: "yea no if he's in the top 4 ban he needs to be taken off"
      -- ANY LEG, not just the anchor. Locked included. "Removal is the rule."
      -- an exemption was proposed and the owner rejected it: "exemption was the wrong direction."
  Dingers 2026-08-25, owner: "i dont care if they are locked" (four locked slips pulled).
  lock-latch 2026-08-17: "Do not conflate 'a locked ticket is never re-derived' with
      'a locked ticket survives anything.'"

CHALKLOCK made a locked slip judged on its ANCHOR only, so a locked slip carrying a banned PARTNER
stayed on the board. That is the exemption the owner rejected, and it is "a locked ticket survives
anything" in code.

WHY I WROTE IT, AND WHY THAT WAS WRONG. 2026-08-28 23:12Z, three Murakami slips:

    The Way Back Machine   Murakami + Junior Caminero + Muncy    Caminero went chalk
    Climbing the Ladder    Murakami + Chaparro + Bauers          NO chalk bat
    Drop the Hook          Murakami                              NO chalk bat

Both moons vanished, and the owner was right that something was broken. But only ONE of them was a
bug. Climbing the Ladder carried no banned bat and died because CHALKSEAT recorded a false vacated
seat and ran a joint redraft that ate the open board. The Way Back Machine carried Caminero and its
removal is CHALKOFF working. I treated one complaint as covering both and wrote an exemption.

MEASURED on that exact transition (23:08 board -> 23:12 data, real engine):

    with CHALKLOCK     14 tickets   Climbing the Ladder SURVIVES   The Way Back Machine STAYS
                                                                   -- with a banned bat on it
    reverted           13 tickets   Climbing the Ladder SURVIVES   The Way Back Machine REMOVED

The slip the owner cared about is protected either way -- by MINTLOCK-2026-08-29 (the sibling kill
exempts locked slips) and UNCHALKSEATFIX-2026-08-29 (a chalk partner no longer fakes a vacated
seat), which are the fixes for the actual bug. CHALKLOCK adds nothing except keeping a banned bat
on the board.

Board-wide cost of carrying it, replayed: 2026-08-23 ran 214 builds at 8 moons instead of 119 at 8
and 95 at 7 -- i.e. for 95 builds a locked moon rode with a bat the ban says comes off. 08-28: 104
instead of 70 and 34.

Same shape as CHALKSEATFIX-2026-08-29, reverted earlier tonight for the same reason: an exemption
invented to explain a complaint that was really a different bug, where the different bug already
had a correct fix.

WHAT THIS RESTORES. `chalkBanned` is ANY LEG again, at all three CHALKOFF doors (the CONFLOCK scan,
the `prior` carry, the localStorage latch). LOCKEVICT-2026-08-29's night-long union rides the same
dispatch, so it goes back to any-leg too, which is what CHALKOFF's door 3 always said.

KEPT: MINTLOCK-2026-08-29. It is a different rule -- a locked moon must not be unwound because its
SIBLING was late to mint. That is not chalk and not a scratch, so the latch doctrine covers it.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD = ("    function chalkBannedIn(t,set){ var lg=(t&&t.players)||[];\n"
       "      if(t&&t.locked) return !!(lg.length&&set[lg[0].name]);\n"
       "      for(var i=0;i<lg.length;i++){ if(set[lg[i].name]) return true; } return false; }\n"
       "    /* LOCKEVICT-2026-08-29: the dispatch above is EXTRACTED, not duplicated. `chalkBanned` is the\n"
       "       live ban; the localStorage latch asks the same question of `_chalkEver`, the union of every\n"
       "       ban this slate has settled on. Two sets, one rule -- a locked slip is judged on its ANCHOR\n"
       "       (CHALKLOCK-2026-08-29: a placed bet is not unwound because a PARTNER went chalk), an open\n"
       "       one on any leg. A second copy of this dispatch is how 2026-08-28 happened. */\n"
       "    function chalkBanned(t){ return chalkBannedIn(t,chalk); }")

NEW = ("    /* CHALKOFF-2026-08-26: ANY LEG, not just the anchor, LOCKED INCLUDED. Owner: \"yea no if\n"
       "       he's in the top 4 ban he needs to be taken off\", and an exemption was proposed then and\n"
       "       rejected -- \"exemption was the wrong direction. Removal is the rule.\" Same call as the\n"
       "       Dingers pull (\"i dont care if they are locked\"), and lock-latch-2026-08-17 states the\n"
       "       principle: do not conflate \"a locked ticket is never re-derived\" with \"a locked ticket\n"
       "       survives anything.\"\n"
       "       CHALKLOCK-2026-08-29 briefly made a locked slip judged on `lg[0]` alone. It is reverted:\n"
       "       it was the rejected exemption, and it was not protecting anything. The slip it was\n"
       "       written for -- Murakami's \"Climbing the Ladder\", locked, no banned bat, deleted at\n"
       "       2026-08-28 23:12Z -- survives without it, because the real cause was CHALKSEAT faking a\n"
       "       vacated seat (UNCHALKSEATFIX) and the sibling kill not exempting locked slips (MINTLOCK).\n"
       "       Replayed on that exact transition: reverted, Climbing the Ladder survives and \"The Way\n"
       "       Back Machine\" -- which really did carry Caminero -- comes off, which is the ban working.\n"
       "       LOCKEVICT-2026-08-29 asks the same question of `_chalkEver`, the night's union, at the\n"
       "       localStorage door. Two sets, one dispatch -- a second copy of it is how 08-28 happened. */\n"
       "    function chalkBannedIn(t,set){ var lg=(t&&t.players)||[];\n"
       "      for(var i=0;i<lg.length;i++){ if(set[lg[i].name]) return true; } return false; }\n"
       "    function chalkBanned(t){ return chalkBannedIn(t,chalk); }")

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 CHALKLOCK dispatch, found {n} -- revert by hand")
src = src.replace(OLD, NEW, 1)
print("  reverted: chalkBanned is ANY LEG again, locked included, at all three CHALKOFF doors")

if "if(t&&t.locked) return !!(lg.length&&set[lg[0].name]);" in src:
    sys.exit("ABORT: the locked-anchor-only branch is still live")
if "&&_anch[t.anchor]&&!t.locked)_kill[t.name]=1;" not in src:
    sys.exit("ABORT: MINTLOCK-2026-08-29 is missing -- it is what protects the clean locked moon")
if "if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;" not in src:
    sys.exit("ABORT: CHALKSEAT is missing -- it is the other half of that protection")
# count the CALL, not the comment above it that quotes it
if src.count("|| chalkBannedIn(t,_chalkEver) ||") != 1:
    sys.exit("ABORT: LOCKEVICT's door-3 call moved")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
