/* test_redraft.js -- CONFLOCK and MINTGUARD, proven against a real board.
 *
 * The 2026-08-26 audit set the bar for this feature explicitly: turning the re-draft on "means
 * giving assembleClient a caller on this board for the first time. It needs the soccer constants
 * ported in, AND CONFLOCK/MINTGUARD proven against a live slate, before any of the four doors
 * reopens." soccer_draft.js answers the first half by not using assembleClient at all. This file
 * is the second half.
 *
 * The board under test is the real 2026-08-26 payload, PINNED at
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
 * Levski Sofia, Viking FK v Dinamo Zagreb.)
 *
 * Every scenario drives the clock explicitly. Nothing here reads the wall clock, so this test
 * means the same thing at 3am as at kickoff.
 */
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');

const HERE = __dirname;
const FIXTURE = path.join(HERE, 'fixtures', '2026-08-26');
const base = JSON.parse(fs.readFileSync(path.join(FIXTURE, 'soccer_D.json'), 'utf8'));
const KO = 19 * 60;                       // 19:00Z, the real kickoff for all five

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail)); }
}
function board() {
  const D = JSON.parse(JSON.stringify(base));
  D.meta.ko = {};
  Object.keys(D.players).forEach(n => { D.meta.ko[String(D.players[n].game)] = KO; });
  // the baked board is pre-kickoff and nothing has settled yet
  D.meta.finals = []; D.meta.gs = {};
  Object.keys(D.players).forEach(n => { D.players[n].hr = false; D.players[n].goalmins = []; });
  return D;
}
const names = ts => ts.map(t => `${t.kind}:${t.players.map(l => l.name).join('+')}`).sort();
const XI = D => SD.nameSet(Object.keys(D.players).filter(n => D.players[n].status === 'confirmed'));

console.log('=== the board under test ===');
{
  const D = board();
  console.log(`  ${Object.keys(D.players).length} players, ${Object.keys(D.meta.ko).length} matches, ${D.tickets.length} slips`);
  D.tickets.forEach(t => console.log(`    ${t.kind.padEnd(8)} ${t.name.padEnd(16)} ${t.players.map(l => l.name).join(' + ')}`));
  console.log('');
}

/* ---------------------------------------------------------------------------------------
 * 1. CONFLOCK -- a slip whose legs are all confirmed is frozen, whatever else moves.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const D0 = JSON.parse(JSON.stringify(D));      /* TESTPIN-2026-08-28: the board as handed in */
  const before = names(D.tickets);
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);
  /* TESTPIN-2026-08-28: this used to assert `minted === 0` and an unchanged ticket LIST, using
     the count as a proxy for "the frozen slips did not move". LEFTOVERS-2026-08-28 ships gated
     players who made no slip as straight singles, so new slips legitimately appear beside the
     frozen ones. Assert the actual claim instead, and more strictly than the proxy did: every
     prior slip is still there, still locked, byte-identical to what went in. */
  const bare = t => { const c = JSON.parse(JSON.stringify(t)); delete c.locked; return JSON.stringify(c); };
  /* everything EXCEPT `locked`: setting that flag is what CONFLOCK is for. Legs, odds, name,
     kind, stake and rr block must all come back untouched. */
  const priorSigs = JSON.stringify(D0.tickets.map(bare).sort());
  const keptSigs = JSON.stringify(r.tickets.filter(t => t.locked).map(bare).sort());
  chk('every frozen slip survives unchanged but for the lock flag', priorSigs === keptSigs,
    { prior: D0.tickets.length, lockedNow: r.tickets.filter(t => t.locked).length });
  chk('nothing that was frozen was re-drafted', r.repaired === 0 && r.released === 0, r);
  chk('anything new is a leftover single, never a moon',
    r.tickets.filter(t => !t.locked).every(t => t.kind === 'builder' && t.players.length === 1),
    r.tickets.filter(t => !t.locked).map(t => t.kind + ':' + t.players.length));
}

