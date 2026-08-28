"""
REVERT CHALKHYST-2026-08-28 -- the incumbency margin can INVERT the ban, which is worse than the
churn it was meant to cure.

Shipped at 21:2xZ; backed out ~40 minutes later off the live board it produced:

    #4  +249  Yordan Alvarez                 ANCHORING
    #5  +250  Christian Encarnacion-Strand   BANNED

The ban is "the four shortest prices" (CHALKODDS-2026-08-20). Holding an incumbent at the
boundary necessarily means a LONGER price is banned while a SHORTER price plays -- there is no
version of the margin that avoids that, because the set is fully determined by price order. So
the mechanism cannot be tuned; it is wrong in kind. Owner, looking at the board it produced:
"is this the correct draft or did people get left off on some bullshit again?" Encarnacion-Strand
was, and by one cent.

The churn it was aimed at was also mis-attributed. Measured on the SERVER's archived builds, the
chalk membership changed ONCE in 52 builds today and once in 137 on 08-26 -- it is not unstable.
What the owner was watching was the reader's browser re-drafting against liveUpdate odds that are
fresher than the odds baked into the board it was served, so the screen and the committed board
disagree about the cut. That is a real problem and it is still open, but the ban rule was never
the cause and must not pay for it.

The right shape for that fix is to DEBOUNCE THE ACTION, not the ban: let the ban be exactly the
four shortest at every instant, and require a flip to persist before it is allowed to tear up the
open board. At rest the ban is then always correct. Not shipping that at 5:30pm on a live slate
with games underway.

CHALKSEAT-2026-08-28 stays -- it is separately measured and correct.
"""
import sys

BOARD = 'index.html'
src = open(BOARD, encoding='utf-8').read()

if 'CHALKHYST-2026-08-28' not in src:
    sys.exit('ABORT: no CHALKHYST block found -- nothing to revert')

start = src.index('    /* CHALKHYST-2026-08-28 -- THE BAN HOLDS ITS SEAT')
marker = '    var _chalkRank=cand.filter(function(n){return _chalkIpp(n)>=0;})'
idx = src.index(marker, start)
ORIG_RANK = ("    var _chalkRank=cand.filter(function(n){return _chalkIpp(n)>=0;})"
             ".sort(function(x,y){return (_chalkIpp(y)-_chalkIpp(x))||(P[x].TOTAL-P[y].TOTAL);});")
end = src.index('});', idx) + 3
src = src[:start] + ORIG_RANK + src[end:]
print('  reverted chalk rank -> plain four shortest prices')

PUB = ("    /* CHALKHYST-2026-08-28: publish the ban this build settled on, so the next one -- and the\n"
       "       reader's browser, re-drafting on fresher odds -- can hold it. Written here because this\n"
       "       is the first point after the chalk fill loop where the set is final. */\n"
       "    if(D.meta)D.meta.chalk=Object.keys(chalk);\n")
n = src.count(PUB)
if n != 1:
    sys.exit(f'ABORT: expected exactly 1 D.meta.chalk publish block, found {n}')
src = src.replace(PUB, '', 1)
print('  reverted D.meta.chalk publish')

if 'CHALKHYST-2026-08-28' in src:
    sys.exit('ABORT: CHALKHYST traces remain -- revert by hand')
if 'CHALKSEAT-2026-08-28' not in src:
    sys.exit('ABORT: CHALKSEAT was removed too -- do not ship this')

open(BOARD, 'w', encoding='utf-8').write(src)
print(f'wrote {BOARD} ({len(src)} bytes) -- CHALKSEAT retained')
