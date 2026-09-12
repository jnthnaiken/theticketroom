#!/usr/bin/env node
/* test_anchorcap.js -- ANCHORCAP2-2026-09-12. FOUR ANCHORS IS A CAP.
 *
 * Owner, on the 2026-09-12 board: "havertz shouldnt be an anchor, hes a leg already and that
 * makes 5 anchors. 5 is more than 4. i know math is hard. fix it."
 *
 * The rule had been stated before (ANCHORCAP-2026-09-06) and broken again from a new direction,
 * so it now lives at the one place every draft path converges -- the end of redraft() -- and
 * this pins the four things it has to get right. Case 4 is the one that keeps an over-eager
 * fix honest: an anchor mirroring onto HIS OWN builder is the legal repeat and must survive.
 *
 *   node test_anchorcap.js
 */
const SD = require('./soccer_draft.js');
const cfg = { ANCH: 4 };

let fails = 0;
function check(label, cond, detail) {
  console.log((cond ? '  ok   ' : '  FAIL ') + label + (cond || !detail ? '' : '  -> ' + detail));
  if (!cond) fails++;
}
const slip = (name, kind, legs, locked) => ({
  name, kind, locked: !!locked, anchor: legs[0],
  players: legs.map((n) => ({ name: n }))
});
const anchorsOf = (out) => {
  const seen = [];
  out.forEach((t) => {
    if (t.kind !== 'moon' && t.kind !== 'builder') return;
    const a = t.anchor || t.players[0].name;
    if (seen.indexOf(a) < 0) seen.push(a);
  });
  return seen;
};
/* TOTAL decides who is weakest when seats have to go */
const D = { players: {
  A: { TOTAL: 160 }, B: { TOTAL: 150 }, C: { TOTAL: 140 }, E: { TOTAL: 130 }, H: { TOTAL: 120 },
  p1: { TOTAL: 90 }, p2: { TOTAL: 89 }, p3: { TOTAL: 88 }, p4: { TOTAL: 87 }
} };

/* ---- 1. THE LIVE BUG: a builder anchored by a man who is a leg on someone else's moon ---- */
{
  const out = [
    slip('m1', 'moon', ['A', 'p1', 'p2']), slip('b1', 'builder', ['A']),
    slip('m2', 'moon', ['B', 'p3', 'p4']), slip('b2', 'builder', ['B']),
    slip('m3', 'moon', ['C', 'p1', 'p3']), slip('b3', 'builder', ['C']),
    slip('m4', 'moon', ['E', 'H', 'p2']),  slip('b4', 'builder', ['E']),
    slip('b5', 'builder', ['H'])            /* <- Havertz: already a leg on m4 */
  ];
  const dem = [];
  const res = SD.enforceAnchorCap(out.slice(), D, cfg, dem);
  const anc = anchorsOf(res);
  check('the duplicate builder is dropped', !res.some((t) => t.name === 'b5'));
  check('board comes back at 4 anchors', anc.length === 4, anc.join(','));
  check('H keeps his leg on the moon', res.some((t) => t.name === 'm4' && t.players.some((l) => l.name === 'H')));
  check('and the reason is recorded', dem.some((d) => d.anchor === 'H' && /already a leg/.test(d.why)));
}

/* ---- 2. THE SAME SHAPE, FROZEN: a placed bet is never deleted, only reported -------------- */
{
  const out = [
    slip('m1', 'moon', ['A', 'p1', 'p2'], true), slip('b1', 'builder', ['A'], true),
    slip('m2', 'moon', ['B', 'p3', 'p4'], true), slip('b2', 'builder', ['B'], true),
    slip('m3', 'moon', ['C', 'p1', 'p3'], true), slip('b3', 'builder', ['C'], true),
    slip('m4', 'moon', ['E', 'H', 'p2'], true),  slip('b4', 'builder', ['E'], true),
    slip('b5', 'builder', ['H'], true)
  ];
  const dem = [];
  const res = SD.enforceAnchorCap(out.slice(), D, cfg, dem);
  check('CONFLOCK holds -- nothing is removed', res.length === out.length, res.length + ' of ' + out.length);
  check('but it is reported loudly', dem.some((d) => /FROZEN/.test(d.why)));
  check('and the overage is reported too', dem.some((d) => /OVER ANCH/.test(d.why)));
}

/* ---- 3. FIVE CLEAN ANCHORS, NO DUPLICATE: the weakest seat goes ---------------------------- */
{
  const out = [
    slip('m1', 'moon', ['A', 'p1', 'p2']), slip('b1', 'builder', ['A']),
    slip('m2', 'moon', ['B', 'p3', 'p4']), slip('b2', 'builder', ['B']),
    slip('m3', 'moon', ['C', 'p1', 'p3']), slip('b3', 'builder', ['C']),
    slip('m4', 'moon', ['E', 'p2', 'p4']), slip('b4', 'builder', ['E']),
    slip('m5', 'moon', ['H', 'p1', 'p4']), slip('b5', 'builder', ['H'])
  ];
  const dem = [];
  const anc = anchorsOf(SD.enforceAnchorCap(out.slice(), D, cfg, dem));
  check('trimmed to 4 anchors', anc.length === 4, anc.join(','));
  check('the WEAKEST one is the one dropped (H, TOTAL 120)', anc.indexOf('H') < 0, anc.join(','));
  check('all of the dropped anchor goes, not just one slip',
        SD.enforceAnchorCap(out.slice(), D, cfg, []).filter((t) => (t.anchor === 'H')).length === 0);
}

/* ---- 4. THE LEGAL REPEAT MUST SURVIVE ------------------------------------------------------
   "The only legal repeat is an anchor mirroring onto his own builder" (index.html). Four
   anchors, each on a moon pair and his own builder, is the NORMAL board -- if this trips, the
   invariant eats every board it touches. */
{
  const out = [
    slip('m1', 'moon', ['A', 'p1', 'p2']), slip('m1b', 'moon', ['A', 'p3', 'p4']), slip('b1', 'builder', ['A']),
    slip('m2', 'moon', ['B', 'p3', 'p4']), slip('b2', 'builder', ['B']),
    slip('m3', 'moon', ['C', 'p1', 'p3']), slip('b3', 'builder', ['C']),
    slip('m4', 'moon', ['E', 'p2', 'p4']), slip('b4', 'builder', ['E']),
    slip('lunch1', 'lunch', ['p1'])
  ];
  const dem = [];
  const res = SD.enforceAnchorCap(out.slice(), D, cfg, dem);
  check('a normal 4-anchor board is untouched', res.length === out.length, res.length + ' of ' + out.length);
  check('nothing is demoted', dem.length === 0, JSON.stringify(dem));
  check('the lunch special survives', res.some((t) => t.kind === 'lunch'));
}

console.log(fails ? '\n' + fails + ' CHECK(S) FAILED' : '\nALL GREEN -- four anchors is a cap, and the legal mirror survives');
process.exit(fails ? 1 : 0);
