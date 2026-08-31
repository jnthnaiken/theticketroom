"""
UNORPHAN-2026-08-31 -- ORPHANSECTION is removed. It was never a baseball rule.

    owner, 2026-08-31: "orphan is not part of baseball, get rid of it. especially if its
                        messing things up"

Both halves of that are right, and the second follows from the first.

## IT IS NOT A BASELINE RULE, AND BASEBALL EXPLICITLY DECIDED AGAINST IT

index.html:1006, live on the MLB board today:

    const _stranded=t=>t.kind==='builder'&&t.anchor&&!_mAnch[t.anchor];
    /* SEAT-LOCK's split sent a stranded anchor single into the Dingers section, because with
       Dingers on the board that was the honest place for a one-bat, one-price slip. With the
       section retired there is nowhere else for it to go, and it must not vanish -- it is a real
       placed builder and it grades as one. So it renders under Anchors again, where its own kind
       always said it belonged. `_stranded` is left defined; nothing else calls it. */

Baseball had this exact question -- what do we do with a builder whose bat holds no moons -- and
answered it: NOTHING. He is a builder, he renders under Anchors, he grades as a builder. The
predicate that would have moved him is left in the file with nothing calling it.

Baseball's lunch special and nightcap are not where demoted anchors go. They are their own
sections, MINTED FROM THE FIELD by SHAPE REPAIR (index.html:2755, REDRAFT-2026-08-18). Soccer got
the demotion and never got the mint, which is why the owner could ask "shouldn't someone fall
through to the specials" and the honest answer was "only an anchor can, and only by dying".

## AND IT IS WHAT WAS MESSING THINGS UP

ORPHANSECTION relabels a slip's `kind`, and that label PERSISTS onto the next build's prior board.
Every rule downstream then has to cope with a slip that is a builder by shape and a lunch special
by name. The file says so itself, in the promotion block this patch also fixes:

    ⚠️ TWO RULES ALREADY DEMOTED HIM, AND BOTH HAVE TO BE READ TO FIND HIM AGAIN.
    ORPHANSECTION-2026-08-29 reseats a moonless single into the lunch/nightcap section, and that
    `kind` PERSISTS on the board -- Lautaro's surviving slip came back as `lunch`, not `builder`.
    ... So a demoted anchor is invisible under both his kind AND his anchor status, and looking
    for a builder finds nothing. Match the SHAPE instead: one leg, still ahead of the clock,
    still alive.

"Match the shape instead" is the compensation, and it is the ratchet. Measured 2026-08-31 while
testing SHAPEREPAIR: because that block adopts ANY single-leg slip as a zero-moon anchor,
FINALREPAIR then builds it a pair, and a lunch special becomes a full anchor with two screamers
on the very next build. Reproduced on the UNPATCHED engine -- seed the current drafter with an
ORPHANSECTION-shaped lunch and redraft once: 7 slips become 9, `topped` naming the lunch player as
an anchor. That is live today; it stays hidden only because orphans appear late, when MINTGUARD
has already closed the field.

Remove the relabel and the compensation is not needed: a moonless single IS a builder again, so
the promotion block can look for a builder, which is what it wanted to do in the first place.

## WHAT IS REMOVED

The ORPHANSECTION / ORPHANSURPLUS / ANCHORISMOONS reclassify block in redraft(), whole. A
single-leg slip keeps the `kind` it was drafted with. `reseated` stays in the return shape and is
now always empty -- soccer_rebuild_cli.js and the workflow log read it, and a key that vanishes is
a crash somewhere I have not looked.

## WHAT IS KEPT, AND WHY

- The SECTIONS. 🍱 and 🌃 are baseball sections and they stay; SHAPEREPAIR-2026-08-31 mints into
  them from the field, which is what baseball does and what the owner asked for.
- LEFTOVERANCHOR-2026-08-28: a single-leg builder anchors nothing and must not spend a seat
  against ANCH. That is orthogonal and still true.
- The promotion block itself, NARROWED. Its purpose -- REPAIRPAIR-2026-08-30, Lautaro Martinez
  left as a stranded single when both screamers failed repair and the ungated top-up could not
  reach him -- is real and was measured. Only its predicate changes, from "any single-leg slip"
  back to "a builder", which is what it says it wanted.

## THE LEDGER

⚠️ soccer_grade.py's KINDS and soccer_payload's `cats` book by kind. ORPHANSURPLUS-2026-08-29
recorded what that means: a reseat moved a WINNING anchor single out of ⚓️ into 🍱 and the season
line went from "Anchors 8-5 +3.6u / Lunch 0-0" to "Anchors 7-5 +2.8u / Lunch 1-0 +0.8u" for a bet
that never stopped being an anchor. Removing the reseat means those slips book as builders, which
is what they are. The one already-graded reseat is 2026-08-29's lunch (1-0, +0.75u on 1.0u
staked). Whether to move it back in soccer_season.json is the owner's call, not a side effect of
a code change -- exactly the line UNLEFTOVER-2026-08-28 drew about its own three slips.
"""
import sys

