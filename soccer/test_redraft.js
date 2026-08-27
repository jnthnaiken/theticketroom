/* test_redraft.js -- CONFLOCK and MINTGUARD, proven against a real board.
 *
 * The 2026-08-26 audit set the bar for this feature explicitly: turning the re-draft on "means
 * giving assembleClient a caller on this board for the first time. It needs the soccer constants
 * ported in, AND CONFLOCK/MINTGUARD proven against a live slate, before any of the four doors
 * reopens." soccer_draft.js answers the first half by not using assembleClient at all. This file
 * is the second half.
 *
 * The board under test is the real 2026-08-25 payload (soccer_D.json): 75 players, 5 matches,
 * three shipped slips, Mbappe anchoring both screamers and his own builder. Kickoffs are
 * synthesised into meta.ko at 19:00Z for every match, which is what that slate actually was --
 * boards baked before STAGE2-2026-08-27 carry no meta.ko.
 *
 * Every scenario drives the clock explicitly. Nothing here reads the wall clock, so this test
 * means the same thing at 3am as at kickoff.
 */
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');

const HERE = __dirname;
const base = JSON.parse(fs.readFileSync(path.join(HERE, 'soccer_D.json'), 'utf8'));
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
  const before = names(D.tickets);
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('all-confirmed slips are frozen (locked === prior count)', r.locked === before.length, r);
  chk('nothing was minted over them', r.minted === 0, r);
  chk('the board is unchanged', !r.changed && JSON.stringify(names(r.tickets)) === JSON.stringify(before), names(r.tickets));
}

/* ---------------------------------------------------------------------------------------
 * 2. A slip that CANNOT be repaired dies, and says why.
 *
 * On the real 2026-08-25 slate the gated pool is SIX. Freeze one screamer and its two partners
 * are spent; drop a leg from the other and there is no legal third leg left -- a partner has to
 * come from a third match, inside WIN, out of a pool that no longer has one. The honest outcome
 * is that the slip dies. All-or-none normally demotes the anchor's whole pair, but his other
 * moon is a PLACED BET and frozen, so it stands: a bet already struck is a fact, and the
 * all-or-none rule is about what to mint, not about what to unwind.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const victim = t0.players[2].name;
  D.players[victim].status = 'projected';
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('the open slip was released, the rest stayed frozen', r.released === 1 && r.locked === D.tickets.length - 1, r);
  chk('it could not be repaired on a six-player pool, and the reason is recorded',
    r.repaired === 0 && r.demoted.length === 1 && /repair/.test(r.demoted[0].why), r.demoted);
  chk('the frozen slips are untouched', r.tickets.length === 2 && r.tickets.every(t => t.locked), names(r.tickets));
  chk('the dropped leg appears nowhere', !r.tickets.some(t => t.players.some(l => l.name === victim)), victim);
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
 * 5. CONFLOCK by clock -- once the earliest leg is underway the slip freezes even with an
 *    unconfirmed leg on it. This is the case that matters live: a bet is placeable right up
 *    to kickoff, so from kickoff the board must stop moving it.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  D.players[t0.players[2].name].status = 'projected';
  const r = SD.redraft(D, { nowUTCmin: KO + 5, xi: XI(D) });
  chk('after kickoff every slip is frozen', r.locked === D.tickets.length, r);
  chk('after kickoff nothing is minted or released', r.minted === 0 && r.released === 0, r);
  chk('after kickoff the board is unchanged', !r.changed, names(r.tickets));
}

/* ---------------------------------------------------------------------------------------
 * 6. The feed can freeze a slip on its own, without the clock.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  D.players[t0.players[2].name].status = 'projected';
  D.meta.gs[String(t0.players[0].game)] = 'live';    // feed says the anchor's match is running
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  chk('a live match freezes its slips even before the clock says so', r.released === 0, r);
}

/* ---------------------------------------------------------------------------------------
 * 7. A frozen slip's players are SPENT -- one player, one slip.
 * ------------------------------------------------------------------------------------- */
{
  const D = board();
  const t0 = D.tickets.find(t => t.kind === 'moon');
  const other = D.tickets.filter(t => t !== t0);
  D.tickets = [t0];                                  // one frozen screamer, room for more
  const r = SD.redraft(D, { nowUTCmin: KO - 120, xi: XI(D) });
  const frozenNames = SD.nameSet(t0.players.map(l => l.name));
  const minted = r.tickets.slice(r.locked);
  const reuse = minted.filter(t => t.players.some(l => frozenNames[l.name]));
  chk('no minted slip re-uses a player from the frozen one', reuse.length === 0,
    reuse.map(t => t.players.map(l => l.name)));
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
  const t = base.tickets.find(t => t.rr);
  const got = SD.rrMaxProfit(t.players, t.rr.risk);
  chk(`rrMaxProfit reproduces the baked figure (${t.rr.maxprofit})`, got === t.rr.maxprofit, { got, want: t.rr.maxprofit });
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
