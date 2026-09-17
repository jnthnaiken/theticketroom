/* test_top8.js -- TOP8-2026-09-17: the soccer board is the top N confirmed starters as 1u singles.
 *   1. fresh draft: N builders, strongest first, <= TOP_PER_MATCH per match, floor respected
 *   2. redraft: a benched pick is replaced by the next man; everyone else keeps his title
 *   3. redraft: a LOCKED single is carried verbatim, even if he would no longer rank
 *   4. redraft: an open single whose match has started is pinned, not replaced
 *   5. redraft: nobody is minted into a match that has started (MINTGUARD)
 *   6. NFL pins TOP_SINGLES 0 and still drafts moons
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SD = require('./soccer_draft.js');
let fail = 0;
const chk = (l, ok, d) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${l}`); if (!ok) { fail++; if (d !== undefined) console.log('      ' + JSON.stringify(d).slice(0, 300)); } };
const J = p => JSON.parse(fs.readFileSync(path.join(__dirname, p), 'utf8'));
const N = SD.DEFAULTS.TOP_SINGLES, CAP = SD.DEFAULTS.TOP_PER_MATCH;

console.log('=== 1. fresh draft ===');
{
  const scored = J('fixtures/2026-08-26/scored.json');
  const r = SD.draft(scored, {}, {});
  const legs = r.tickets.map(t => t.legs[0]);
  chk(`defaults are top ${N}, ${CAP} per match`, N === 8 && CAP === 2);
  chk(`${N} singles`, r.tickets.length === N && r.tickets.every(t => t.kind === 'builder' && t.legs.length === 1 && t.risk === 1), r.tickets.length);
  const per = {}; legs.forEach(l => per[l.match] = (per[l.match] || 0) + 1);
  chk('per-match cap holds', Object.values(per).every(v => v <= CAP), per);
  chk('floor holds', legs.every(l => SD.priceOk(l, SD.DEFAULTS)));
  const elig = scored.filter(p => !p.out && !p.void && SD.priceOk(p, SD.DEFAULTS)).sort((a, b) => b.TOTAL - a.TOTAL);
  chk('the strongest eligible man is first', legs[0].name === elig[0].name, [legs[0].name, elig[0].name]);
  const xi = SD.nameSet(elig.slice(1).map(p => p.name));
  const r2 = SD.draft(scored, {}, { xi });
  chk('XI filter: a benched top man is not drafted', !r2.tickets.some(t => t.legs[0].name === elig[0].name));
}

function board() {
  const D = J('boards/2026-09-16.json');
  Object.keys(D.players).forEach(n => { D.players[n].status = 'projected'; delete D.players[n].out; });
  D.meta.finals = []; D.meta.gs = {};
  D.tickets = [];
  const ko = Math.min(...Object.values(D.meta.ko).map(Number));
  let r = SD.redraft(D, { nowUTCmin: ko - 120, xi: null });
  D.tickets = r.tickets;
  return { D, ko };
}

console.log('\n=== 2. redraft: a benched pick is replaced ===');
{
  const { D, ko } = board();
  chk(`an empty board fills to ${N}`, D.tickets.length === N, D.tickets.length);
  const before = D.tickets.map(t => [t.name, t.players[0].name]);
  const victim = before[0][1];
  D.players[victim].out = true;
  const r = SD.redraft(D, { nowUTCmin: ko - 90, xi: null });
  const names = r.tickets.map(t => t.players[0].name);
  chk('the benched man is gone', !names.includes(victim));
  chk(`still ${N} singles`, r.tickets.length === N, r.tickets.length);
  const keep = before.slice(1).filter(([t, n]) => names.includes(n));
  chk('every survivor keeps his title', keep.every(([t, n]) => r.tickets.find(x => x.players[0].name === n).name === t), keep);
  chk('titles are unique', new Set(r.tickets.map(t => t.name)).size === r.tickets.length);
  chk('reported as changed', r.changed === true);
}

console.log('\n=== 3. redraft: a LOCKED single is carried ===');
{
  const { D, ko } = board();
  const t0 = D.tickets[D.tickets.length - 1], who = t0.players[0].name;
  D.players[who].status = 'confirmed';
  D.players[who].TOTAL = -999;
  const r = SD.redraft(D, { nowUTCmin: ko - 60, xi: null });
  const kept = r.tickets.find(t => t.name === t0.name);
  chk(`locked "${t0.name}" (${who}) is carried`, !!kept && kept.players[0].name === who && kept.locked === true);
  chk(`board is still ${N}`, r.tickets.length === N, r.tickets.length);
}

console.log('\n=== 4 & 5. kickoff: pinned, and no mint into a started match ===');
{
  const { D } = board();
  const t0 = D.tickets[0], who = t0.players[0].name, g = String(D.players[who].game);
  const start = Number(D.meta.ko[g]);
  const r = SD.redraft(D, { nowUTCmin: start + 5, xi: null });
  chk(`open single on a started match (${who}) is pinned`, r.tickets.some(t => t.name === t0.name && t.players[0].name === who));
  const started = Object.keys(D.meta.ko).filter(k => Number(D.meta.ko[k]) <= start + 5);
  const priorNames = new Set(D.tickets.map(t => t.players[0].name));
  const fresh = r.tickets.filter(t => !priorNames.has(t.players[0].name));
  chk('nothing new is minted into a started match', fresh.every(t => !started.includes(String(D.players[t.players[0].name].game))), fresh.map(t => t.players[0].name));
}

console.log('\n=== 6. NFL is untouched ===');
{
  const src = fs.readFileSync(path.join(__dirname, '..', 'nfl', 'nfl_draft_cli.js'), 'utf8');
  const m = src.match(/const CFG = (\{[\s\S]*?\});/);
  const CFG = Function('return ' + m[1])();
  chk('nfl_draft_cli pins TOP_SINGLES 0', CFG.TOP_SINGLES === 0);
  const scored = J('fixtures/2026-08-26/scored.json');
  const r = SD.draft(scored, { TOP_SINGLES: 0, MIN_ODDS: null }, {});
  chk('with TOP_SINGLES 0 the engine drafts screamers', r.tickets.some(t => t.kind === 'moon'));
}
console.log(fail ? `\n${fail} FAILURE(S)` : '\nALL GREEN -- top-8 singles board');
process.exit(fail ? 1 : 0);
