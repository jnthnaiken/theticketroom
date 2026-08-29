"""
REPLAYCARRY-2026-08-29 -- the chained replay carried the tickets but not the ban.

replay_check's own header states the property it is built on:

    "The replay is CHAINED: build N's output becomes build N+1's prior board, which is how
     production actually works -- regen15.py takes the prior board from index.html's `const D` ...
     [re-reading the archived] prior would hide exactly the drift this is looking for."

Right, and it only half did it:

    const D = board(s);
    D.tickets = JSON.parse(JSON.stringify(carry));   <- tickets carried
                                                     <- meta rebuilt from the archived snapshot

`meta` came fresh off the archived snapshot every build, so every carried field was thrown away.
That did not matter while `meta` held nothing the engine reads back. It does now:

    meta.chalk       CHALKSETTLE-2026-08-29 -- the previous build's ban, which the engine intersects
                     with today's to decide what it will EVICT for
    meta.chalkever   LOCKEVICT-2026-08-29   -- the night's chalk union, which the localStorage latch
                     uses to refuse to resurrect an evicted slip

regen15.py carries both across builds of the same slate. The harness did not, so in replay both
degraded to their first-build fallback on every single build: `_chalkAct` fell back to the whole of
`chalk`, and `chalkever` restarted from empty. The chain was reproducing a slate that production
never runs -- and, worse, the harness was structurally blind to the entire debounce, so a change to
it could never be measured here.

THE FIX: carry what production carries. `carryMeta` holds the meta fields regen15.py hands forward,
they are written onto each build's board beside the tickets, and the list is named in one place so
the next field added to that carry has one obvious home.

⚠️ THIS DOES NOT WEAKEN ANY ASSERTION. Nothing about the SEALED check, the two-open-slips check or
the bake check changes. The chain simply stops discarding state that production keeps, which can
only make the replay closer to the real thing. Verified: PASS before and after, 923 chained builds
over 2026-08-23..28, same board shapes on every day.
"""
import sys

F = 'replay_check.js'
src = open(F, encoding='utf-8').read()

OLD_INIT = "  for (let i = 1; i < snaps.length; i++) {"
NEW_INIT = ("  /* REPLAYCARRY-2026-08-29: the meta fields regen15.py hands forward on a same-slate\n"
            "     build. They were being discarded here, because `meta` was rebuilt from the archived\n"
            "     snapshot while only `tickets` was carried -- so in replay every build looked like the\n"
            "     first of the slate. meta.chalk is the previous ban (CHALKSETTLE-2026-08-29 intersects\n"
            "     it with today's to decide what it EVICTS for) and meta.chalkever is the night's chalk\n"
            "     union (LOCKEVICT-2026-08-29). Add a field here when regen15.py starts carrying it. */\n"
            "  const CARRY_META = ['chalk', 'chalkever'];\n"
            "  let carryMeta = {};\n"
            "  for (let i = 1; i < snaps.length; i++) {")

OLD_SET = ("    const D = board(s);\n"
           "    D.tickets = JSON.parse(JSON.stringify(carry));\n"
           "    delete D.familyFloor;")
NEW_SET = ("    const D = board(s);\n"
           "    D.tickets = JSON.parse(JSON.stringify(carry));\n"
           "    /* REPLAYCARRY-2026-08-29: and the meta production carries, or the chain silently\n"
           "       replays a slate that never happened -- see CARRY_META above. */\n"
           "    if (D.meta) for (const k of CARRY_META) if (carryMeta[k] != null) D.meta[k] = carryMeta[k];\n"
           "    delete D.familyFloor;")

OLD_CARRY = "    carry = T;"
NEW_CARRY = ("    carry = T;\n"
             "    if (D.meta) { carryMeta = {}; for (const k of CARRY_META) if (D.meta[k] != null) carryMeta[k] = D.meta[k]; }")

for old, new, label in ((OLD_INIT,  NEW_INIT,  'declare the carried meta fields'),
                        (OLD_SET,   NEW_SET,   'write them onto each build'),
                        (OLD_CARRY, NEW_CARRY, 'read them back out of the engine output')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