F = 'soccer_draft.js'
src = open(F, encoding='utf-8').read()

if 'UNORPHAN-2026-08-31' in src:
    sys.exit('ABORT: already applied')
if 'ORPHANSECTION-2026-08-29 -- a single with no moons behind it is a LUNCH SPECIAL' not in src:
    sys.exit('ABORT: no ORPHANSECTION block found -- nothing to remove')

# 1. THE RECLASSIFY BLOCK -- from its banner down to (not including) SHORTLAST's banner.
start_marker = """    var reseated = [];
    /* 🚨 ONLY THE SURPLUS IS A LEFTOVER. ORPHANSURPLUS-2026-08-29."""
end_marker = """    /* ==================================================================================
     * SHORTLAST-2026-08-29 -- an anchor that is short a screamer sorts to the BOTTOM."""

if src.count(start_marker) != 1 or src.count(end_marker) != 1:
    sys.exit('ABORT: could not bracket the reclassify block -- back out by hand')
start = src.index(start_marker)
end = src.index(end_marker)
if end <= start:
    sys.exit('ABORT: markers out of order')

HEADSTONE = """    /* UNORPHAN-2026-08-31. THE ORPHANSECTION RECLASSIFY LIVED HERE AND IS GONE, NOT DISABLED.
     * Owner: "orphan is not part of baseball, get rid of it. especially if its messing things up."
     *
     * ORPHANSECTION-2026-08-29 / ORPHANSURPLUS / ANCHORISMOONS rewrote a moonless single-leg
     * slip's `kind` to 'lunch' or 'late'. Baseball had the same question and answered it the
     * other way, and the answer is still in index.html:1006 with nothing calling it:
     *
     *     const _stranded=t=>t.kind==='builder'&&t.anchor&&!_mAnch[t.anchor];
     *     /* ... it is a real placed builder and it grades as one. So it renders under Anchors
     *        again, where its own kind always said it belonged. `_stranded` is left defined;
     *        nothing else calls it. *(/)
     *
     * Baseball's 🍱 and 🌃 are not where demoted anchors go -- they are minted from the FIELD by
     * SHAPE REPAIR (index.html:2755). Soccer took the demotion and never took the mint.
     * SHAPEREPAIR-2026-08-31 adds the mint; this removes the demotion.
     *
     * It was also the ratchet. The relabel PERSISTS onto the next build's prior board, so the
     * promotion block below had to match a slip's SHAPE rather than its kind to find a demoted
     * anchor again -- which meant it adopted ANY single-leg slip as a zero-moon anchor and
     * FINALREPAIR built it a pair. Reproduced on the unpatched engine: a lunch special becomes a
     * full anchor with two screamers on the next build, 7 slips to 9. With the relabel gone a
     * moonless single IS a builder, so that block looks for a builder again.
     *
     * `reseated` stays and is now always empty: soccer_rebuild_cli.js and the workflow read it,
     * and a key that vanishes is a crash somewhere I have not looked. */
    var reseated = [];

"""

src = src[:start] + HEADSTONE + src[end:]
print('  removed the ORPHANSECTION reclassify and left a headstone')

