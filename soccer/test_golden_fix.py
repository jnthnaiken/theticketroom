"""
TESTPIN-2026-08-28 (part 2) -- test_draft_golden.js, same fixture defect, plus an obsolete premise.

THE FIXTURE DEFECT, identical to test_redraft.js

    const J = n => JSON.parse(fs.readFileSync(path.join(HERE, n), 'utf8'));
    const scored = J('scored.json'); const tn = J('teamnews.json'); const want = J('tickets.json');

All three live in the soccer root and all three are rewritten by every build. A golden master
whose GOLDEN is overwritten several times an hour is not a golden master. Repointed at
fixtures/2026-08-26/, committed from dea662c1 and immutable.

THE OBSOLETE PREMISE

The header claims: "soccer_draft.js drafts the SAME board soccer_mock.py drafted on 2026-08-25 ...
If the two ever disagree the soccer room has two drafters again."

There is no longer a second drafter to disagree with. soccer_mock.py's own comment records the
retirement -- "`draft()`, `span_ok()` and the THINSLATE loop above are gone ... scoring is not
drafting, and scored.json is the interface" -- and it now shells out to soccer_draft_cli.js and
reads tickets.json back. The two-drafter risk this file was written to police no longer exists in
soccer. Left unchanged, the header sends the next reader looking for a Python drafter that is not
there.

What the file is STILL worth: a regression pin. Given these exact inputs, the drafter produces
exactly this board. That is worth keeping and is what it becomes.

WHAT THE RUN ACTUALLY SHOWS

Against the pinned fixture the three shipped slips reproduce EXACTLY -- same moons, same legs,
same order, same odds, same matches, same stakes. The only difference is one extra ticket:

    got  [... ,[["Zlatko Tripic",210]]]

a leftover single, which is LEFTOVERS-2026-08-28 doing exactly what it was added to do. So the
golden did not rot; the drafter gained a deliberate feature after the golden was cut.

HOW THAT IS HANDLED, WITHOUT MAKING THE TEST TAUTOLOGICAL

The dishonest fix is to re-cut the golden from today's output, which asserts nothing on the day it
is written. Instead the comparison is SPLIT along the line the feature actually drew:

  - MOONS AND THEIR BUILDERS are compared against the shipped golden, unchanged and strict. This
    is the historical claim and it is not self-fulfilling: it says the drafter still reproduces a
    board a human shipped on a night nobody is going to re-cut.

  - LEFTOVER SINGLES are asserted STRUCTURALLY, not by value: each is a one-leg `builder` at
    SINGLE_STAKE, its player is in the gated pool, appears on no other slip, and the count is
    within LEFTOVER_CAP. That is a real constraint the code can fail, and it does not encode
    today's particular output as truth.

  - 'builders == moon anchors, one each' was true before LEFTOVERS and is now wrong in the same
    way `_placedLeg` was wrong: `builder` came to mean two things. Restated precisely -- every
    moon anchor has exactly one builder, and every OTHER builder is a leftover single.
"""
import sys

F = 'test_draft_golden.js'
src = open(F, encoding='utf-8').read()

OLD_HDR = """/* test_draft_golden.js -- GOLDEN MASTER for soccer_draft.js.
 *
 * The claim this file has to earn: soccer_draft.js drafts the SAME board soccer_mock.py drafted
 * on 2026-08-25, from the same inputs. Not "a similar board" -- the same slips, same legs, same
 * order, same stakes. If the two ever disagree the soccer room has two drafters again, which is
 * the assemble_tickets.py failure the codebase already paid for once.
 *
 * Inputs are the COMMITTED artifacts of that night, not re-derived:
 *     scored.json    every priced player with TOTAL / gate_z / kickoff  (soccer_mock.py output)
 *     teamnews.json  the XI that night                                  (soccer_teamnews.py output)
 *     tickets.json   what the board actually shipped                    <- the assertion
 */"""

NEW_HDR = """/* test_draft_golden.js -- GOLDEN MASTER for soccer_draft.js.
 *
 * The claim: given the exact inputs of 2026-08-26, soccer_draft.js still produces the board that
 * actually shipped that night. Not "a similar board" -- the same slips, same legs, same order,
 * same stakes.
 *
 * TESTPIN-2026-08-28. Two things were wrong with this file.
 *
 * 1. THE INPUTS WERE NOT PINNED. It read scored.json / teamnews.json / tickets.json from the
 *    soccer root -- all three rewritten by every build, several times an hour. A golden master
 *    whose golden is overwritten is not a golden master. They now come from
 *    fixtures/2026-08-26/, committed from dea662c1 and immutable. (The old header said
 *    2026-08-25; the board's own meta.date is 2026-08-26.)
 *
 * 2. THE PREMISE WAS OBSOLETE. It said this file exists so soccer_draft.js and soccer_mock.py
 *    cannot drift into "two drafters again". soccer_mock.py no longer drafts -- its own comment
 *    records it ("`draft()`, `span_ok()` and the THINSLATE loop above are gone ... scoring is
 *    not drafting, and scored.json is the interface") and it now shells out to
 *    soccer_draft_cli.js and reads tickets.json back. There is no second drafter to disagree
 *    with. What this file is still worth is a REGRESSION PIN, and that is what it now is.
 *
 * ⚠️ THE COMPARISON IS SPLIT ON PURPOSE. LEFTOVERS-2026-08-28 added leftover singles after this
 * golden was cut, so the drafter legitimately emits one more ticket than shipped that night. The
 * dishonest fix is to re-cut the golden from today's output, which asserts nothing on the day it
 * is written. Instead: MOONS AND THEIR BUILDERS are still compared against the shipped golden,
 * strictly -- a historical claim nobody is going to re-cut -- and LEFTOVER SINGLES are asserted
 * STRUCTURALLY, by the rules they must obey rather than by the values they happen to have today.
 *
 * Inputs are the COMMITTED artifacts of that night, not re-derived:
 *     scored.json    every priced player with TOTAL / gate_z / kickoff  (soccer_mock.py output)
 *     teamnews.json  the XI that night                                  (soccer_teamnews.py output)
 *     tickets.json   what the board actually shipped                    <- the assertion
 */"""

