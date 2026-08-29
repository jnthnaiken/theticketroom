"""
UNLEFTOVER-2026-08-28 -- back out LEFTOVERS. I resurrected a section the owner retired.

    owner, 2026-08-29: "bro there is no leftover section anymore"

He is right, and the retirement is written down in two places I had read:

    soccer_mock.py, SCREAMERS-2026-08-26:
      "the leftover section is RETIRED, matching the MLB Dingers retirement (family went
       11-80 / -33.34u there). No `family` tickets are minted."

    index.html, DINGERS=false 2026-08-25, owner: "its just bleeding money"
      11-80 for -33.34u on 91 staked, -36.6% ROI -- the worst line on the board and the only
      kind materially negative on a real sample. Its 12 graded nights were BACKED OUT of
      season.json.

LEFTOVERS-2026-08-28 was that section again. It shipped every gated player who made no slip as a
straight single, capped at eight. Measured on the pinned 2026-08-26 fixture, on a HEALTHY board
with the moons all built:

    LEFTOVER SINGLES minted: 6      Oskarsson +350, Ceh +200, Kukharevych +200,
                                    Prevljak +200, Himbert +210, Tripic +210
    extra staked: 6u a night, on the longest prices that cleared the gate and nothing more

That is the retired section, in its own shape -- the dross beneath the draft, one unit each. It
went unnoticed because I minted it as `kind: 'builder'` rather than `kind: 'family'`, so every
check that enforces the retirement looked straight past it.

WHAT THE OWNER ACTUALLY ASKED FOR, and why this is not it

2026-08-28, on a board that had collapsed: "thats all the tickets that it can make today? its a
friday and a full slate" ... "then the other 4 players should be singles".

The board that night had ONE anchor and nine gated players because the team-news gate was broken
(XIPARTIAL) and a name join was silently marking a starter as out of squad (UNMATCHED). Once
those were fixed the anchors came back. The four stranded players were a SYMPTOM. Shipping them
as singles papered over the bug, and then generalising it into a standing section on every board
resurrected something that lost 33 units the last time it ran.

WHAT IS KEPT

`anchorsOnly()` stays, untouched. It is a different thing and its own comment says so: when four
anchors will not fit, it ships THE ANCHORS as singles -- "the exact line every screamer would have
been built around anyway". Those are the top of the board, not the leftovers beneath it. That is
the honest answer to a thin slate.

WHAT THIS FIXES FOR FREE

test_redraft scenario 3 and the four test_stage2_page failures were all one thing: leftovers froze
and a man on a frozen single is correctly barred from being drafted as a partner, so the leftovers
ate the entire repair pool and a screamer with one dead leg could not be repaired. With the
section gone the pool is there again and the repair happens.

LEFTOVERANCHOR-2026-08-28 is left in place. It fixed a real confusion -- a frozen single-leg
builder claiming an anchor seat it does not occupy -- and that reasoning holds for any future
single-leg builder, whatever mints it.

TONIGHT'S BOARD IS NOT TOUCHED. The 2026-08-28 soccer slate is unsettled (`graded_nights` ends
08-27) and carries three of these singles, which were published and visible for hours. This
change stops the MINTING; it does not reach back and delete slips that shipped. Verified: the
committed board redrafts to the same six tickets under the patched engine. Whether those three
should be backed out of the ledger the way the MLB family nights were is the owner's call, not
a side effect of a code change.
"""
import sys

F = 'soccer_draft.js'
src = open(F, encoding='utf-8').read()

if 'LEFTOVERS-2026-08-28' not in src:
    sys.exit('ABORT: no LEFTOVERS block found -- nothing to back out')

# 1. the DEFAULTS entry
OLD_CFG = """    SINGLE_STAKE: 1.0,
    LEFTOVER_CAP: 8      // LEFTOVERS-2026-08-28: most gated-but-undrafted players shipped as singles"""
NEW_CFG = """    SINGLE_STAKE: 1.0"""

# 2. the function and its comment block
start = src.index('  /* LEFTOVERS-2026-08-28 -- ')
end_marker = """  function leftoverSingles(byStrength, used, cfg) {
    var out = [];
    for (var i = 0; i < byStrength.length && out.length < cfg.LEFTOVER_CAP; i++) {
      var p = byStrength[i];
      if (used[p.name]) continue;
      out.push({ kind: 'builder', legs: [p], risk: cfg.SINGLE_STAKE });
    }
    return out;
  }
"""
if end_marker not in src:
    sys.exit('ABORT: leftoverSingles() does not look as expected -- back out by hand')
