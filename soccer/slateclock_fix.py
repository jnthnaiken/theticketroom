"""
SLATECLOCK-2026-08-31 -- `now` and `kickoff` were on different clocks.

    owner, 2026-08-31: "go"

## THE MISMATCH

`kickoff` in fixtures.json is MINUTES PAST MIDNIGHT UTC OF THE SLATE DATE. soccer_payload depends
on exactly that:

    def et_dt(mins):
        return (datetime(slate.year, slate.month, slate.day, tzinfo=timezone.utc)
                + timedelta(minutes=int(mins))).astimezone(ET)

so a value over 1440 is legal and means "the following day". MLS kicks off at 00:30Z, which is
1470.

`now` was WALL-CLOCK UTC, 0..1439, computed in the workflow:

    NOW=$(( 10#$(date -u +%H) * 60 + 10#$(date -u +%M) ))

MINTGUARD compares them directly -- soccer_draft.js, placeable():

    if (ko == null || now >= ko) return false;   // no slip is created past its own kickoff

Two bases, one comparison.

## MEASURED, ISOLATED (every other match forced underway, so only match 5 is draftable)

    A) EUROPEAN ko 1170 (19:30Z), now 1200 (20:00Z) -- underway, should block:
         minted 0 slips                                              MINTGUARD works
    B) MLS ko 1470 (00:30Z next day), now 60 (01:00Z) -- underway 30 min:
         minted 1 slip -> lunch: Raphinha                            DEFEATED
    C) MLS ko 1470, now 1400 (23:20Z) -- 70 minutes BEFORE kickoff:
         minted 1 slip -> lunch: Raphinha                            correct

B and C are identical, and that is the proof: past 1440 `now` can never reach the kickoff, so the
engine cannot tell BEFORE a match from DURING it, at any hour of any day.

## IT WAS ALREADY A HOLE ON THE EUROPEAN BOARD

Same arithmetic reached the other way. On the slate's own day `now < ko` correctly means "not
yet"; after midnight UTC the clock wraps and the slate does not, so a finished match reads as
unstarted. Measured on the published 2026-08-31 board at now=15 (00:15Z, same slate, every match
long over): SIX new slips minted into finished matches, three of them fresh screamers.

It had not bitten only because soccer-settle.yml grades the night and the build skips a slate in
`graded_nights` -- 2026-08-30 settled at 21:51Z, covering the window before the 08-31 slate landed
at 10:05Z. A real protection, but an incidental one: a late or failed settle and the board
redrafts a finished card. The same shape as RCTRAP and GATEOUT, and the same lesson written on
both -- a guard that only runs when something is wrong is a guard nobody has tested.

## THE FIX, AND WHY IT IS AT THE CALLER

`soccer_draft.js` takes `nowUTCmin` as an opaque number and is already SLATE-RELATIVE BY CONTRACT:
every test passes it that way (`nowUTCmin: KO - 120`). The drafter is not wrong and is not
touched. What was wrong is the one caller that manufactured a wall-clock number and handed it
over.

So `soccer_rebuild_cli.js` computes it, from the prior board's own `meta.date`:

    now = wallClockUTCMinutes + 1440 * (todayUTC - slateDate)

- On the slate's own day the offset is 0 and every existing European build is BIT-IDENTICAL.
- After midnight the offset is 1: now = 1455 against ko 1170 -> correctly blocked.
- For MLS: ko 1470 against now 1500 at 01:00Z -> blocked; against 1400 at 23:20Z -> allowed.

⚠️ `--now` KEEPS ITS MEANING AND IS TAKEN VERBATIM. It is slate-relative, which is what every
test and every manual invocation already assumes, so nothing that passes it changes behaviour.
The workflow stops passing it and lets the CLI read the clock instead. Both halves must ship
together: the CLI alone changes nothing while the workflow still passes a wall-clock `--now`.

⚠️ CONFLOCK reads the same `now` (`ticketIsLocked`), so this moves more than MINTGUARD. That is
the point -- a slip whose legs are all confirmed and whose match is over should be frozen, and
under the old clock, after midnight, it was not.
"""
import sys

# ---------------------------------------------------------------------------------------------
# 1. soccer_rebuild_cli.js -- derive the slate-relative clock.
F = 'soccer_rebuild_cli.js'
src = open(F, encoding='utf-8').read()
if 'SLATECLOCK-2026-08-31' in src:
    sys.exit('ABORT: already applied')

OLD_USAGE = """ *   node soccer_rebuild_cli.js <prior board.json> <scored.json> <out tickets.json> \\
 *        [--teamnews teamnews.json] [--now <UTC minutes past midnight>]"""
NEW_USAGE = """ *   node soccer_rebuild_cli.js <prior board.json> <scored.json> <out tickets.json> \\
 *        [--teamnews teamnews.json] [--now <minutes past midnight UTC OF THE SLATE DATE>]
 *
 * ⚠️ SLATECLOCK-2026-08-31 -- `--now` IS SLATE-RELATIVE, NOT WALL-CLOCK, and may exceed 1440.
 * It is on the same basis as `kickoff` in fixtures.json, which soccer_payload's et_dt() defines
 * as minutes past midnight UTC OF THE SLATE DATE. MLS kicks off at 00:30Z = 1470. Omit the flag
 * and this file computes it from the real clock and the prior board's own meta.date, which is
 * what the workflow now does; pass it only from a test or a hand run, where it has always meant
 * this."""
