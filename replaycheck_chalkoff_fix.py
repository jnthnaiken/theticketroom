"""
REPLAYCHALK-2026-08-28 -- teach replay_check.js's SEALED assertion about CHALKOFF.

THE PROBLEM

Assertion 1 says, in its own header: "a ticket that has locked never changes again ... and only
ever leaves the board when one of its own players is SCRATCHED. Any other disappearance is a
violation."

That was true when it was written. CHALKOFF-2026-08-26 added a SECOND lawful way for a locked slip
to leave -- owner: "yea no if he's in the top 4 ban he needs to be taken off", "i dont care if
they are locked" -- and the assertion was never told. So every correct chalk eviction of a locked
slip is reported as a violation:

    2026-08-26  19:34Z  SEALED TICKET VANISHED: "Full Fathom" -- every leg still alive

Hunter Goodman became the fourth shortest price when Buxton was scratched; his locked builder was
correctly removed; the harness called it a bug. It has failed on that for two days.

WHY THAT MATTERS MORE THAN ONE LINE OF OUTPUT

A suite that is red for a known-benign reason stops being read, and then it stops working. The
chalk ban leaked a top-4 price onto the board on eight of the last nine slates (CHALKPLACED) and
nobody noticed, while this harness printed FAIL every night for something harmless. Green has to
mean something.

HOW, AND THE THING NOT TO DO

The tempting fix is to have the harness compute the ban itself -- the four shortest prices, easy.
That is the assemble_tickets.py mistake in miniature: two implementations of one rule, drifting
apart, disagreeing about the same board. Most of 2026-08-28 was that class of bug (soccer_live.js
vs soccer_teamnews.py normalisation; _placedLeg meaning one thing for a seat you get and another
for a seat you are barred from). Writing another one INSIDE THE TEST would be the worst place for
it: a harness that disagrees with the engine reports fiction in both directions.

So the engine publishes `D.meta.chalk` (CHALKOBS-2026-08-28, write-only) and the harness reads it.
One implementation, one source of truth.

WHAT THIS DOES AND DOES NOT RELAX

A vanished locked slip is now lawful for exactly two reasons, both evidenced from the build that
removed it:
    - a leg is scratched  (p.out / p.void / gone from the board)   -- as before
    - a leg is in that build's published chalk ban                 -- new

Everything else is still a violation. A locked slip that CHANGES is still a violation -- CHALKOFF
removes, it never rewrites. And if `D.meta.chalk` is absent (an older engine, or a board built
before CHALKOBS) the set is empty and the assertion behaves EXACTLY as it does today: the failure
mode of this patch is stricter, never looser, which is the only safe direction for a test.

Both reasons are accounted for in the removals report at the end of the run, so a lawful removal
is still visible rather than silently swallowed.
"""
import sys

F = 'replay_check.js'
src = open(F, encoding='utf-8').read()

OLD_DOC = (" *   1. SEALED   a ticket that has locked never changes again -- not its legs, not its\n"
           " *               prices -- and only ever leaves the board when one of its own players is\n"
           " *               scratched. Any other disappearance is a violation.\n")

NEW_DOC = (" *   1. SEALED   a ticket that has locked never changes again -- not its legs, not its\n"
           " *               prices -- and only ever leaves the board for one of TWO lawful reasons:\n"
           " *               one of its own players is scratched, or one of them is in that build's\n"
           " *               chalk ban (CHALKOFF-2026-08-26: \"if he's in the top 4 ban he needs to be\n"
           " *               taken off ... i dont care if they are locked\"). Any other disappearance\n"
           " *               is a violation, and a locked slip that CHANGES always is -- CHALKOFF\n"
           " *               removes, it never rewrites.\n"
           " *               REPLAYCHALK-2026-08-28: the ban is READ FROM THE ENGINE (D.meta.chalk,\n"
           " *               published by CHALKOBS-2026-08-28), never recomputed here. A harness that\n"
           " *               reimplements the rule it is testing is the assemble_tickets.py mistake in\n"
           " *               the worst possible place. If the field is absent the set is empty and\n"
           " *               this assertion behaves exactly as it did before -- stricter, never\n"
           " *               looser, which is the only safe direction for a test to fail in.\n")

OLD_CHK = """        const scratched = sealed[nm].legs.filter(n => {
          const p = D.players[n];
          return !p || p.out || p.void;
        });
        if (scratched.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- scratched: ${scratched.join(', ')}`);
        } else {"""

NEW_CHK = """        const scratched = sealed[nm].legs.filter(n => {
          const p = D.players[n];
          return !p || p.out || p.void;
        });
        /* REPLAYCHALK-2026-08-28: the OTHER lawful removal. Read off the build that did it. */
        const bannedNow = new Set(((D.meta || {}).chalk) || []);
        const banned = sealed[nm].legs.filter(n => bannedNow.has(n));
        if (scratched.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- scratched: ${scratched.join(', ')}`);
        } else if (banned.length) {
          removals.push(`${s.hh}:${s.mm}Z  "${nm}" removed -- now chalk (CHALKOFF): ${banned.join(', ')}`);
        } else {"""

OLD_SUM = "    console.log(`  -- ${removals.length} scratch-driven removal(s), all accounted for:`);"
NEW_SUM = "    console.log(`  -- ${removals.length} lawful removal(s) (scratch or chalk ban), all accounted for:`);"

for old, new, label in ((OLD_DOC, NEW_DOC, 'assertion 1 doc'),
                        (OLD_CHK, NEW_CHK, 'SEALED removal check'),
                        (OLD_SUM, NEW_SUM, 'removals summary line')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
