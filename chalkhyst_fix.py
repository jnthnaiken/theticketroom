"""
CHALKHYST-2026-08-28 -- the chalk ban had no hysteresis, so the board churned anchors on noise.

WHAT THE OWNER SAW, after CHALKSEAT shipped
    "nah dude murakami only has one moon, and i see 13 tickets. this is not right"

He was right, and CHALKSEAT was only half the fix.

THE MEASUREMENT

`CHALK_N` is 4 and the ban is the four SHORTEST PRICES (CHALKODDS-2026-08-20). Tonight five bats
sat inside a ~50-cent band around that cut line, and they kept trading places:

    Alonso 205 . Olson 208/213 . Schwarber 230/234 . Alvarez 249 . CES 250/251
    Caminero 241 -> 250 -> 252 . Mayo 246 -> 252

A tick of a few cents on any of them rewrites who is banned. Before CHALKSEAT the board answered
that by silently losing an anchor seat (3 anchors / 6 moons, all night). After CHALKSEAT it
answers by running a full joint redraft -- correct, but it means the board now RESHAPES every time
the boundary flips. The owner watched Murakami's second moon appear and disappear between reloads,
and saw Coby Mayo -- barred an hour earlier -- come back as an anchor while Yordan Alvarez, an
anchor on the committed board, went into the ban.

The reader's browser makes this worse, not better: it re-drafts on every page load against LIVE
odds from liveUpdate, which are fresher than the odds baked into the board it was served. So the
browser and the server routinely disagree about who the four shortest prices are, and the reader
sees a different anchor set from the one that was committed. That is exactly what he was looking
at: server board = Goodman / Murakami / Alvarez / Encarnacion-Strand, his screen = Goodman /
Murakami / Mayo / ... , 13 tickets, Murakami leading one moon.

WHY HYSTERESIS IS THE RIGHT ANSWER, AND NOT A WIDER BAN

The board already believes this. CHEF_HYST and ANCH_HYST are both 0.02 of strength() and exist for
exactly this reason -- a seat should not change hands on a difference too small to mean anything.
The chalk ban is the one seat-assignment on the board that had no such guard, and it is the one
whose input (raw market price) is the noisiest.

When two bats are four cents apart, which of them is "the fourth shortest price" is not
information. It is jitter. The ban's purpose -- keep the shortest prices off the parlays -- is
served just as well by either choice, so the tie should go to the incumbent and the board should
stay still.

MEASURED, over every archived build of the last five slates (661 builds):

    date         builds   chalk membership changes: no hysteresis -> CHALK_HYST 0.01
    2026-08-24      160       5  ->  0
    2026-08-25      186       0  ->  0
    2026-08-26      137       1  ->  0
    2026-08-27      126       0  ->  0
    2026-08-28       52       1  ->  0     <- the Mayo flip that started all of this

All seven mid-slate flips in five days were noise, and every one of them is absorbed. 0.01 of
implied probability is not a small margin -- around +250 it is about twelve cents of price, around
+205 about nine. A bat whose price genuinely migrates into the top four still crosses it; a bat
four cents away no longer takes a seat off someone.

THE FIX

  1. INCUMBENCY. `_chalkRank` sorts by implied probability; an incumbent gets +CHALK_HYST on that
     key. A challenger must beat him by more than the margin to take his seat. Everything else
     about the order is untouched, including CHALKTIE-2026-08-22's ascending-TOTAL tiebreak.
  2. MEMORY. The engine writes the ban it settled on to `D.meta.chalk`, beside `D.pool`, so the
     next build -- and, just as importantly, the reader's browser re-drafting against fresher
     odds -- knows who was already banned. With no `D.meta.chalk` (first build of a slate) the
     behaviour is bit-for-bit what it is today.

Line comments are forbidden inside this script block (2026-08-08: a `//` swallowed a `var`
declaration and cost a live slate) -- everything below uses the block form.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

OLD_RANK = ("    var _chalkRank=cand.filter(function(n){return _chalkIpp(n)>=0;})"
            ".sort(function(x,y){return (_chalkIpp(y)-_chalkIpp(x))||(P[x].TOTAL-P[y].TOTAL);});")

NEW_RANK = (
    "    /* CHALKHYST-2026-08-28 -- THE BAN HOLDS ITS SEAT UNLESS IT IS CLEARLY BEATEN.\n"
    "       CHEF_HYST and ANCH_HYST are both 0.02 of strength() because a seat should not change\n"
    "       hands on a difference too small to mean anything. The chalk ban was the one seat on the\n"
    "       board with no such guard, and its input -- the raw market price -- is the noisiest thing\n"
    "       the draft reads. On 2026-08-28 five bats sat inside fifty cents of the CHALK_N cut and\n"
    "       traded places all evening; Caminero drifting +241 -> +250 made Coby Mayo the fourth\n"
    "       shortest without Mayo's own price moving, which cost an anchor, his builder and both his\n"
    "       moons. When two bats are four cents apart, which one is 'the fourth shortest' is not\n"
    "       information, it is jitter, and the ban is served equally well by either -- so the tie\n"
    "       goes to the incumbent and the board stays still.\n"
    "       Measured over 661 archived builds, 08-24..08-28: all seven mid-slate membership changes\n"
    "       were noise, and 0.01 absorbs every one of them. It is not a small margin -- about twelve\n"
    "       cents of price at +250 -- so a real migration into the top four still crosses it.\n"
    "       `_chalkWas` is last build's ban, carried on D.meta.chalk (written beside D.pool below).\n"
    "       Absent -- the first build of a slate -- this is bit-for-bit the old behaviour. It also\n"
    "       matters in the READER'S browser, which re-drafts against fresher odds than the board it\n"
    "       was served and so disagrees with the server about the cut on exactly these boundary\n"
    "       cases. The tiebreak below is untouched (CHALKTIE-2026-08-22, ascending TOTAL). */\n"
    "    var CHALK_HYST=0.01;\n"
    "    var _chalkWas={}; ((D.meta&&D.meta.chalk)||[]).forEach(function(n){_chalkWas[n]=1;});\n"
    "    var _chalkKey=function(n){return _chalkIpp(n)+(_chalkWas[n]?CHALK_HYST:0);};\n"
    "    var _chalkRank=cand.filter(function(n){return _chalkIpp(n)>=0;})"
    ".sort(function(x,y){return (_chalkKey(y)-_chalkKey(x))||(P[x].TOTAL-P[y].TOTAL);});")

OLD_POOL = "    D.pool=nonchalk.slice();"

NEW_POOL = (
    "    D.pool=nonchalk.slice();\n"
    "    /* CHALKHYST-2026-08-28: publish the ban this build settled on, so the next one -- and the\n"
    "       reader's browser, re-drafting on fresher odds -- can hold it. Written here because this\n"
    "       is the first point after the chalk fill loop where the set is final. */\n"
    "    if(D.meta)D.meta.chalk=Object.keys(chalk);")

for old, new, label in ((OLD_RANK, NEW_RANK, 'chalk rank -> incumbency margin'),
                        (OLD_POOL, NEW_POOL, 'D.pool -> publish the ban')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