if src.count(OLD_USAGE) != 1:
    sys.exit('ABORT: usage block moved')
src = src.replace(OLD_USAGE, NEW_USAGE, 1)

OLD_NOW = """const now = flag('--now') != null ? Number(flag('--now')) : null;
if (now == null || !isFinite(now)) { console.error('!! --now is required (UTC minutes past midnight)'); process.exit(2); }"""

NEW_NOW = """/* 🚨 SLATECLOCK-2026-08-31 -- THE CLOCK MUST BE ON THE SLATE'S BASIS, NOT THE WALL'S.
   `kickoff` is minutes past midnight UTC OF THE SLATE DATE (soccer_payload.et_dt builds it that
   way), so it legally exceeds 1440 -- MLS kicks off 00:30Z = 1470. `now` used to be wall-clock
   UTC 0..1439, straight out of the workflow's `date -u`, and MINTGUARD compares the two
   directly (`if (ko == null || now >= ko) return false`).
   Measured: with ko 1470, a slip minted identically at now=1400 (70 min BEFORE kickoff) and at
   now=60 (30 min INTO the match) -- past 1440 the guard cannot tell one from the other, ever.
   The same arithmetic the other way is a hole that was already live on the European board: after
   midnight the clock wraps and the slate does not, so at now=15 the 2026-08-31 board minted SIX
   slips into matches that had finished hours earlier. Only the graded-night skip was covering
   it, which depends on settling beating the first post-midnight build.
   soccer_draft.js is fine and is not touched -- it takes `nowUTCmin` opaquely and every test
   already passes it slate-relative. The bug was this caller manufacturing a wall-clock number. */
function slateRelativeNow(slateDate) {
  var d = new Date();
  var wall = d.getUTCHours() * 60 + d.getUTCMinutes();
  var m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(String(slateDate || ''));
  if (!m) return wall;                       /* no usable slate date -> old behaviour, loudly */
  var slate = Date.UTC(+m[1], +m[2] - 1, +m[3]);
  var today = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  var offDays = Math.round((today - slate) / 86400000);
  return wall + 1440 * offDays;
}
var now;
if (flag('--now') != null) {
  /* taken VERBATIM: `--now` has always meant slate-relative minutes and every test passes it
     that way (nowUTCmin: KO - 120). Do not "correct" it here or they all shift. */
  now = Number(flag('--now'));
  if (!isFinite(now)) { console.error('!! --now must be a number (minutes past slate midnight UTC)'); process.exit(2); }
} else {
  if (!D.meta || !D.meta.date) {
    console.error('!! no --now and the prior board carries no meta.date -- cannot place the clock');
    process.exit(2);
  }
  now = slateRelativeNow(D.meta.date);
  var _off = Math.round((now - (new Date().getUTCHours() * 60 + new Date().getUTCMinutes())) / 1440);
  console.log(`  clock: slate ${D.meta.date}, now ${now} min past slate midnight UTC`
              + (_off ? `  (+${_off}d past the slate date)` : ''));
}"""
if src.count(OLD_NOW) != 1:
    sys.exit('ABORT: the --now block does not look as expected')
src = src.replace(OLD_NOW, NEW_NOW, 1)
open(F, 'w', encoding='utf-8').write(src)
print(f'  patched {F}')

# ---------------------------------------------------------------------------------------------
# 2. The workflow -- stop manufacturing a wall-clock `--now`.
W = '../.github/workflows/soccer-build.yml'
wsrc = open(W, encoding='utf-8').read()

OLD_WF = """            NOW=$(( 10#$(date -u +%H) * 60 + 10#$(date -u +%M) ))
            set +e
            node soccer_rebuild_cli.js prior.json scored.json tickets.json \\
                 $([ -f teamnews.json ] && echo "--teamnews teamnews.json") --now $NOW"""
NEW_WF = """            # 🚨 SLATECLOCK-2026-08-31 -- `--now` IS GONE, DELIBERATELY. This computed wall-clock
            # UTC minutes (0..1439) and handed them to a comparison against `kickoff`, which is
            # minutes past midnight UTC OF THE SLATE DATE and legally exceeds 1440 (MLS kicks off
            # 00:30Z = 1470). Two bases, one comparison, so MINTGUARD could not tell "before the
            # match" from "during it" for any late kickoff -- and after midnight it read every
            # FINISHED match on the current slate as unstarted, which measured as six new slips
            # minted into completed games on the 2026-08-31 board. soccer_rebuild_cli.js now
            # derives the clock from the prior board's own meta.date. Do not reintroduce this
            # line; if you need to pin the clock, pass a SLATE-RELATIVE --now.
            # (The OCTAL-2026-08-28 note below is kept: it is why `10#` was here at all.)
            set +e
            node soccer_rebuild_cli.js prior.json scored.json tickets.json \\
                 $([ -f teamnews.json ] && echo "--teamnews teamnews.json")"""
if wsrc.count(OLD_WF) != 1:
    sys.exit(f'ABORT: the rebuild invocation in {W} does not look as expected -- found '
             f'{wsrc.count(OLD_WF)} matches')
wsrc = wsrc.replace(OLD_WF, NEW_WF, 1)
open(W, 'w', encoding='utf-8').write(wsrc)
print(f'  patched {W}')
print('slateclock_fix: done')
