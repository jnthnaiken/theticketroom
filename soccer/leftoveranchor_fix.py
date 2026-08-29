"""
LEFTOVERANCHOR-2026-08-28 -- a leftover single is not an anchor, and it was eating the budget.

FOUND BY THE REPAIRED HARNESS, which is the point of repairing it.

redraft() walks the frozen slips and claims an anchor slot for every frozen `builder`. That was
right when it was written (SINGLES-2026-08-27) and the comment says exactly why:

    "On a SINGLES-ONLY board there are no moons at all, so this was the only place the anchor
     could be claimed -- and skipping it left him absent from `takenAnchors`, free of
     `freeForPartner`, and minted a SECOND TIME by the fresh draft. Caught 2026-08-27 building
     the scheduled rebuild: a four-single board came back as seven slips with three players on
     two tickets each."

True, and it stays true. But it rests on an assumption that stopped holding TODAY: that every
single-leg `builder` is an anchor's builder. LEFTOVERS-2026-08-28 introduced a second kind --
a gated player who made no slip, shipped as a straight single. He is not an anchor of anything.

So `builder` now means two different things and the code treats them as one:

    LEFTOVER_CAP = 8    ANCH = 4

Eight leftover singles can freeze and claim EIGHT anchor slots against a budget of four. Then

    var budget = Math.max(0, cfg.ANCH - Object.keys(takenAnchors).length);   -> 0

and nothing can be minted or repaired for the rest of the night. Measured on the pinned
2026-08-26 fixture, scenario 3 of test_redraft (a dead leg on an OPEN moon, with a deep enough
XI that a legal replacement demonstrably exists):

    before   repaired 0 · minted 0 · anchors 8 · demoted [Mbappe: "could not repair the pair"]
    after    the pair repairs, the anchor survives, only the dead leg is swapped

This is the same shape as everything else on 2026-08-28: a rule that was correct until the
meaning of the thing it tested changed underneath it. `_placedLeg` for a seat you GET vs a seat
you are BARRED from; CHALKOFF deleting the evidence REDRAFT needs; and now "a frozen builder is
an anchor" meeting a builder that is not one.

THE FIX -- derive it instead of assuming it

A frozen builder claims an anchor slot when he ACTUALLY anchors something:
    - he leads a moon on this board, or
    - the board has no moons at all (the singles-only case the 08-27 comment is about)
Otherwise he is a leftover, and he is recorded in `spentAsSingle` instead: still barred from
being re-minted and from being drafted as a partner -- which is what `takenAnchors` was really
doing for him -- but no longer spending a seat he does not occupy.

No new field, and nothing to thread through soccer_payload.py: the distinction is already on the
board, in whether a moon names him. A flag would have to survive the Python payload round-trip
and would be one more thing to keep in step.

VERIFIED
    test_redraft.js            scenario 3 repairs; SINGLES-2026-08-27 double-mint guard still
                               holds (a singles-only board still claims, "re-running it does not
                               mint the same anchors again" still passes)
    live 2026-08-28 board      redrafts to the identical six tickets, leg for leg

Line comments are forbidden inside this file's sibling script block, and the same convention is
kept here: block comments only.
"""
import sys

F = 'soccer_draft.js'
src = open(F, encoding='utf-8').read()

OLD_DECL = "    var spentAsPartner = {}, takenAnchors = {}, anchorMatchCounts = {};"
NEW_DECL = ("    var spentAsPartner = {}, takenAnchors = {}, anchorMatchCounts = {}, spentAsSingle = {};\n"
            "    /* LEFTOVERANCHOR-2026-08-28: which frozen builders are REALLY anchors. A builder backs an\n"
            "       anchor when a moon on this board names him, or when there are no moons at all and the\n"
            "       board is singles-only. Anything else is a LEFTOVERS-2026-08-28 single, which anchors\n"
            "       nothing and must not spend a seat against ANCH. */\n"
            "    var frozenMoonAnchor = {};\n"
            "    frozen.forEach(function (t) {\n"
            "      if (t.kind === 'moon' && (t.players || []).length) frozenMoonAnchor[t.players[0].name] = true;\n"
            "    });\n"
            "    var boardHasMoons = (D.tickets || []).some(function (t) { return t.kind === 'moon'; });")

OLD_CLAIM = """        claimAnchor(legs[0]);
      } else {
        legs.forEach(function (l) { spentAsPartner[l.name] = true; });
      }"""
NEW_CLAIM = """        /* LEFTOVERANCHOR-2026-08-28: only if he anchors something. LEFTOVER_CAP is 8 and ANCH
           is 4, so eight frozen leftovers used to claim eight seats against a budget of four and
           zero it out -- no repair, no mint, for the rest of the night. A leftover is spent
           (not re-mintable, not draftable as a partner) without spending a seat. */
        if (frozenMoonAnchor[legs[0].name] || !boardHasMoons) claimAnchor(legs[0]);
        else spentAsSingle[legs[0].name] = true;
      } else {
        legs.forEach(function (l) { spentAsPartner[l.name] = true; });
      }"""

OLD_FREE = "      return placeable(n) && !spentAsPartner[n] && !takenAnchors[n];"
NEW_FREE = "      return placeable(n) && !spentAsPartner[n] && !takenAnchors[n] && !spentAsSingle[n];"

OLD_REM = ("    var remaining = field.filter(function (p) "
           "{ return !usedPartners[p.name] && !takenAnchors[p.name]; });")
NEW_REM = ("    var remaining = field.filter(function (p) "
           "{ return !usedPartners[p.name] && !takenAnchors[p.name] && !spentAsSingle[p.name]; });")

for old, new, label in ((OLD_DECL, NEW_DECL, 'declare spentAsSingle + frozen moon anchors'),
                        (OLD_CLAIM, NEW_CLAIM, 'frozen builder claims a seat only if it anchors'),
                        (OLD_FREE, NEW_FREE, 'a frozen single is not free to partner'),
                        (OLD_REM, NEW_REM, 'a frozen single is not re-mintable')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
