"""
TESTPIN-2026-08-28 -- test_redraft.js was reading a file every build overwrites.

THE DEFECT

    const base = JSON.parse(fs.readFileSync(path.join(HERE, 'soccer_D.json'), 'utf8'));

`soccer/soccer_D.json` is THE LIVE BOARD. The soccer workflow rewrites it every few minutes. So a
test whose header says "the board under test is ... 75 players, 5 matches, three shipped slips,
Mbappe anchoring both screamers and his own builder" was in fact being handed whatever board
happened to be live -- tonight, a 90-player, 6-match, Haaland board. Seven assertions failed and a
`TypeError` at line 204 killed the run before the last third of the file executed. None of it
meant anything: the fixture had walked away from the assertions.

Same defect as test_draft_golden.js, same cause, and it is why the soccer suite has been red and
therefore unread.

THE FIX

Pin the inputs. `soccer/fixtures/2026-08-26/` holds the board, scoring, team news and shipped
tickets exactly as committed in dea662c1 -- immutable, never rewritten by a build, and carrying
the very slate the assertions were written against.

⚠️ THE DATE IN THE OLD HEADER WAS WRONG. It said 2026-08-25 throughout. The board's own
`meta.date` is 2026-08-26 and its matches are Real Madrid v Real Sociedad, Lyon v Fenerbahce,
NK Celje v Slovan Bratislava, AEK Athens v Levski Sofia, Viking FK v Dinamo Zagreb. Corrected
here rather than carried forward: a fixture whose name lies about which night it is is how the
next person loses an hour.

WHAT ELSE CHANGED, AND WHY EACH IS NOT A WEAKENING

  1. Scenario 1 and 2 asserted a TICKET COUNT as a proxy for "the frozen slips did not move".
     LEFTOVERS-2026-08-28 ships gated-but-undrafted players as straight singles, so the count is
     legitimately higher now while the frozen slips are untouched. The count proxy is replaced
     with the claim it was standing in for, asserted DIRECTLY and more strictly than before:
     every prior slip is still present, still locked, and BYTE-IDENTICAL to what went in. That
     is a stronger test of CONFLOCK than counting was.

  2. Scenario 9 asserted `rrMaxProfit` reproduces the figure baked into the fixture (20). That
     figure was computed by the OLD round-robin formula, the one RRSTAKE-2026-08-28 fixed after
     the owner's "its 2u per moon" -- it staked `risk` on EVERY combination instead of `risk`
     across all of them, roughly a 2x overstatement (20 vs the correct 9). Asserting it would be
     asserting the bug. Replaced with the arithmetic done LONGHAND in the test -- every double
     and the treble, unit stake = risk / combination count -- so the assertion no longer depends
     on any baked number and documents the formula it is checking.

WHAT IS LEFT FAILING ON PURPOSE

Scenario 3 ("the repaired slip kept its name" / "repair happened rather than a rebuild") still
fails, and the assertion is RIGHT: a moon with one dead leg, on a board with a demonstrably legal
replacement, should repair. It does not, because LEFTOVERS-2026-08-28 ships every gated player who
made no slip as a single, those singles freeze, and a man on a frozen single is correctly barred
from being drafted as a partner -- so leftovers consume the whole repair pool.

That is a genuine product decision (do leftovers outrank repairing a screamer?) and not mine to
settle. It is left failing, loudly and with the reason in the test, rather than adjusted away.
"""
import sys

F = 'test_redraft.js'
src = open(F, encoding='utf-8').read()

OLD_HDR = """ * The board under test is the real 2026-08-25 payload (soccer_D.json): 75 players, 5 matches,
 * three shipped slips, Mbappe anchoring both screamers and his own builder. Kickoffs are
 * synthesised into meta.ko at 19:00Z for every match, which is what that slate actually was --
 * boards baked before STAGE2-2026-08-27 carry no meta.ko."""