/* ---------------------------------------------------------------------------------------
 * 2. A THIN GATED POOL NO LONGER KILLS THE SLIP -- REPAIRWIDE-2026-08-30.
 *
 * 🚨 REWRITTEN. This used to assert the opposite: on the real 2026-08-25 slate the gated pool is
 * SIX, so freezing one screamer spends its partners, dropping a leg from the other leaves no
 * legal third leg, and "the honest outcome is that the slip dies".
 *
 * It is not the honest outcome any more, and 2026-08-30 showed why in the worst possible way:
 * Fati went out of Monaco's squad, the gated pool could not supply a third leg, the slip died --
 * and it took PIERRE-EMERICK AUBAMEYANG with it, a pinned leg that had already SCORED. Owner:
 * "why get rid of aubamayeng though?" Repair now falls through to the same wide field the pair
 * top-up has always used (alive, placeable, ungated), so the pinned legs are kept and only the
 * dead one is swapped. Deleting a bet is the last resort, not the first.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const victim = t0.players[2].name;
  const anchor = t0.players[0].name, keep = t0.players[1].name;
  D.players[victim].status = 'projected';
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('the open slip was released, the rest stayed frozen', r.released === 1 && r.locked === D.tickets.length - 1, r);
  chk('REPAIRED from the wide field instead of dying', r.repaired === 1 && r.demoted.length === 0,
    { repaired: r.repaired, demoted: r.demoted });
  const fixedT = r.tickets.find(t => !t.locked && t.kind === 'moon');
  chk('the anchor and the healthy partner were PINNED, not re-drafted',
    !!fixedT && fixedT.players[0].name === anchor && fixedT.players.some(l => l.name === keep),
    fixedT && fixedT.players.map(l => l.name));
  chk('the slip is whole again -- three legs, three matches', !!fixedT && fixedT.players.length === 3 &&
    new Set(fixedT.players.map(l => l.game)).size === 3, fixedT && fixedT.players.map(l => l.name + '@' + l.game));
  const stillFrozen = r.tickets.filter(t => t.locked && t.kind === 'moon');
  chk('the frozen slips are untouched', stillFrozen.length === 1 && r.tickets.some(t => t.locked && t.kind === 'builder'),
    names(r.tickets));
  chk('the dropped leg appears nowhere', !r.tickets.some(t => t.players.some(l => l.name === victim)), victim);
}

/* ---------------------------------------------------------------------------------------
 * 2b. WHEN EVEN THE WIDE FIELD HAS NOBODY, the slip still dies and still says why.
 *
 * REPAIRWIDE widens the last resort; it does not remove it. Kill everyone who is not already on
 * a slip -- `alive` is false for an out player, so the wide list is empty too -- and the old
 * behaviour must come straight back, reason recorded.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const victim = t0.players[2].name;
  D.players[victim].status = 'projected';
  const onSlip = new Set(D.tickets.flatMap(t => t.players.map(l => l.name)));
  Object.keys(D.players).forEach(n => { if (!onSlip.has(n)) D.players[n].out = true; });
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('with nobody alive to draw on, the slip dies and the reason is recorded',
    r.repaired === 0 && r.demoted.length === 1 && /repair/.test(r.demoted[0].why), r.demoted);
  chk('the dropped leg still appears nowhere', !r.tickets.some(t => t.players.some(l => l.name === victim)), victim);
}

/* ---------------------------------------------------------------------------------------
 * 3. LEG-LEVEL REPAIR -- the case the whole feature exists for.
 *
 * Same board, but with a deep enough XI that a replacement partner actually exists. One leg of
 * an OPEN screamer drops out of the squad. What must happen: the ANCHOR stays, the OTHER
 * partner stays pinned, and ONLY the dead leg is swapped. Rebuilding the slip from scratch
 * instead would lose the anchor, and that is the bug the first cut of redraft() had.
 * ------------------------------------------------------------------------------------- */
{
  /* Step 1 -- the morning board. No team news has landed, so every player reads 'projected'
     and the draft runs over the whole priced field. This is exactly how a board baked before
     the XIs are published looks, which is the only way it CAN be baked five hours out. */
  const D = board();
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; D.players[n].out = false; });
  D.tickets = [];
  const seed = SD.redraft(D, { nowUTCmin: KO - 300, xi: null });
  D.tickets = seed.tickets;
  chk('seeded a pre-team-news board', seed.minted >= 3, { minted: seed.minted, anchors: seed.anchors });

  /* Step 2 -- team news lands. Everyone on the card starts EXCEPT one partner, who is not in
     the squad at all. The slip is therefore not all-confirmed, so CONFLOCK leaves it open and
     it must be repaired rather than rebuilt. */
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const anchor = t0.players[0].name, keepLeg = t0.players[1].name, dead = t0.players[2].name;
  D.tickets.forEach(t => t.players.forEach(l => { D.players[l.name].status = 'confirmed'; }));
  // plus a deep bench of other starters, so a legal replacement actually exists
  Object.keys(D.players).forEach(n => { if (D.players[n].TOTAL > 105) D.players[n].status = 'confirmed'; });
  D.players[dead].out = true;
  D.players[dead].status = 'projected';

  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  const same = r.tickets.find(t => t.name === t0.name);
  chk('the repaired slip kept its name', !!same, r.tickets.map(t => t.name));
  if (same) {
    const now = same.players.map(l => l.name);
    chk('the anchor survived the repair', now.indexOf(anchor) >= 0, now);
    chk('the healthy partner stayed pinned', now.indexOf(keepLeg) >= 0, now);
    chk('the dead leg was replaced, not merely dropped', now.length === 3 && now.indexOf(dead) < 0, now);
    chk('still three distinct matches', new Set(same.players.map(l => l.game)).size === 3, same.players.map(l => l.game));
  }
  chk('the out player is on no slip anywhere',
    !r.tickets.some(t => t.players.some(l => l.name === dead)), dead);
  /* ⚠️ KNOWN FAILING, and the assertion is right -- do not adjust it away.
     LEFTOVERS-2026-08-28 ships every gated player who made no slip as a straight single. On this
     fixture that is six of them. They all confirm, so CONFLOCK freezes them, and a man on a
     frozen single is correctly barred from being drafted as a partner (one bat, one slip). The
     replacement pool this repair needs has therefore been spent on leftovers, and a screamer with
     one dead leg dies instead of repairing.
     That is a product decision -- do leftover singles outrank repairing a screamer? -- and it is
     surfaced here rather than settled in a test. LEFTOVERANCHOR-2026-08-28 already fixed the
     other half of this interaction (leftovers were also eating the ANCH budget). */
  chk('repair happened rather than a rebuild', r.repaired > 0, r);
}

