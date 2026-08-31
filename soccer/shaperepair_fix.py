"""
SHAPEREPAIR-2026-08-31 -- the specials are part of the board's shape, and only an anchor could
ever reach them.

    owner, 2026-08-31: "yea it shouldnt be only anchors that can fall through to the specials"
    ruling, same session: the lunch special is a FIXED SHAPE, like baseball's.

THE GAP

ORPHANSECTION-2026-08-29 puts a moonless single in the lunch special or the nightcap. It
RECLASSIFIES a slip already in `out` -- it never mints one:

    out.forEach(function (t) {
      if (!outHasMoons) return;
      if (t.kind !== 'builder' && t.kind !== 'lunch' && t.kind !== 'late') return;

The only thing that can BE such a single is an anchor's builder, so the specials were reachable
by exactly one route: be drafted as an anchor first, then lose your screamers. When the anchor
himself dies, his builder dies with him and there is nothing left to fall through.

Measured tonight on the published board (`/tmp/sim/sim.js`, prior.json = the live 3 tickets):

    now=1139 out=[Gabriel Jesus, Raphinha]
      tickets 0  anchors 0  minted=0 repaired=0 demoted=["anchor is no longer startable"]

Zero, with 24 alive priced players sitting in two matches that had not kicked off. The fresh-draft
arm ran with a full budget and returned nothing, because a screamer needs MOON_LEGS legs from
three DIFFERENT matches and MINTGUARD leaves only two -- and `anchorsOnly()` does not fire either,
because its gate is `slateMatches < MOON_LEGS` and `slateMatches` counts every match on the DAY,
not the matches still open. Five is not less than three, so the board never enters singles mode at
the moment it actually is in one.

BASEBALL ALREADY HAS THIS, AND IT IS THE MODEL

index.html:2755, SHAPE REPAIR -- REDRAFT-2026-08-18:

    "The board's shape is fixed: four anchors x two moons, one nightcap, one lunch play. The moon
     half of that is repaired directly above; the two singles never were ... A PLACED single that
     dies stays dead: that is a settled bet. An EMPTY SLOT gets drafted, same as a short anchor."

It mints from `byS(nonchalk)` -- the whole field -- not from the anchors, one per empty section,
under `!started(n)`. This is that block, in soccer's spelling: `alive[]` for the XI filter (a man
dropped from a published XI is not flagged `out` on this board -- see the REPAIRWIDE note, which
re-drafted Luka Jovic on the first cut of that port), `freeForPartner()` for MINTGUARD and the
partner/anchor/burnt-single exclusions, TOTAL order with a name tiebreak for determinism.

THIS IS NOT UNLEFTOVER-2026-08-28 COMING BACK

That section minted a single for EVERY gated player who made no slip, one unit each, capped at
eight -- six extra slips a night on a healthy board. This mints AT MOST ONE per empty section,
and only when the section is empty, which is the same cap REDRAFT-2026-08-18 states for baseball:
"one nightcap and one lunch play, full stop."

Measured over the five committed boards, grading each mint off that board's own settled `hr`:

    2026-08-27   singles-only slate  -> excluded (see the guard below)
    2026-08-28   Christian Pulisic  +150   lost   -1.00u
    2026-08-29   already has a lunch -> no mint
    2026-08-30   Carlos Espi        -138   lost   -1.00u
    2026-08-31   Donyell Malen      +100   WON (4', 23')   +1.00u
                 -------------------------------------------------
                 3 slips, 3u staked, -1.00u

Three slips is not a sample and the owner's ruling was about SHAPE, not that number. Recorded so
the next reader does not mistake it for evidence in either direction.

NOT ON A SINGLES-ONLY SLATE, and the guard is the SLATE, not the board. ORPHANSECTION uses
`outHasMoons`, which is false in two very different situations: a two-match slate where every
builder IS an anchor (SINGLES-2026-08-27 -- reclassifying there "turned it into four lunch
specials on the first cut", caught by test_redraft), and a board that drafted NOTHING, which is
exactly the case this exists for. So the test here is `Object.keys(KO).length < cfg.MOON_LEGS` --
SINGLES-2026-08-27's own condition, asked of the slate directly.

WHERE IT RUNS

`redraft()` only, after the ORPHANSECTION reclassify (so `haveKind` reads final kinds) and before
the SHORTLAST/ANCHORGROUP display sort. Deliberately NOT in `draft()`: test_draft_golden.js pins
the 2026-08-26 board slip-for-slip and asserts the drafter ships "MOONS and their ANCHOR BUILDERS
and nothing else". Adding a mint there would rewrite the golden, and a golden you rewrite to pass
is not a golden. Consequence to know: the first build of a slate has no prior and takes the fresh
`draft()` path, so a new day's lunch special appears on the SECOND build, ~5 minutes later.

⚠️ THE LEDGER BOOKS BY KIND. soccer_grade.py's KINDS and soccer_payload's `cats` split by kind, so
these slips land in `cats.lunch` / `cats.late` and nowhere else -- the same warning
ORPHANSURPLUS-2026-08-29 raised when a reseat moved a winning anchor out of the anchors column.
That is intended here: they really are lunch specials. They are new exposure, not a reshuffle.

⚠️ THE NIGHTCAP ARM IS PRESENT AND CANNOT CURRENTLY FIRE. soccer_payload.py:219 sets
`'late': et_min(ko_of(match)) >= 17 * 60` -- 5:00 PM ET, inherited from baseball, where it means a
night game. European football is over by then: across the five committed boards, 0 of 818 players
carry the flag, and the season ledger agrees (`late: graded 0`). The arm is written so that fixing
the threshold is a one-line change to the payload and not a change here. Flagged to the owner
2026-08-31, not yet ruled on.
"""
import sys