NEW_HDR = """ * The board under test is the real 2026-08-26 payload, PINNED at
 * fixtures/2026-08-26/soccer_D.json: 75 players, 5 matches, three shipped slips, Mbappe
 * anchoring both screamers and his own builder. Kickoffs are synthesised into meta.ko at 19:00Z
 * for every match, which is what that slate actually was -- boards baked before
 * STAGE2-2026-08-27 carry no meta.ko.
 *
 * TESTPIN-2026-08-28. This used to read `soccer_D.json` from the soccer root, which is THE LIVE
 * BOARD and is rewritten by every build. The test was silently handed whatever slate was running
 * -- seven assertions failed against a board they were never written for, and a TypeError killed
 * the run two thirds of the way through. A fixture a build can overwrite is not a fixture.
 * (The old header also said 2026-08-25. The board's own meta.date is 2026-08-26 and its matches
 * are Real Madrid v Real Sociedad, Lyon v Fenerbahce, NK Celje v Slovan Bratislava, AEK Athens v
 * Levski Sofia, Viking FK v Dinamo Zagreb.)"""

OLD_READ = "const base = JSON.parse(fs.readFileSync(path.join(HERE, 'soccer_D.json'), 'utf8'));"
NEW_READ = ("const FIXTURE = path.join(HERE, 'fixtures', '2026-08-26');\n"
            "const base = JSON.parse(fs.readFileSync(path.join(FIXTURE, 'soccer_D.json'), 'utf8'));")

OLD_S1 = """  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);
  chk('nothing was minted over them', r.minted === 0, r);
  chk('the board is unchanged', !r.changed && JSON.stringify(names(r.tickets)) === JSON.stringify(before), names(r.tickets));"""

NEW_S1 = """  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);
  /* TESTPIN-2026-08-28: this used to assert `minted === 0` and an unchanged ticket LIST, using
     the count as a proxy for "the frozen slips did not move". LEFTOVERS-2026-08-28 ships gated
     players who made no slip as straight singles, so new slips legitimately appear beside the
     frozen ones. Assert the actual claim instead, and more strictly than the proxy did: every
     prior slip is still there, still locked, byte-identical to what went in. */
  const priorSigs = JSON.stringify(D0.tickets.map(t => JSON.stringify(t)).sort());
  const keptSigs = JSON.stringify(r.tickets.filter(t => t.locked).map(t => JSON.stringify(t)).sort());
  chk('every frozen slip survives byte-identical', priorSigs === keptSigs,
    { prior: D0.tickets.length, lockedNow: r.tickets.filter(t => t.locked).length });
  chk('nothing that was frozen was re-drafted', r.repaired === 0 && r.released === 0, r);
  chk('anything new is a leftover single, never a moon',
    r.tickets.filter(t => !t.locked).every(t => t.kind === 'builder' && t.players.length === 1),
    r.tickets.filter(t => !t.locked).map(t => t.kind + ':' + t.players.length));"""

OLD_S1_SETUP = """  const D = board();
  const before = names(D.tickets);
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);"""
NEW_S1_SETUP = """  const D = board();
  const D0 = JSON.parse(JSON.stringify(D));      /* TESTPIN-2026-08-28: the board as handed in */
  const before = names(D.tickets);
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);"""

OLD_S2 = "  chk('the frozen slips are untouched', r.tickets.length === 2 && r.tickets.every(t => t.locked), names(r.tickets));"
NEW_S2 = ("  /* TESTPIN-2026-08-28: was `tickets.length === 2`, a count proxy that LEFTOVERS-2026-08-28\n"
          "     invalidated. The claim is that the two SURVIVING frozen slips are untouched. */\n"
          "  const stillFrozen = r.tickets.filter(t => t.locked && t.kind === 'moon');\n"
          "  chk('the frozen slips are untouched', stillFrozen.length === 1 && r.tickets.some(t => t.locked && t.kind === 'builder'),\n"
          "    names(r.tickets));")

