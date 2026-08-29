"""
STAGE2KO-2026-08-29 -- test_stage2_page.js forked a page with NO KICKOFFS and then asserted
                       pre-kickoff behaviour. It could never have passed.

    node test_stage2_page.js
      --- 2. team news lands an hour before kickoff ---
      FAIL  the board moved off the baked draft
      FAIL  the dead leg was replaced, not dropped
      FAIL  the dead leg is on no slip at all
      FAIL  every remaining leg is a confirmed starter

Four failures, one cause, and it is not in the drafter. Dumping `D.meta` out of the running page
at each scenario:

    scenario 1   meta keys = date, finals, gs      <- no `ko`
    scenario 2   meta keys = date, finals, gs      <- no `ko`
    scenario 3   meta keys = date, finals, gs      <- no `ko`

`soccerRedraft()`'s very first guard is

    if(!D.meta.ko||!Object.keys(D.meta.ko).length) return;   /* board baked before STAGE2 */

so the live loop returned before it ever reached the drafter, on every pass, in every scenario.
`SoccerDraft.redraft()` carries the same guard for itself ("no kickoffs baked (meta.ko)"). The
board on screen therefore could not move, which is precisely what the four assertions were
complaining about.

WHY THE FIXTURE HAS NO KICKOFFS, AND WHY THAT IS CORRECT

TESTPIN-2026-08-28 repointed this test at `fixtures/2026-08-26/`, the committed artifact of that
night. Boards baked before STAGE2-2026-08-27 carry no `meta.ko` -- test_redraft.js says so in its
own header and works around it in three lines:

    const KO = 19 * 60;                       // 19:00Z, the real kickoff for all five
    D.meta.ko = {};
    Object.keys(D.players).forEach(n => { D.meta.ko[String(D.players[n].game)] = KO; });

test_stage2_page.js already declares the same `const KO = 19 * 60` and builds all three of its
scenario clocks from it -- 18:00Z is "an hour before kickoff", 19:30Z is "thirty minutes after".
It just never wrote the value into the payload it forked the page from. So the test has always
been asking the page to repair a board an hour before a kickoff the page did not know about.

THE FIX -- synthesise the kickoffs into the FORKED PAYLOAD, the same way, for the same reason

The pinned fixture on disk is NOT modified: it is the committed artifact and stays immutable, the
whole point of TESTPIN. The kickoffs are written into a temp copy which is what gets forked, and
the test prints the fact so a reader is never guessing which board is under test.

⚠️ THIS IS NOT AN ADJUSTMENT TO MAKE FAILING ASSERTIONS PASS. Every assertion is left exactly as
written. The change is to the INPUT, and it makes the input match what the assertions have always
described in words: a board whose matches kick off at 19:00Z. A test that cannot reach the code it
names is not a failing test, it is a test that has not run -- the same defect TESTPIN found when
this file was dying on ENOENT before a single assertion executed.

WHAT IT REVEALS. With kickoffs present the drafter is finally reachable, and what it then does is
a separate question answered by OUTSQUAD-2026-08-29 in soccer_draft.js.
"""
import sys

F = 'test_stage2_page.js'
src = open(F, encoding='utf-8').read()

OLD = """const D0 = JSON.parse(fs.readFileSync(PAYLOAD, 'utf8'));
const KO = 19 * 60;                                   // every match kicks off 19:00Z
const DATE = D0.meta.date;"""

NEW = """const D0 = JSON.parse(fs.readFileSync(PAYLOAD, 'utf8'));
const KO = 19 * 60;                                   // every match kicks off 19:00Z
const DATE = D0.meta.date;

/* STAGE2KO-2026-08-29 -- THE FORKED PAGE HAD NO KICKOFFS, so the live loop never reached the
 * drafter and scenario 2 could not possibly pass. Dumping D.meta out of the running page gave
 * `date, finals, gs` and no `ko`, and soccerRedraft()'s first guard is
 *     if(!D.meta.ko||!Object.keys(D.meta.ko).length) return;   // board baked before STAGE2
 * The pinned fixture is 2026-08-26 and boards baked before STAGE2-2026-08-27 carry no meta.ko --
 * test_redraft.js documents exactly this and synthesises them in three lines. This file already
 * declares KO above and builds all three scenario clocks from it; it simply never wrote the value
 * into the payload it forks from, so it has been asking the page to repair a board an hour before
 * a kickoff the page did not know about.
 * The FIXTURE ON DISK IS NOT TOUCHED -- it is the committed artifact and immutable by design
 * (TESTPIN-2026-08-28). The kickoffs go into a temp copy, and that copy is what is forked. */
if (!D0.meta.ko || !Object.keys(D0.meta.ko).length) {
  D0.meta.ko = {};
  Object.keys(D0.players).forEach(n => { D0.meta.ko[String(D0.players[n].game)] = KO; });
  PAYLOAD = path.join(require('os').tmpdir(), 'stage2_payload_ko.json');
  fs.writeFileSync(PAYLOAD, JSON.stringify(D0));
  console.log(`  (kickoffs synthesised at 19:00Z for ${Object.keys(D0.meta.ko).length} matches -- `
    + `the pinned 2026-08-26 board predates STAGE2 and carries none)`);
  execFileSync('python3', [path.join(__dirname, 'soccer_fork.py'), path.join(__dirname, '..', 'index.html'),
                           PAYLOAD, FILE], { cwd: __dirname, stdio: 'inherit' });
}"""

n = src.count(OLD)
if n != 1:
    sys.exit(f"ABORT: expected exactly 1 payload-read block in {F}, found {n} -- the source moved, patch by hand")
src = src.replace(OLD, NEW, 1)
print("  patched: synthesise kickoffs into the forked payload")

# `PAYLOAD` and `FILE` are declared with `let`/`const` above; the block above REASSIGNS PAYLOAD, so
# it must not be a const. Check rather than assume -- a const reassignment is a TypeError at load
# and would put this file straight back to "dies before any assertion runs".
import re
m = re.search(r'^\s*(let|const|var)\s+FILE\s*=\s*process\.argv\[2\],\s*PAYLOAD\s*=\s*process\.argv\[3\];',
              src, re.M)
if not m:
    sys.exit("ABORT: could not find the FILE/PAYLOAD declaration to check its binding")
if m.group(1) == 'const':
    sys.exit("ABORT: PAYLOAD is declared const and this patch reassigns it -- change the "
             "declaration to let, by hand, deliberately")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