F = 'soccer_draft.js'
src = open(F, encoding='utf-8').read()

# NB: check for the CODE, not the tag. UNORPHAN-2026-08-31's headstone cites SHAPEREPAIR by name,
# so a tag search reports "already applied" against a file that has none of this patch in it.
if 'var shaped = [];' in src:
    sys.exit('ABORT: already applied')

# The insertion point used to be the tail of the ORPHANSECTION reclassify. UNORPHAN-2026-08-31
# deleted that block, so anchor on what it left behind: the `reseated` declaration and the
# SHORTLAST banner that follows it.
ANCHOR = """    var reseated = [];

    /* ==================================================================================
     * SHORTLAST-2026-08-29 -- an anchor that is short a screamer sorts to the BOTTOM."""

NEW = """    var reseated = [];

    /* ==================================================================================
     * 🚨 THE SPECIALS ARE PART OF THE SHAPE. SHAPEREPAIR-2026-08-31.
     * ==================================================================================
     * Owner: "yea it shouldnt be only anchors that can fall through to the specials."
     *
     * ORPHANSECTION above RECLASSIFIES a single that is already in `out`; it never mints one. The
     * only thing that can BE such a single is an anchor's builder, so the lunch special and the
     * nightcap were reachable by exactly one route -- be drafted as an anchor, then lose your
     * screamers. When the anchor dies his builder dies with him and nothing is left to fall
     * through: on 2026-08-31, with Raphinha struck out, the board redrafted to ZERO tickets while
     * 24 alive priced players sat in two matches that had not kicked off.
     *
     * This is index.html's SHAPE REPAIR (REDRAFT-2026-08-18) in soccer's spelling -- "The board's
     * shape is fixed ... A PLACED single that dies stays dead: that is a settled bet. An EMPTY
     * SLOT gets drafted, same as a short anchor." One per empty section, from the whole field,
     * which is the same cap that block states: "one nightcap and one lunch play, full stop."
     *
     * ⚠️ NOT UNLEFTOVER-2026-08-28. That minted a single for EVERY gated player who made no slip,
     * capped at eight -- six a night on a healthy board. This mints at most one, and only into a
     * section that is empty. Measured over the five committed boards: 3 slips, -1.00u, which is
     * not a sample and is recorded in shaperepair_fix.py only so nobody mistakes it for evidence.
     *
     * ⚠️ THE GUARD IS THE SLATE, NOT THE BOARD. `outHasMoons` is false both on a two-match
     * singles-only slate -- where every builder IS an anchor, and reclassifying "turned it into
     * four lunch specials on the first cut" -- and on a board that drafted nothing, which is the
     * case this exists for. So ask the slate directly, which is SINGLES-2026-08-27's own test.
     *
     * `alive[]` and not `!p.out`: a man dropped from a published XI is not flagged `out` on this
     * board, and the first cut of the REPAIRWIDE port used the baseball spelling literally and
     * re-drafted the very leg team news had just removed. `freeForPartner()` carries MINTGUARD
     * (no slip created past its own kickoff) and the partner / anchor / burnt-single exclusions.
     * TOTAL order with a name tiebreak, so the pick is deterministic and testable. */
    var shaped = [];
    if (Object.keys(KO).length >= cfg.MOON_LEGS) {
      var haveKind = {}, onBoard = {};
      out.forEach(function (t) {
        haveKind[t.kind] = true;
        (t.players || []).forEach(function (l) { onBoard[l.name] = true; });
      });
      [['lunch', false], ['late', true]].forEach(function (spec) {
        var kind = spec[0], wantLate = spec[1];
        if (haveKind[kind]) return;
        var c = Object.keys(D.players).filter(function (n) {
          return !onBoard[n] && alive[n] && freeForPartner(n) &&
                 !!(D.players[n].late) === wantLate;
        }).sort(function (x, y) {
          var dx = (D.players[y].TOTAL || 0) - (D.players[x].TOTAL || 0);
          return dx || (x < y ? -1 : x > y ? 1 : 0);
        });
        if (!c.length) return;
        var n = c[0];
        out.push(mkTicket(kind, [legOf(n, D.players[n])], cfg.SINGLE_STAKE,
                          pickName(kind, null), koOf, D.players));
        onBoard[n] = true;
        haveKind[kind] = true;
        shaped.push({ name: n, kind: kind });
      });
    }

    /* ==================================================================================
     * SHORTLAST-2026-08-29 -- an anchor that is short a screamer sorts to the BOTTOM."""

