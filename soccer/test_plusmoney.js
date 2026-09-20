/* test_plusmoney.js -- PLUSMONEY-2026-09-11, amended FLOOR200-2026-09-17.
 *
 * FLOOR200: soccer's floor is now -200 (DEFAULTS.MIN_ODDS); NFL pins its own +100 in
 * nfl_draft_cli.js. The checks below test "shorter than the floor", with FLOOR read from DEFAULTS.
 *
 * Original rule, kept for history: only +100 and longer can make the board.
 *
 * Owner: "only + money guys can make the board" -> "+100 and longer" (evens stays in) ->
 * "i want to do it with nfl as well". The rule is DEFAULTS.MIN_ODDS in soccer_draft.js, the one
 * draft soccer and NFL share. These checks prove it holds at every door a player can come
 * through, not just the pool gate:
 *
 *   1. priceOk()        -- the boundary: +100 in, -110 out, unpriced out, null = rule off
 *   2. draft()          -- a fresh draft, including the Z_GATE-lifted wide retry
 *   3. redraft()        -- OPEN slips drafted before the rule lose their minus-money legs
 *                          (repair, top-up and FINALREPAIR all draw on alive[]/placeable)
 *   4. redraft()        -- a LOCKED slip is a placed bet and is carried verbatim, price or not
 *   5. NFL              -- nfl_draft_cli.js's CFG does not set MIN_ODDS, so it inherits the floor
 *   6. MIN_ODDS = null  -- restores the old behaviour exactly (the golden board reproduces)
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');
/* TOP8-2026-09-17: this file tests the anchor + screamer engine, which soccer no longer runs by
   default (DEFAULTS.TOP_SINGLES = 8) but NFL still does. Pin it off so the engine stays covered. */
SD.DEFAULTS.TOP_SINGLES = 0;

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail).slice(0, 400)); }
}
const J = p => JSON.parse(fs.readFileSync(path.join(__dirname, p), 'utf8'));
const legsOf = ts => ts.flatMap(t => (t.legs || t.players || []));
const FLOOR = -200;
const minus = ls => ls.filter(l => l.odds == null || Number(l.odds) < FLOOR).map(l => `${l.name} ${l.odds}`);

console.log('=== 1. the boundary ===');
{
  const C = SD.DEFAULTS;
  chk('DEFAULTS.MIN_ODDS is -200 (soccer)', C.MIN_ODDS === FLOOR);
  chk('+100 (evens) is eligible', SD.priceOk({ odds: 100 }, C));
  chk('+400 is eligible', SD.priceOk({ odds: 400 }, C));
  chk('-110 is eligible', SD.priceOk({ odds: -110 }, C));
  chk('-200 is eligible (the floor itself)', SD.priceOk({ odds: -200 }, C));
  chk('-201 is NOT eligible', !SD.priceOk({ odds: -201 }, C));
  chk('-333 is NOT eligible', !SD.priceOk({ odds: -333 }, C));
  chk('an unpriced man is NOT eligible', !SD.priceOk({ odds: null }, C));
  chk('MIN_ODDS null switches the rule off', SD.priceOk({ odds: -400 }, SD.cfgOf({ MIN_ODDS: null })));
  chk('MIN_ODDS 100 (the NFL floor) still refuses -110', !SD.priceOk({ odds: -110 }, SD.cfgOf({ MIN_ODDS: 100 })));
}

console.log('\n=== 2. fresh draft ===');
{
  const scored = J('fixtures/2026-08-26/scored.json');
  const tn = J('fixtures/2026-08-26/teamnews.json');
  const xi = SD.nameSet(Object.keys(tn.xi || {}));
  const got = SD.draft(scored, {}, { xi });
  chk('no leg on the fresh draft is shorter than -200', minus(legsOf(got.tickets)).length === 0, minus(legsOf(got.tickets)));
  chk('the pool holds nobody shorter than -200', got.pool.every(p => p.odds >= FLOOR), got.pool.filter(p => p.odds < FLOOR).map(p => p.name));

  /* The slate's strongest man at -250 must vanish; at -150 he is allowed back in. */
  const s2 = JSON.parse(JSON.stringify(scored));
  const top = s2.slice().sort((a, b) => b.TOTAL - a.TOTAL)[0];
  top.odds = -250;
  const g2 = SD.draft(s2, {}, { xi });
  chk(`the slate's strongest man at -250 (${top.name}) makes no ticket`, !legsOf(g2.tickets).some(l => l.name === top.name));
  chk('and the board still drafts', g2.tickets.length > 0, g2.tickets.length);
  const off = SD.draft(s2, { MIN_ODDS: null }, { xi });
  chk('with the rule off he is back on the board', legsOf(off.tickets).some(l => l.name === top.name));
  const s3 = JSON.parse(JSON.stringify(scored));
  const top3 = s3.slice().sort((a, b) => b.TOTAL - a.TOTAL)[0];
  top3.odds = -150;
  const g3 = SD.draft(s3, {}, { xi });
  chk(`at -150 he is draftable (${top3.name} in the pool)`, g3.pool.some(p => p.name === top3.name));
  const g3n = SD.draft(s3, { MIN_ODDS: 100 }, { xi });
  chk('and under the +100 floor he is not', !g3n.pool.some(p => p.name === top3.name));
}