end = src.index(end_marker) + len(end_marker)
REPLACEMENT = """  /* UNLEFTOVER-2026-08-28. leftoverSingles() lived here and is GONE, not disabled.
   * SCREAMERS-2026-08-26 retired the leftover section to match the MLB Dingers retirement
   * ("its just bleeding money" -- family went 11-80, -33.34u, -36.6% ROI, and its 12 graded
   * nights were backed out of season.json). LEFTOVERS-2026-08-28 was that section again in a
   * different coat: every gated player who made no slip, one unit each, capped at eight. On a
   * healthy board that is six extra singles a night at +200 to +350 -- the dross beneath the
   * draft, which is exactly what was retired. It escaped notice because it minted `builder`
   * rather than `family`, so every check enforcing the retirement looked past it.
   * The thin-slate answer is anchorsOnly() below: ship THE ANCHORS as singles. Not the leftovers.
   */
"""
src = src[:start] + REPLACEMENT + src[end:]
print('  removed leftoverSingles() and left a headstone')

# 3. the two call sites
OLD_SINGLES = """      var singles = anchorsOnly(byStrength, cfg, opts);
      var usedS = {}; singles.forEach(function (t) { usedS[t.legs[0].name] = true; });
      singles = singles.concat(leftoverSingles(byStrength, usedS, cfg));"""
NEW_SINGLES = """      var singles = anchorsOnly(byStrength, cfg, opts);"""

OLD_EXTRAS = """    var used = {};
    tickets.forEach(function (t) { t.legs.forEach(function (l) { used[l.name] = true; }); });
    builders.forEach(function (t) { used[t.legs[0].name] = true; });
    var extras = leftoverSingles(byStrength, used, cfg);

    return {
      tickets: tickets.concat(builders, extras),"""
NEW_EXTRAS = """    return {
      tickets: tickets.concat(builders),"""

for old, new, label in ((OLD_CFG, NEW_CFG, 'DEFAULTS: drop LEFTOVER_CAP'),
                        (OLD_SINGLES, NEW_SINGLES, 'singles-only path: no leftover top-up'),
                        (OLD_EXTRAS, NEW_EXTRAS, 'main path: no leftover section')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, back out by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

# 4. LEFTOVERANCHOR-2026-08-28's comments name LEFTOVER_CAP and "a LEFTOVERS single". That
#    reasoning still holds for any single-leg builder, but it must not cite a constant that no
#    longer exists -- a comment pointing at a deleted symbol is how the next reader loses time.
OLD_A = """       board is singles-only. Anything else is a LEFTOVERS-2026-08-28 single, which anchors
       nothing and must not spend a seat against ANCH. */"""
NEW_A = """       board is singles-only. Any other single-leg builder anchors nothing and must not spend
       a seat against ANCH. (Written for LEFTOVERS-2026-08-28, backed out by
       UNLEFTOVER-2026-08-28; kept because it is true of any such builder, whatever mints it.) */"""

OLD_B = """        /* LEFTOVERANCHOR-2026-08-28: only if he anchors something. LEFTOVER_CAP is 8 and ANCH
           is 4, so eight frozen leftovers used to claim eight seats against a budget of four and
           zero it out -- no repair, no mint, for the rest of the night. A leftover is spent
           (not re-mintable, not draftable as a partner) without spending a seat. */"""
NEW_B = """        /* LEFTOVERANCHOR-2026-08-28: only if he anchors something. Under the (since backed
           out) leftover section, eight frozen singles could claim eight seats against an ANCH
           budget of four and zero it out -- no repair, no mint, for the rest of the night. Such
           a builder is spent (not re-mintable, not draftable as a partner) without taking a
           seat. */"""

for old, new, label in ((OLD_A, NEW_A, 'LEFTOVERANCHOR comment A'),
                        (OLD_B, NEW_B, 'LEFTOVERANCHOR comment B')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n}")
    src = src.replace(old, new, 1)
    print(f"  reworded {label}")

# the guard: no LIVE reference may survive. Prose mentions in the headstone and in
# LEFTOVERANCHOR's comments are deliberate history and are fine; a CALL or a CONFIG READ is not.
for bad in ('leftoverSingles(byStrength', 'cfg.LEFTOVER_CAP', 'LEFTOVER_CAP:'):
    if bad in src:
        sys.exit(f'ABORT: live reference `{bad}` still in {F} -- back out by hand')

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