n = src.count(ANCHOR)
if n != 1:
    sys.exit(f'ABORT: expected exactly 1 insertion point, found {n} -- the source moved')
src = src.replace(ANCHOR, NEW, 1)

# ---------------------------------------------------------------------------------------------
# NAMES / BADGE. The drafter's pools carry `moon` and `builder` only, because until now those were
# the only kinds it could MINT -- ORPHANSECTION reaches 'lunch' and 'late' by rewriting `t.kind` on
# a slip that already has a builder's title. A minted special has no title to inherit, and
# pickName()'s fallback is `NAMES[kind] || ['Ticket']`, so the first run of this shipped a slip
# literally called "Ticket". NAMECARRY-2026-08-29 makes that stick: soccer_payload.shape_ticket
# USES the title the draft assigned and only walks its own pool when there is none.
#
# So the pools go here, copied EXACTLY from soccer_payload.py's NAMES/BADGE. Two copies, one rule
# -- the same standing hazard as WIN / Z_GATE across soccer_draft.DEFAULTS and soccer_mock.CFG. If
# one side changes, change both.
OLD_NAMES = """    builder: ['Target Man', 'The Poacher', 'Six-Yard Box', 'Back Post', 'Near Post', 'The Nine',
              'First Time', 'Gets Across', 'Runs the Channel', 'Shoulder of the Last Man']
  };
  var BADGE = { moon: '💥', builder: '⚓️' };"""

NEW_NAMES = """    builder: ['Target Man', 'The Poacher', 'Six-Yard Box', 'Back Post', 'Near Post', 'The Nine',
              'First Time', 'Gets Across', 'Runs the Channel', 'Shoulder of the Last Man'],
    /* SHAPEREPAIR-2026-08-31. Until now the drafter could only MINT moons and builders --
       ORPHANSECTION reaches 'lunch' and 'late' by rewriting `t.kind` on a slip that already
       carries a builder's title. A minted special has no title to inherit and pickName() fell
       through to its `|| ['Ticket']` fallback, shipping a slip called "Ticket" -- and
       NAMECARRY-2026-08-29 makes that stick, because soccer_payload.shape_ticket USES the title
       the draft assigned. Copied EXACTLY from soccer_payload.py's NAMES; two copies, one rule,
       same as WIN / Z_GATE across DEFAULTS and soccer_mock.CFG. Change one, change both. */
    lunch:   ['Early Doors', 'Lunchtime Kickoff', 'The Twelve Thirty', 'First Match On'],
    late:    ['Under Lights', 'Last One On', 'The Late Kickoff', 'Sunday Night']
  };
  var BADGE = { moon: '💥', builder: '⚓️', lunch: '🍱', late: '🌃' };"""

