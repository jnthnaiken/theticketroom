/* test_plusmoney.js -- PLUSMONEY-2026-09-11: only +100 and longer can make the board.
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

let fail = 0;
function chk(label, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) { fail++; if (detail !== undefined) console.log('      ' + JSON.stringify(detail).slice(0, 400)); }
}
const J = p => JSON.parse(fs.readFileSync(path.join(__dirname, p), 'utf8'));
const legsOf = ts => ts.flatMap(t => (t.legs || t.players || []));
const minus = ls => ls.filter(l => l.odds == null || Number(l.odds) < 100).map(l => `${l.name} ${l.odds}`);

console.log('=== 1. the boundary ===');
{
  const C = SD.DEFAULTS;
  chk('DEFAULTS.MIN_ODDS is 100', C.MIN_ODDS === 100);
  chk('+100 (evens) is eligible', SD.priceOk({ odds: 100 }, C));
  chk('+101 is eligible', SD.priceOk({ odds: 101 }, C));
  chk('-110 is NOT eligible', !SD.priceOk({ odds: -110 }, C));
  chk('-100 is NOT eligible', !SD.priceOk({ odds: -100 }, C));
  chk('an unpriced man is NOT eligible', !SD.priceOk({ odds: null }, C));
  chk('MIN_ODDS null switches the rule off', SD.priceOk({ odds: -400 }, SD.cfgOf({ MIN_ODDS: null })));
}

console.log('\n=== 2. fresh draft ===');
{
  const scored = J('fixtures/2026-08-26/scored.json');
  const tn = J('fixtures/2026-08-26/teamnews.json');
  const xi = SD.nameSet(Object.keys(tn.xi || {}));
  const nMinus = scored.filter(p => p.odds != null && p.odds < 100).length;
  const got = SD.draft(scored, {}, { xi });
  chk(`fixture carries minus-money men to exclude (${nMinus})`, nMinus > 0);
  chk('no leg on the fresh draft is shorter than +100', minus(legsOf(got.tickets)).length === 0, minus(legsOf(got.tickets)));
  chk('the pool holds no minus-money man', got.pool.every(p => p.odds >= 100), got.pool.filter(p => p.odds < 100).map(p => p.name));

  /* Force the strongest man on the slate to odds-on. He must vanish from every ticket, and the
     board must still draft -- the rule narrows the field, it does not zero it. */
  const s2 = JSON.parse(JSON.stringify(scored));
  const top = s2.slice().sort((a, b) => b.TOTAL - a.TOTAL)[0];
  top.odds = -150;
  const g2 = SD.draft(s2, {}, { xi });
  const names2 = legsOf(g2.tickets).map(l => l.name);
  chk(`the slate's strongest man at -150 (${top.name}) makes no ticket`, !names2.includes(top.name));
  chk('and the board still drafts', g2.tickets.length > 0, g2.tickets.length);

  const off = SD.draft(s2, { MIN_ODDS: null }, { xi });
  chk('with the rule off he is back on the board', legsOf(off.tickets).some(l => l.name === top.name));
}

console.log('\n=== 3. redraft: open slips drafted before the rule ===');
{
  const D = J('boards/2026-09-09.json');
  const before = minus(legsOf(D.tickets));
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; });
  D.tickets.forEach(t => { delete t.locked; });
  D.meta.finals = []; D.meta.gs = {};
  const ko = Math.min(...Object.values(D.meta.ko).map(Number));
  const r = SD.redraft(D, { nowUTCmin: ko - 120, xi: null });
  const after = minus(legsOf(r.tickets));
  chk(`the 09-09 board carried minus-money legs before (${before.length})`, before.length > 0);
  chk('after a redraft, no OPEN slip carries one', after.length === 0, after);
  chk('and the board is not wiped out', r.tickets.length > 0, r.tickets.length);
  console.log(`      ${D.tickets.length} slips before -> ${r.tickets.length} after`);
}

console.log('\n=== 4. redraft: a LOCKED slip is a placed bet ===');
{
  const D = J('boards/2026-09-09.json');
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; });
  D.tickets.forEach(t => { delete t.locked; });
  D.meta.finals = []; D.meta.gs = {};
  const victim = D.tickets.find(t => minus(t.players).length > 0);
  victim.locked = true;
  const sig = JSON.stringify(victim.players.map(l => [l.name, l.odds]));
  const ko = Math.min(...Object.values(D.meta.ko).map(Number));
  const r = SD.redraft(D, { nowUTCmin: ko - 120, xi: null });
  const kept = r.tickets.find(t => t.name === victim.name && JSON.stringify(t.players.map(l => [l.name, l.odds])) === sig);
  chk(`locked "${victim.name}" (${minus(victim.players).join(', ')}) is carried verbatim`, !!kept);
  const openMinus = minus(legsOf(r.tickets.filter(t => t !== kept)));
  chk('every OTHER slip is still plus money', openMinus.length === 0, openMinus);
}

console.log('\n=== 5. NFL inherits the floor ===');
{
  const src = fs.readFileSync(path.join(__dirname, '..', 'nfl', 'nfl_draft_cli.js'), 'utf8');
  const m = src.match(/const CFG = (\{[\s\S]*?\});/);
  chk('nfl_draft_cli.js declares a CFG', !!m);
  const CFG = m ? Function('return ' + m[1])() : {};
  chk('NFL CFG does not override MIN_ODDS', !('MIN_ODDS' in CFG));
  chk('so the NFL draft runs with MIN_ODDS 100', SD.cfgOf(CFG).MIN_ODDS === 100);
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

console.log(fail ? `\n${fail} FAILURE(S)` : '\nALL GREEN -- only +100 and longer makes the board; locked bets are untouched');
process.exit(fail ? 1 : 0);
