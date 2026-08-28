"""
CHALKOBS-2026-08-28 -- the engine states which bats it banned, so nothing has to guess.

WHY THIS EXISTS, and it is not the reverted CHALKHYST.

CHALKHYST-2026-08-28 used a stored `D.meta.chalk` as INPUT -- an incumbency margin that let last
build's ban hold its seat. That was wrong in kind and is reverted. This writes the same field as
pure OUTPUT: nothing in the engine reads it, no draft decision depends on it, and deleting it
changes no board. It is a statement of fact about the build that just ran.

WHAT IT IS FOR

Two things tonight needed to know the ban and could not ask:

  1. Diagnosing CHALKPLACED-2026-08-28 required hand-instrumenting the chalk fill loop on a live
     board to print its own decision. That is the second time today the answer only came from
     instrumenting the running engine (the first was SLATEDAY). An engine that will not say what
     it did makes every such diagnosis a patch-and-rerun.

  2. replay_check.js's SEALED assertion does not model CHALKOFF-2026-08-26, so it reports a
     violation every time a locked chalk slip is correctly evicted. It has been failing on that
     for two days. The obvious fix -- have the harness recompute the ban itself -- is the
     assemble_tickets.py mistake in miniature: two implementations of one rule, drifting, and
     today was a whole day of exactly that class of bug. So the engine publishes, and the harness
     reads. One implementation, one source of truth.

WHERE

Beside `D.pool`, which is the first point after the chalk fill loop where the set is final, and
which is already the place the engine publishes what it decided.

Line comments are forbidden inside this script block (2026-08-08: a `//` swallowed a `var`
declaration and cost a live slate) -- everything below uses the block form.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

if 'CHALKHYST' in src:
    sys.exit('ABORT: CHALKHYST is still present -- this patch must not be confused with it')

OLD = "    D.pool=nonchalk.slice();"

NEW = ("    D.pool=nonchalk.slice();\n"
       "    /* CHALKOBS-2026-08-28: publish the ban this build settled on. OUTPUT ONLY -- nothing in\n"
       "       the engine reads it and no draft decision depends on it, so deleting it changes no\n"
       "       board. It exists because two separate diagnoses today (SLATEDAY, CHALKPLACED) could\n"
       "       only be made by hand-instrumenting the running engine, and because replay_check.js\n"
       "       needs the ban to know that a vanished locked slip was a lawful CHALKOFF eviction\n"
       "       rather than a violation. The harness reading this is the whole point: a harness that\n"
       "       recomputed the ban itself would be a second implementation of the rule, which is the\n"
       "       exact failure mode that produced most of 2026-08-28.\n"
       "       NOT CHALKHYST. That patch read a stored ban back as INPUT to hold an incumbent's\n"
       "       seat; it inverted the ban and is reverted. This one is write-only. */\n"
       "    if(D.meta)D.meta.chalk=Object.keys(chalk);")

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 `D.pool=nonchalk.slice();`, found {n} -- "
             f"the source moved, patch by hand")
src = src.replace(OLD, NEW, 1)
print("  patched D.pool -> publish the ban (write-only)")

open(BOARD, 'w', encoding='utf-8').write(src)
print(f"wrote {BOARD} ({len(src)} bytes)")