console.log('\n=== 3. redraft: an open slip with a leg shorter than the floor ===');
{
  const D = J('boards/2026-09-09.json');
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; });
  D.tickets.forEach(t => { delete t.locked; });
  D.meta.finals = []; D.meta.gs = {};
  const leg = D.tickets[0].players[0].name;
  D.players[leg].odds = -300;
  D.tickets.forEach(t => t.players.forEach(l => { if (l.name === leg) l.odds = -300; }));
  const ko = Math.min(...Object.values(D.meta.ko).map(Number));
  const r = SD.redraft(D, { nowUTCmin: ko - 120, xi: null });
  const after = minus(legsOf(r.tickets));
  chk(`${leg} forced to -300 is repaired off every open slip`, after.length === 0, after);
  chk('and the board is not wiped out', r.tickets.length > 0, r.tickets.length);
}

console.log('\n=== 4. redraft: a LOCKED slip is a placed bet ===');
{
  const D = J('boards/2026-09-09.json');
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; });
  D.tickets.forEach(t => { delete t.locked; });
  D.meta.finals = []; D.meta.gs = {};
  const victim = D.tickets[0];
  const leg = victim.players[0].name;
  D.players[leg].odds = -300;
  D.tickets.forEach(t => t.players.forEach(l => { if (l.name === leg) l.odds = -300; }));
  victim.locked = true;
  const sig = JSON.stringify(victim.players.map(l => [l.name, l.odds]));
  const ko = Math.min(...Object.values(D.meta.ko).map(Number));
  const r = SD.redraft(D, { nowUTCmin: ko - 120, xi: null });
  const kept = r.tickets.find(t => t.name === victim.name && JSON.stringify(t.players.map(l => [l.name, l.odds])) === sig);
  chk(`locked "${victim.name}" (${leg} -300) is carried verbatim`, !!kept);
  const openMinus = minus(legsOf(r.tickets.filter(t => t !== kept)));
  chk('every OTHER slip respects the floor', openMinus.length === 0, openMinus);
}

console.log('\n=== 5. NFL keeps +100 ===');
{
  /* CFGDRIFT-2026-09-20: the football CFG moved out of nfl_draft_cli.js into nfl/nfl_cfg.js so
     the fresh-draft and rebuild entry points cannot drift apart. This check is about the VALUE,
     not the file, so it now requires the module -- which is also stricter than scraping the
     source with a regex, because it fails if the file does not load at all. */
  const CFG = require(path.join(__dirname, '..', 'nfl', 'nfl_cfg.js')).CFG;
  chk('nfl_cfg.js exports a CFG', !!CFG && typeof CFG === 'object');
  chk('NFL CFG pins MIN_ODDS 100', CFG.MIN_ODDS === 100);
  chk('so the NFL draft runs with MIN_ODDS 100', SD.cfgOf(CFG).MIN_ODDS === 100);
  chk('and refuses -110', !SD.priceOk({ odds: -110 }, SD.cfgOf(CFG)));
  const staged = fs.readFileSync(path.join(__dirname, '..', '.github', 'workflows', 'nfl-build.yml'), 'utf8');
  chk('and nfl-build.yml stages this very soccer_draft.js', /cp \.\.\/soccer\/soccer_draft\.js \.work\//.test(staged));
}

console.log('\n=== 6. MIN_ODDS null reproduces the pre-rule golden ===');
{
  const scored = J('fixtures/2026-08-26/scored.json');
  const tn = J('fixtures/2026-08-26/teamnews.json');
  const want = J('fixtures/2026-08-26/tickets_snake.json');
  const got = SD.draft(scored, { MIN_ODDS: null }, { xi: SD.nameSet(Object.keys(tn.xi || {})) });
  const g = got.tickets.map(t => t.legs.map(l => l.name));
  const w = (want.tickets || want).map(t => (t.legs || t.players).map(l => l.name));
  chk('same legs as the shipped 08-26 board', JSON.stringify(g) === JSON.stringify(w), { got: g, want: w });
}

console.log(fail ? `\n${fail} FAILURE(S)` : '\nALL GREEN -- soccer floor -200, NFL floor +100; locked bets are untouched');
process.exit(fail ? 1 : 0);