if src.count(OLD_NAMES) != 1:
    sys.exit('ABORT: could not find the NAMES/BADGE block')
src = src.replace(OLD_NAMES, NEW_NAMES, 1)

# (The ORPHANSECTION guard patch that used to sit here is GONE. It fixed `!outHasMoons` -- a fact
# about the BOARD standing in for a fact about the SLATE -- so that a carried lunch would be
# relabelled back to 'lunch' instead of returning as a 'builder' and provoking a second mint.
# UNORPHAN-2026-08-31 deletes the reclassify block outright, on the owner's call that it was never
# a baseball rule, so there is no guard left to fix. The churn it was patching is now handled at
# the root: a minted special keeps its own kind, and the promotion block below looks for a
# 'builder', so a 🍱 is never adopted as a stranded anchor and never topped up into a pair.)

# ---------------------------------------------------------------------------------------------
# THE REPAIR PATH DESTROYED THE SLIP'S KIND, and that is the ratchet's actual root.
#
# The anchor-group split is `if (t.kind === 'moon') ... else groups[a].builders.push(t)`, so every
# single-leg slip -- lunch, nightcap, builder alike -- lands in `g.builders`. It was then re-emitted
# with the kind HARDCODED:
#
#     repaired.push({ kind: 'builder', legs: [rowOf(an)], risk: cfg.SINGLE_STAKE, priorName: b.name });
#
# So a 🍱 that is not yet frozen comes back a builder every single build. With ORPHANSECTION in the
# file that was invisible: the reclassify relabelled it 'lunch' again a few lines later, which is
# precisely why nobody noticed the repair was lying about the slip's kind. UNORPHAN removed the
# relabel, and the bug stood up in the open -- measured on tonight's real board, where the minted
# lunch is open rather than frozen:
#
#     pass1  4 tix   lunch   Early Doors        = Yamal
#     pass2  5 tix   builder Early Doors        = Yamal      + lunch | Lunchtime Kickoff = Gyokeres
#     pass3  6 tix   builder Early Doors        = Yamal      + builder ... + lunch | ... = Adeyemi
#
# (The 2026-08-26 fixture hid it a second way: there the lunch is all-confirmed, so CONFLOCK freezes
# it and it never enters the repair path at all. Two different masks over one bug -- which is why
# the iteration test runs against BOTH the fixture and the live board.)
#
# A repair swaps a LEG. It has never been entitled to change what kind of bet a slip is, and
# REDRAFT-2026-08-18 is emphatic about the consequences of a slip changing identity underneath a
# reader. So carry the slip's own kind, and its own stake with it.
OLD_REEMIT = """      g.builders.forEach(function (b) {
        repaired.push({ kind: 'builder', legs: [rowOf(an)], risk: cfg.SINGLE_STAKE, priorName: b.name });
      });"""
NEW_REEMIT = """      g.builders.forEach(function (b) {
        /* ⚠️ `b.kind`, NOT 'builder'. SHAPEREPAIR-2026-08-31. The group split above files every
           single-leg slip under `builders`, so a 🍱 lunch special or a 🌃 nightcap arrives here
           too -- and hardcoding the kind turned it back into a builder on every build. That was
           masked for as long as ORPHANSECTION existed to relabel it a few lines later, and stood
           up the moment UNORPHAN removed the relabel: the specials section emptied, shape repair
           minted a fresh single into it, and the board grew by one slip every five minutes.
           A repair swaps a LEG. It does not get to change what kind of bet the slip is. */
        repaired.push({ kind: b.kind || 'builder', legs: [rowOf(an)], risk: cfg.SINGLE_STAKE,
                        priorName: b.name });
      });"""
if src.count(OLD_REEMIT) != 1:
    sys.exit('ABORT: the builder re-emit does not look as expected')
src = src.replace(OLD_REEMIT, NEW_REEMIT, 1)

# report it, next to the other counters
OLD_RET = """      reseated: reseated,
      topped: topped,"""
NEW_RET = """      reseated: reseated,
      shaped: shaped,
      topped: topped,"""
if src.count(OLD_RET) != 1:
    sys.exit('ABORT: could not find the return block')
src = src.replace(OLD_RET, NEW_RET, 1)

open(F, 'w', encoding='utf-8').write(src)
print(f'shaperepair_fix: patched {F} ({len(src)} bytes)')