# 2. THE PROMOTION BLOCK -- back to a builder, which is what its own comment wanted.
OLD_PROMO = """    /* ⚠️ TWO RULES ALREADY DEMOTED HIM, AND BOTH HAVE TO BE READ TO FIND HIM AGAIN.
     * ORPHANSECTION-2026-08-29 reseats a moonless single into the lunch/nightcap section, and
     * that `kind` PERSISTS on the board -- Lautaro's surviving slip came back as `lunch`, not
     * `builder`. LEFTOVERANCHOR-2026-08-28 then spends him as a single rather than an anchor,
     * because `frozenMoonAnchor` is false once his moons are gone. So a demoted anchor is
     * invisible under both his kind AND his anchor status, and looking for a builder finds
     * nothing. Match the SHAPE instead: one leg, still ahead of the clock, still alive.
     * The ANCH budget is the guard that keeps this honest -- a genuine lunch special is only
     * ever promoted when the board is actually SHORT of anchors, which is exactly the state a
     * demoted pair leaves behind. A full board promotes nobody. */
    var _anchorsNow = Object.keys(takenAnchors).length + (res.anchors || 0);
    out.forEach(function (t) {
      var legs = t.players || [];
      if (legs.length !== 1) return;
      if (t.kind === 'moon') return;
      var an = legs[0].name;"""

NEW_PROMO = """    /* A DEMOTED ANCHOR IS A BUILDER, AND THAT IS HOW WE FIND HIM AGAIN.
     * REPAIRPAIR-2026-08-30's case is real and measured: when both of Lautaro Martinez's
     * screamers failed repair the all-or-none pair rule took them, `moonCnt` had no entry for
     * him, and the ungated top-up below -- which had candidates the whole time -- could not
     * reach him. A builder on the board IS the board's commitment to that anchor, so seed him at
     * zero and let the same block rebuild his pair.
     *
     * ⚠️ NARROWED BY UNORPHAN-2026-08-31. This used to match one-leg SHAPE rather than kind,
     * because ORPHANSECTION had relabelled the demoted anchor 'lunch' and looking for a builder
     * found nothing. That relabel is gone, so the kind is honest again -- and matching shape is
     * exactly what turned a minted lunch special into a full anchor with two screamers on the
     * next build. A 🍱 or 🌃 is NOT a stranded anchor: it is its own bet, in its own section,
     * and it is not promoted into the anchors by a top-up. It stays one leg for the night.
     *
     * The ANCH budget still guards this -- a board that is not short of anchors promotes
     * nobody. */
    var _anchorsNow = Object.keys(takenAnchors).length + (res.anchors || 0);
    out.forEach(function (t) {
      var legs = t.players || [];
      if (legs.length !== 1) return;
      if (t.kind !== 'builder') return;
      var an = legs[0].name;"""

if src.count(OLD_PROMO) != 1:
    sys.exit('ABORT: the promotion block does not look as expected -- back out by hand')
src = src.replace(OLD_PROMO, NEW_PROMO, 1)
print('  narrowed the promotion block from one-leg SHAPE back to kind builder')

# 3. THE DEAD LOCALS. `moonAnchorOnBoard` / `outHasMoons` existed ONLY to feed the reclassify --
#    they are computed and never read once it is gone. Leaving them is how the next reader spends
#    twenty minutes working out which rule still depends on them. (`boardHasMoons`, line ~555, is
#    a DIFFERENT variable read by the frozen-builder branch, and is untouched.)
OLD_DEAD = """    var moonAnchorOnBoard = {}, outHasMoons = false;
    out.forEach(function (t) {
      if (t.kind === 'moon' && (t.players || []).length) {
        moonAnchorOnBoard[t.players[0].name] = true; outHasMoons = true;
      }
    });
"""
if src.count(OLD_DEAD) != 1:
    sys.exit('ABORT: could not find the moonAnchorOnBoard scan')
src = src.replace(OLD_DEAD, '', 1)
print('  removed moonAnchorOnBoard / outHasMoons, dead once the reclassify is gone')

# guard: no live reference to the removed block may survive. Prose in headstones is history.
for bad in ('moonAnchorOnBoard[n] ?', "t.kind = moonAnchorOnBoard"):
    if bad in src:
        sys.exit(f'ABORT: live reference `{bad}` still present -- back out by hand')

open(F, 'w', encoding='utf-8').write(src)
print(f'unorphan_fix: patched {F} ({len(src)} bytes)')