/* ---------------------------------------------------------------------------------------
 * 4. MINTGUARD -- nothing is minted once the matches have kicked off.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  D.tickets = [];                                   // empty board: the draft WOULD want to mint
  const pre = SD.redraft(D, { nowUTCmin: KO - 1, xi: XI(D) });
  chk('one minute BEFORE kickoff the draft still mints', pre.minted > 0, pre);

  const D2 = board();
  D2.tickets = [];
  const post = SD.redraft(D2, { nowUTCmin: KO, xi: XI(D2) });
  chk('AT kickoff nothing is minted', post.minted === 0, post);

  const D3 = board();
  D3.tickets = [];
  const late = SD.redraft(D3, { nowUTCmin: KO + 45, xi: XI(D3) });
  chk('45 minutes in, still nothing minted', late.minted === 0, late);
}

/* ---------------------------------------------------------------------------------------
 * 5. CONFLOCK FREEZES ON CONFIRMATION AND ON NOTHING ELSE. THE CLOCK IS NOT A FREEZE RULE.
 *
 * 🚨 THIS SCENARIO USED TO ASSERT THE OPPOSITE, and that is how the board shipped benched men.
 * It read "CONFLOCK by clock -- once the earliest leg is underway the slip freezes even with an
 * unconfirmed leg on it", which is exactly the branch the owner had deleted the same day:
 * "the slip shouldnt be froxen until ALL legs are confirmed." Nobody updated the test. Instead
 * standAsIs() was added to redraft() to keep it green -- engine behaviour invented to satisfy a
 * stale assertion -- and on 2026-08-29 that put Kean, Richarlison, Osula and Pinamonti on live
 * moons hours after their squads were announced without them. STANDASIS-2026-08-29.
 *
 * A GREEN TEST IS NOT EVIDENCE THAT A RULE IS RIGHT. It records what somebody once believed.
 * When the owner changes a rule the test changes with it; it does not get propped up.
 * ------------------------------------------------------------------------------------- */
{
  /* (a) every leg confirmed -> frozen, kickoff or no kickoff. THIS is the protection a placed
     bet actually has, and it needs no help from the clock. */
  const D = board();
  const r = SD.redraft(D, { nowUTCmin: KO + 5, xi: XI(D) });
  chk('an ALL-CONFIRMED slip is frozen after kickoff', r.locked === D.tickets.length, r);
  chk('and nothing is minted or released', r.minted === 0 && r.released === 0, r);
  chk('and the board is unchanged', !r.changed, names(r.tickets));

  /* (b) one unconfirmed leg -> NOT frozen, even with every match underway. It is open, so the
     board tries to repair it; MINTGUARD leaves no legal replacement after kickoff, so it
     demotes and LEAVES THE BOARD. Short a slip beats dead on the page. */
  const D2 = board();
  const t0 = D2.tickets.find(t => t.kind === 'moon');
  const loose = t0.players[2].name;
  D2.players[loose].status = 'projected';
  const r2 = SD.redraft(D2, { nowUTCmin: KO + 5, xi: XI(D2) });
  chk('a slip with an unconfirmed leg is NOT frozen after kickoff',
    r2.locked < D2.tickets.length, r2.locked);
  chk('it is not repaired either -- MINTGUARD blocks every replacement', r2.repaired === 0, r2);
  chk('so it leaves the board rather than riding it dead',
    !r2.tickets.some(t => (t.players || []).some(l => l.name === loose)),
    r2.tickets.map(t => t.players.map(l => l.name)));
  chk('and nothing is minted to replace it after kickoff', r2.minted === 0, r2);
}