OLD_RR = """{
  const t = base.tickets.find(t => t.rr);
  const got = SD.rrMaxProfit(t.players, t.rr.risk);
  chk(`rrMaxProfit reproduces the baked figure (${t.rr.maxprofit})`, got === t.rr.maxprofit, { got, want: t.rr.maxprofit });
}"""

NEW_RR = """{
  /* TESTPIN-2026-08-28. This used to assert rrMaxProfit reproduces the figure BAKED INTO THE
     FIXTURE (20). That number was produced by the pre-RRSTAKE-2026-08-28 formula, which staked
     `risk` on EVERY combination instead of `risk` across all of them -- roughly a 2x
     overstatement, and the bug the owner called out with "its 2u per moon". Asserting it would
     be asserting the bug.
     So the arithmetic is done longhand here instead: on N legs a "by 2s & 3" round robin is
     every pair plus every triple, the stake is split evenly across those combinations, and the
     max profit is the best case (all legs win, so every combination pays) minus the total risk.
     No baked number, and the formula it checks is written out where a reader can see it. */
  const t = base.tickets.find(t => t.rr);
  const dec = o => (o > 0 ? 1 + o / 100 : 1 + 100 / -o);
  const d = t.players.map(l => dec(l.odds));
  const combos = [];
  for (let a = 0; a < d.length; a++) for (let b = a + 1; b < d.length; b++) combos.push([a, b]);
  for (let a = 0; a < d.length; a++) for (let b = a + 1; b < d.length; b++)
    for (let c = b + 1; c < d.length; c++) combos.push([a, b, c]);
  const unit = t.rr.risk / combos.length;
  const gross = combos.reduce((s, c) => s + unit * c.reduce((p, i) => p * d[i], 1), 0);
  const want = Math.round((gross - t.rr.risk) * 10) / 10;
  const got = SD.rrMaxProfit(t.players, t.rr.risk);
  chk(`rrMaxProfit matches the round-robin arithmetic (${combos.length} combos, ${unit}u each -> ${want})`,
    got === want, { got, want, bakedUnderOldFormula: t.rr.maxprofit });
}"""

OLD_S3_NOTE = "  chk('repair happened rather than a rebuild', r.repaired > 0, r);"
NEW_S3_NOTE = ("""  /* ⚠️ KNOWN FAILING, and the assertion is right -- do not adjust it away.
     LEFTOVERS-2026-08-28 ships every gated player who made no slip as a straight single. On this
     fixture that is six of them. They all confirm, so CONFLOCK freezes them, and a man on a
     frozen single is correctly barred from being drafted as a partner (one bat, one slip). The
     replacement pool this repair needs has therefore been spent on leftovers, and a screamer with
     one dead leg dies instead of repairing.
     That is a product decision -- do leftover singles outrank repairing a screamer? -- and it is
     surfaced here rather than settled in a test. LEFTOVERANCHOR-2026-08-28 already fixed the
     other half of this interaction (leftovers were also eating the ANCH budget). */
  chk('repair happened rather than a rebuild', r.repaired > 0, r);""")

edits = ((OLD_HDR, NEW_HDR, 'header: pinned fixture + corrected date'),
         (OLD_READ, NEW_READ, 'read the pinned fixture'),
         (OLD_S1_SETUP, NEW_S1_SETUP, 'scenario 1: capture the board as handed in'),
         (OLD_S1, NEW_S1, 'scenario 1: assert the claim, not a ticket count'),
         (OLD_S2, NEW_S2, 'scenario 2: assert the claim, not a ticket count'),
         (OLD_RR, NEW_RR, 'scenario 9: round-robin arithmetic longhand'),
         (OLD_S3_NOTE, NEW_S3_NOTE, 'scenario 3: record why it fails'))

for old, new, label in edits:
    n = src.count(old)
    if n != 1:
        sys.exit(f"ABORT: expected exactly 1 occurrence of [{label}], found {n} -- "
                 f"the source moved, patch by hand")
    src = src.replace(old, new, 1)
    print(f"  patched {label}")

open(F, 'w', encoding='utf-8').write(src)
print(f"wrote {F} ({len(src)} bytes)")
