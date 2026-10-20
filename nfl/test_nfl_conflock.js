#!/usr/bin/env node
/* test_nfl_conflock.js -- CONFLOCK-NFL-2026-10-19.
 *
 * Owner, 10-19, after George Kittle's single dropped off the MNF board on a later build:
 *   "once he was confirmed, he shouldnt have been able to drop off unless he wasnt starting".
 * Football never sent `status: 'confirmed'` server-side (nfl_payload.py hard-coded 'projected'),
 * so CONFLOCK could never freeze a football slip before kickoff and every build re-ranked it.
 * nfl_injuries.py now confirms everyone the posted inactives list leaves active; this file proves
 * the drafter then holds the slip:
 *   1. every leg confirmed, before kickoff        -> locked, legs verbatim
 *   2. ... and a later build re-scores him down    -> still locked, still verbatim (the Kittle case)
 *   3. one leg still projected                    -> not locked (the repair window is intact)
 *   4. confirmed leg goes OUT before the latch     -> not locked, repaired
 *
 *     node test_nfl_conflock.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SD = require(path.join(__dirname, '..', 'soccer', 'soccer_draft.js'));
SD.DEFAULTS.TOP_SINGLES = 0; SD.DEFAULTS.MIN_ODDS = null;

const base = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'soccer', 'fixtures', '2026-08-26', 'soccer_D.json'), 'utf8'));
const KO = 19 * 60, NOW = KO - 60;     /* an hour out: inactives posted, game not started */
let fail = 0;
const chk = (l, ok, d) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${l}`); if (!ok) { fail++; if (d !== undefined) console.log('      ' + JSON.stringify(d)); } };
function board() {
  const D = JSON.parse(JSON.stringify(base));
  D.meta.ko = {}; D.meta.finals = []; D.meta.gs = {};
  Object.keys(D.players).forEach(n => { const p = D.players[n]; D.meta.ko[String(p.game)] = KO; p.status = 'projected'; p.hr = false; p.goalmins = []; });
  (D.tickets || []).forEach(t => { delete t.locked; });
  return D;
}
const legs = t => t.players.map(l => l.name).join('+');
const CFG = { TOP_SINGLES: 0, LOCK_ON_KICKOFF: true };
const target = board().tickets[0];

{ const D = board(); D.tickets[0].players.forEach(l => { D.players[l.name].status = 'confirmed'; });
  const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG, xi: null, xiMatches: null });
  const t = r.tickets.find(x => x.name === target.name);
  chk('1. all legs confirmed before kickoff -> locked, legs verbatim', t && t.locked && legs(t) === legs(target), t && { locked: t.locked, legs: legs(t) });
  /* 2 -- the next build: the latch rides LOCKCARRY, and the anchor's number collapses. */
  const D2 = JSON.parse(JSON.stringify(D)); D2.tickets = r.tickets.map(x => JSON.parse(JSON.stringify(x)));
  target.players.forEach(l => { D2.players[l.name].TOTAL = 0.1; D2.players[l.name].blend = 0.01; D2.players[l.name].novalue = true; });
  const r2 = SD.redraft(D2, { nowUTCmin: NOW + 10, cfg: Object.assign({ VALUE_ONLY: true }, CFG), xi: null, xiMatches: null });
  const t2 = r2.tickets.find(x => x.name === target.name);
  chk('2. later build re-scores the legs to nothing -> still locked, legs verbatim', t2 && t2.locked && legs(t2) === legs(target), t2 && { locked: t2.locked, legs: legs(t2) });
}
{ const D = board(); D.tickets[0].players.forEach((l, i) => { if (i) D.players[l.name].status = 'confirmed'; });
  const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG, xi: null, xiMatches: null });
  const t = r.tickets.find(x => x.name === target.name);
  chk('3. one leg still projected -> not locked', t && !t.locked, t && { locked: t.locked }); }
{ const D = board(); D.tickets[0].players.forEach(l => { D.players[l.name].status = 'confirmed'; });
  const dead = target.players[target.players.length - 1].name; D.players[dead].out = true;
  const r = SD.redraft(D, { nowUTCmin: NOW, cfg: CFG, xi: null, xiMatches: null });
  const t = r.tickets.find(x => x.name === target.name);
  chk('4. a confirmed leg goes OUT before the latch -> not locked, he is repaired off', !t || (!t.locked && !t.players.some(l => l.name === dead)), t && { locked: t.locked, legs: legs(t) }); }

console.log(fail ? `\n${fail} FAILED` : '\nall CONFLOCK-NFL checks pass');
process.exit(fail ? 1 : 0);