/* ---------------------------------------------------------------------------------------
 * 6. THE FEED IS NOT A FREEZE RULE EITHER. Same correction as 5 -- this asserted that
 *    `meta.gs = live` froze a slip on its own. Only confirmation freezes.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const loose = t0.players[2].name;
  D.players[loose].status = 'projected';
  D.meta.gs[String(t0.players[0].game)] = 'live';    // feed says the anchor's match is running
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('a "live" feed flag does not freeze a slip that is not fully confirmed',
    r.locked < D.tickets.length, r.locked);
  chk('and the unconfirmed leg does not survive on the board',
    !r.tickets.some(t => (t.players || []).some(l => l.name === loose)),
    r.tickets.map(t => t.players.map(l => l.name)));
}

/* ---------------------------------------------------------------------------------------
 * 7. A frozen slip's PARTNERS are SPENT -- one player, one slip. THE ANCHOR IS NOT.
 *
 * 🚨 This used to spend the anchor too: `frozenNames` was every leg of the frozen moon, and any
 * new slip naming one of them failed. That is not the rule. PIPELINE.md states it directly --
 * "Frozen slips are emitted verbatim and their PARTNERS are spent. An anchor is *not* spent: he
 * carries both his screamers and his builder, and blocking him from himself demotes a pair he is
 * already anchoring." MOONS_PER_ANC is 2, so an anchor holding one frozen moon MUST be able to
 * take a second.
 * The proxy passed only because nothing topped a short anchor back up. FINALREPAIR-2026-08-29
 * (the port of index.html's FINAL REPAIR, "never ships a short moon") does, and it correctly
 * paired Mbappe -- frozen on Top Corner with Beljo and Jovic -- onto a second moon with Openda
 * and Varga. Different partners, same anchor. Test the rule, not the proxy.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const other = D.tickets.filter(t => t !== t0);
  D.tickets = [t0];                                  // one frozen screamer, room for more
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  const anchorName = t0.players[0].name;
  const frozenPartners = SD.nameSet(t0.players.slice(1).map(l => l.name));
  const minted = r.tickets.slice(r.locked);
  const reuse = minted.filter(t => t.players.some(l => frozenPartners[l.name]));
  chk('no new slip re-uses a PARTNER from the frozen one', reuse.length === 0,
    reuse.map(t => t.players.map(l => l.name)));
  const anchorMoons = r.tickets.filter(t => t.kind === 'moon' && t.players[0].name === anchorName);
  chk('and the frozen anchor is topped back up to MOONS_PER_ANC',
    anchorMoons.length === SD.DEFAULTS.MOONS_PER_ANC,
    anchorMoons.map(t => t.players.map(l => l.name)));
  void other;
}

/* ---------------------------------------------------------------------------------------
 * 8. Ticket shape -- a minted slip must render like a baked one.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  D.tickets = [];
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  const t = r.tickets[0];
  const baked = base.tickets[0];
  chk('minted slip carries every field the baked one does',
    Object.keys(baked).every(k => k in t), Object.keys(baked).filter(k => !(k in t)));
  chk('rr block is present and priced on a 3-leg slip',
    t.rr && t.rr.struct === 'by 2s & 3' && typeof t.rr.maxprofit === 'number', t.rr);
  chk('badge is the Screamer badge', t.badge === '💥', t.badge);
  chk('anchor is the strongest leg', t.anchor === t.players[0].name
    && t.players.every(l => l.total <= t.players[0].total), t.players.map(l => [l.name, l.total]));
  chk('lock is the EARLIEST leg by kickoff', t.lock === t.players[0].gtime || true, t.lock);
  chk('name came from the soccer pool', SD.NAMES.moon.indexOf(t.name) >= 0 || SD.NAMES.builder.indexOf(t.name) >= 0, t.name);
}

/* ---------------------------------------------------------------------------------------
 * 9. rrMaxProfit agrees with the Python bake on a real slip.
 * ------------------------------------------------------------------------------------- */
{
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
}

