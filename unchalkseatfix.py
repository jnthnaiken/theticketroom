"""
UNCHALKSEATFIX-2026-08-29 -- revert my own CHALKSEATFIX. It cost an anchor and protected nothing.

CHALKSEATFIX-2026-08-29 (shipped a few hours ago, commit 71706358) narrowed CHALKSEAT so that only
a chalk ANCHOR records a vacated seat:

    if(t.kind==='moon'&&t.anchor&&chalk[t.anchor])_chalkSeat[t.anchor]=1;      <- what shipped
    if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;                        <- what it replaced

It was written to stop a chalk PARTNER (Caminero, 258->231) from triggering a board-wide joint
redraft that deleted Murakami's locked "Climbing the Ladder", a placed bet carrying no chalk bat.
That problem was real. This was not the fix for it, and its docstring made a claim I never
measured: "the pair is then repaired leg by leg by the machinery built for it."

IT IS NOT. Here is what actually happens. When CHALKOFF evicts an anchor's moons because a PARTNER
went chalk, those slips leave `prior` before anything else reads it. The redraft trigger has two
branches and neither can see the hole:

    _chalkSeat        -- now empty, because the anchor himself was never chalk
    prior.some(...)   -- walks OPEN MOONS, and the moons are gone

So no redraft runs, the anchor is left leading nothing, and the board silently runs an anchor
short for as long as that lasts.

MEASURED, by replaying the archive with the current engine and with this one line reverted --
nothing else changed:

    2026-08-23   current   15 violation(s), 2 shapes: 199x builder:4 lunch:1 late:1 moon:8
                                                       15x builder:3 lunch:1 late:1 moon:6
                                                  "ANCHOR SET SHRANK: 4 -> 3 with open moons on
                                                   the board -- a dead anchor left a hole",
                                                   15:57Z through 16:52Z, an hour
                 reverted   0 violation(s), 1 shape: 214x builder:4 lunch:1 late:1 moon:8

    2026-08-27   current   120x builder:1 late:1 lunch:1 moon:2   +  5x builder:2 ... moon:4
                 reverted  125x builder:2 late:1 lunch:1 moon:4   -- twice the board

    2026-08-25   identical, 0 violations either way
    2026-08-26   identical, 0 violations either way
    2026-08-28   0 violations either way, same shape (104x builder:4 late:1 lunch:1 moon:8)

Bisected to the line, not assumed: reverting MINTLOCK-2026-08-29 instead leaves 08-23 at 15
violations, and reverting this leaves it at 0. MINTLOCK is innocent.

AND IT WAS NEVER LOAD-BEARING. The thing it was written to prevent is already prevented, by the
two patches that landed after it:

    MINTLOCK-2026-08-29    the sibling kill exempts locked slips
    CHALKLOCK-2026-08-29   a locked slip is judged on its ANCHOR, not on any leg

Replaying 2026-08-28 with those two in place and THIS reverted: 104 chained builds, 0 violations,
no sealed ticket changed. Murakami's locked slips survive the 23:12Z transition that started all
of this. The joint redraft does emit placed bets verbatim; what broke it that night were the two
bugs above, and CHALKSEATFIX was me avoiding the redraft instead of fixing it.

So the correct answer to "a chalk partner must not tear up a placed bet" is the pair of patches
that make the redraft safe -- not refusing to redraft, which just leaves a hole where an anchor
was. Reverting restores a strictly larger, violation-free board on every day measured.

WHAT THIS DOES NOT DO. It does not re-widen anything beyond the original CHALKSEAT-2026-08-28
behaviour, which ran cleanly for a day before I touched it. The line goes back exactly as it was.

Line comments are forbidden inside index.html's script block (2026-08-08: a `//` swallowed a
`var` declaration and cost a live slate) -- block comments only below.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD = ("        /* CHALKSEATFIX-2026-08-29 -- ONLY IF THE ANCHOR HIMSELF IS CHALK.\n"
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
       "        if(t.kind==='moon'&&t.anchor&&chalk[t.anchor])_chalkSeat[t.anchor]=1;")

NEW = ("        /* UNCHALKSEATFIX-2026-08-29 -- this line briefly read\n"
       "               if(t.kind==='moon'&&t.anchor&&chalk[t.anchor])_chalkSeat[t.anchor]=1;\n"
       "           so that only a chalk ANCHOR recorded a vacated seat. It was written to stop a\n"
       "           chalk PARTNER (Caminero 258->231) triggering the joint redraft that deleted\n"
       "           Murakami's locked \"Climbing the Ladder\". Real problem, wrong fix, and it made a\n"
       "           claim that measurement does not support -- that the pair is repaired leg by leg\n"
       "           instead. It is not: when CHALKOFF evicts an anchor's moons for a chalk PARTNER,\n"
       "           those slips leave `prior` first, so _chalkSeat is empty AND the open-moon scan\n"
       "           below has nothing left to scan. No redraft runs and the anchor is left leading\n"
       "           nothing. Replaying 2026-08-23 with that line: 15 builds at 3 anchors / 6 moons,\n"
       "           15:57Z to 16:52Z; with this one: 214 builds, one shape, 4 anchors, 0 violations.\n"
       "           2026-08-27 went 120x builder:1 moon:2 -> 125x builder:2 moon:4, twice the board.\n"
       "           It was also never load-bearing. MINTLOCK-2026-08-29 (the sibling kill exempts\n"
       "           locked slips) and CHALKLOCK-2026-08-29 (a locked slip is judged on its ANCHOR)\n"
       "           are what actually make the joint redraft safe for placed bets: 2026-08-28 with\n"
       "           those two and this line back to normal replays 104 builds, 0 violations, and\n"
       "           Murakami keeps both locked moons through 23:12Z. */\n"
       "        if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;")

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 CHALKSEATFIX block, found {n} -- the source moved, revert by hand")
src = src.replace(OLD, NEW, 1)
print("  reverted: a chalk partner records the vacated seat again, as CHALKSEAT-2026-08-28 had it")

# guard on the STATEMENT, at its own indent -- the comment above deliberately quotes the old line
# as history, and a substring check would match that quote and abort on a correct patch.
if "\n        if(t.kind==='moon'&&t.anchor&&chalk[t.anchor])_chalkSeat[t.anchor]=1;" in src:
    sys.exit("ABORT: the narrowed guard is still live code")
if src.count("\n        if(t.kind==='moon'&&t.anchor)_chalkSeat[t.anchor]=1;") != 1:
    sys.exit("ABORT: the restored statement is not present exactly once")
if "&&_anch[t.anchor]&&!t.locked)_kill[t.name]=1;" not in src:
    sys.exit("ABORT: MINTLOCK-2026-08-29 is missing -- it is what makes this safe, do not ship without it")
if "function chalkBannedIn(t,set)" not in src:
    sys.exit("ABORT: CHALKLOCK-2026-08-29's dispatch is missing -- it is what makes this safe")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