OLD_CMP = """eq('ticket count', got.tickets.length, want.length);
eq('kinds', got.tickets.map(t => t.kind), want.map(t => t.kind));
eq('stakes', got.tickets.map(t => t.risk), want.map(t => t.risk));
eq('legs (name+odds, in order)',
  got.tickets.map(t => t.legs.map(l => [l.name, l.odds])),
  want.map(t => t.legs.map(l => [l.name, l.odds])));
eq('leg matches', got.tickets.map(t => t.legs.map(l => l.match)), want.map(t => t.legs.map(l => l.match)));"""

NEW_CMP = """/* THE HISTORICAL CLAIM -- moons and the builders that back them, against what shipped.
   Leftover singles (LEFTOVERS-2026-08-28) postdate the golden and are excluded here; they are
   asserted structurally below. `core` is every slip whose player anchors a moon, which is
   exactly the set that existed when the golden was cut. */
const wantAnchors = SD.nameSet(want.filter(t => t.kind === 'moon').map(t => t.legs[0].name));
const core = got.tickets.filter(t => t.kind === 'moon' || wantAnchors[t.legs[0].name]);
const leftovers = got.tickets.filter(t => core.indexOf(t) < 0);

eq('ticket count (moons + anchor builders)', core.length, want.length);
eq('kinds', core.map(t => t.kind), want.map(t => t.kind));
eq('stakes', core.map(t => t.risk), want.map(t => t.risk));
eq('legs (name+odds, in order)',
  core.map(t => t.legs.map(l => [l.name, l.odds])),
  want.map(t => t.legs.map(l => [l.name, l.odds])));
eq('leg matches', core.map(t => t.legs.map(l => l.match)), want.map(t => t.legs.map(l => l.match)));"""

OLD_INV = """inv('builders == moon anchors, one each',
  JSON.stringify(builders.map(t => t.legs[0].name).sort()) === JSON.stringify([...anchorNames].sort()));"""

NEW_INV = """/* TESTPIN-2026-08-28: was 'builders == moon anchors, one each'. True until LEFTOVERS-2026-08-28
   made `builder` mean two things -- an anchor's builder, and a gated player shipped as a straight
   single. Restated so it still pins the first without being wrong about the second. */
inv('every moon anchor has exactly one builder',
  anchorNames.every(n => builders.filter(t => t.legs[0].name === n).length === 1));
inv('every other builder is a leftover single',
  builders.filter(t => anchorNames.indexOf(t.legs[0].name) < 0).length === leftovers.length);

/* LEFTOVER SINGLES -- asserted by the rules they must obey, never by today's values. */
inv('leftovers are one-leg builders at SINGLE_STAKE',
  leftovers.every(t => t.kind === 'builder' && t.legs.length === 1 && t.risk === SD.DEFAULTS.SINGLE_STAKE));
inv('leftovers come from the gated pool',
  leftovers.every(t => got.pool.some(p => p.name === t.legs[0].name)));
inv('a leftover is on no other slip', (() => {
  const elsewhere = {};
  core.forEach(t => t.legs.forEach(l => { elsewhere[l.name] = true; }));
  return leftovers.every(t => !elsewhere[t.legs[0].name]);
})());
inv('no leftover is drafted twice',
  new Set(leftovers.map(t => t.legs[0].name)).size === leftovers.length);
inv('leftovers respect LEFTOVER_CAP', leftovers.length <= SD.DEFAULTS.LEFTOVER_CAP);"""

OLD_END = "console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- soccer_draft.js reproduces the 2026-08-25 board');"
NEW_END = ("console.log(fail ? `${fail} FAILURE(S)`\n"
           "  : `ALL GREEN -- soccer_draft.js reproduces the 2026-08-26 board`\n"
           "    + ` (${core.length} shipped slips` + (leftovers.length ? `, plus ${leftovers.length} leftover single(s)` : '') + `)`);")

for old, new, label in ((OLD_HDR, NEW_HDR, 'header: pinned fixture + corrected premise'),
                        (OLD_CMP, NEW_CMP, 'split the golden comparison'),
                        (OLD_INV, NEW_INV, 'restate the builder invariant + leftover rules'),
                        (OLD_END, NEW_END, 'summary line')):
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