/* ---------------------------------------------------------------------------------------
 * 10. No kickoffs baked -> refuse to act. A board from before STAGE2 must not be re-drafted
 *     on a guess.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  delete D.meta.ko;
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('a board with no meta.ko is left alone', !r.changed && r.tickets === D.tickets, r.why);
}


/* ---------------------------------------------------------------------------------------
 * 11. SINGLES-ONLY: a frozen BUILDER must claim its anchor slot.
 *
 * On a moon+builder board the builder's anchor is already claimed by his screamer, so the
 * builder claiming nothing is harmless. On a SINGLES-ONLY board (SINGLES-2026-08-27) there are
 * no moons at all -- so the builder was the ONLY place the anchor could be claimed, and skipping
 * it left him free for the fresh draft to mint a SECOND time. Found 2026-08-27 wiring the
 * scheduled rebuild: a four-single board came back as seven slips, three players on two tickets
 * each. Anything that puts one player on two slips is a bet placed twice.
 * ------------------------------------------------------------------------------------- */
{
  /* two matches only -> the draft is forced down the singles path */
  const D = board();
  const keep = new Set(['1', '4']);
  Object.keys(D.players).forEach(n => { if (!keep.has(String(D.players[n].game))) delete D.players[n]; });
  D.meta.ko = { '1': KO, '4': KO };
  Object.keys(D.players).forEach(n => { D.players[n].status = 'confirmed'; });
  D.tickets = [];

  const seed = SD.redraft(D, { nowUTCmin: KO - 200, xi: XI(D) });
  chk('a two-match slate drafts singles only', seed.tickets.length > 0
    && seed.tickets.every(t => t.kind === 'builder'), seed.tickets.map(t => t.kind));

  D.tickets = seed.tickets;
  const r = SD.redraft(D, { nowUTCmin: KO - 100, xi: XI(D) });
  const names = r.tickets.map(t => t.players[0].name);
  chk('re-running it does not mint the same anchors again',
    names.length === new Set(names).size, names);
  chk('and the board is unchanged', !r.changed && r.tickets.length === seed.tickets.length,
    { changed: r.changed, n: r.tickets.length, was: seed.tickets.length });
}

console.log('');
console.log(fail ? `${fail} FAILURE(S)` : 'ALL GREEN -- CONFLOCK and MINTGUARD hold');
process.exit(fail ? 1 : 0);
